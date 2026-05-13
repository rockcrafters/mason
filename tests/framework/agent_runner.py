"""agent backends. each subclass of Backend handles one underlying agent
(cli binary, sdk, future codex, etc). shared run loop + watchdog live here.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "AgentResult",
    "Backend",
    "ClaudeCli",
    "EvalError",
    "ProgressCallback",
    "get_backend",
]


ProgressCallback = Callable[[dict], None]


class EvalError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentResult:
    text: str
    returncode: int
    stdout_path: Path
    stderr_path: Path


# ----- generic run loop helpers -----

def _stream_pipe(
    pipe, sink, chunks: list[str], on_event: ProgressCallback | None = None
) -> None:
    for line in pipe:
        chunks.append(line)
        sink.write(line)
        sink.flush()
        if on_event is not None and line.lstrip().startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                try:
                    on_event(event)
                except Exception:
                    pass
    pipe.close()


def _terminate(process: subprocess.Popen) -> None:
    try:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    except OSError:
        pass


# ----- backend abstraction -----

class Backend(ABC):
    """Abstract agent backend. Subclasses define command shape + output parsing.

    The shared `run` method handles process spawning, log capture, watchdog.
    """

    name: str = "abstract"
    binary: str = ""  # required cli binary on PATH

    @abstractmethod
    def build_command(
        self, model: str, effort: str, prompt: str, *, cwd: Path
    ) -> list[str]:
        """Return argv for one-shot agent invocation."""

    def extract_final_text(self, raw_stdout: str) -> str:
        """Default: return raw stdout. Subclasses can parse structured output."""
        return raw_stdout

    def require_on_path(self) -> None:
        if which(self.binary) is None:
            raise EvalError(f"required command not found on PATH: {self.binary}")

    def run(
        self,
        *,
        model: str,
        effort: str,
        prompt: str,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout: int | None = None,
        stuck_timeout: int = 300,
        on_event: ProgressCallback | None = None,
    ) -> AgentResult:
        self.require_on_path()
        cmd = self.build_command(model, effort, prompt, cwd=cwd)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                text=True,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
        except OSError as exc:
            raise EvalError(f"failed to launch {cmd[0]}: {exc}") from exc

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        with stdout_path.open("w", encoding="utf-8") as so, stderr_path.open(
            "w", encoding="utf-8"
        ) as se:
            out_t = threading.Thread(
                target=_stream_pipe,
                args=(process.stdout, so, stdout_chunks, on_event),
            )
            err_t = threading.Thread(
                target=_stream_pipe, args=(process.stderr, se, stderr_chunks)
            )
            out_t.start()
            err_t.start()

            stuck_event = threading.Event()
            stop_watchdog = threading.Event()

            def watchdog() -> None:
                last = 0
                stale_since: float | None = None
                while not stop_watchdog.wait(timeout=30):
                    if process.poll() is not None:
                        return
                    count = len(stdout_chunks) + len(stderr_chunks)
                    if count != last:
                        last = count
                        stale_since = None
                    else:
                        if stale_since is None:
                            stale_since = time.monotonic()
                        elif time.monotonic() - stale_since >= stuck_timeout:
                            _terminate(process)
                            stuck_event.set()
                            return

            wd_t = threading.Thread(target=watchdog, daemon=True)
            wd_t.start()

            timed_out = False
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate(process)
                returncode = process.wait()

            out_t.join()
            err_t.join()
            stop_watchdog.set()
            wd_t.join(timeout=10)

        if timed_out:
            raise EvalError(f"agent timed out after {timeout}s")
        if stuck_event.is_set():
            raise EvalError(f"agent produced no output for {stuck_timeout}s")

        text = self.extract_final_text("".join(stdout_chunks))
        return AgentResult(
            text=text,
            returncode=returncode,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


# ----- claude cli backend -----

_SANDBOX_DENY = (
    # block upstream chisel-releases fetches + general http retrieval.
    # apt/dpkg/chisel-cut intentionally NOT blocked: agent legitimately
    # needs them to inspect deb contents + self-test its slicing.
    "WebFetch",
    "WebSearch",
    "Bash(curl)",
    "Bash(curl *)",
    "Bash(wget)",
    "Bash(wget *)",
    "Bash(git fetch *)",
    "Bash(git pull *)",
    "Bash(git clone *)",
    "Bash(git remote *)",
    "Bash(git checkout *)",
    "Bash(git ls-remote *)",
    "Bash(pip *)",
)


class ClaudeCli(Backend):
    """anthropic claude cli (`claude --print`). Streams ndjson; deny rules
    enforced via `--disallowedTools` so a sandboxed agent can't relax them
    by writing settings.json (combined w/ `--setting-sources user`).
    """

    name = "claude"
    binary = "claude"

    def __init__(
        self,
        deny: "Sequence[str] | None" = None,
        plugin_dirs: "Sequence[Path] | None" = None,
    ) -> None:
        self.deny: tuple[str, ...] = tuple(deny) if deny is not None else _SANDBOX_DENY
        self.plugin_dirs: tuple[Path, ...] = tuple(plugin_dirs) if plugin_dirs else ()

    def build_command(
        self, model: str, effort: str, prompt: str, *, cwd: Path
    ) -> list[str]:
        cmd = [
            "claude",
            "--print",
            "--model", model,
            "--effort", effort,
            "--permission-mode", "bypassPermissions",
            # ignore sandbox-level settings -- agent can't relax denies by
            # writing <sandbox>/.claude/settings.json
            "--setting-sources", "user",
        ]
        for pdir in self.plugin_dirs:
            cmd += ["--plugin-dir", str(pdir)]
        cmd += [
            # deny rules enforced at cli level
            "--disallowedTools", *self.deny,
            "--verbose",
            "--output-format", "stream-json",
            "--include-partial-messages",
            prompt,
        ]
        return cmd

    def extract_final_text(self, raw_stdout: str) -> str:
        last_result: str | None = None
        assistant_messages: list[str] = []
        for line in raw_stdout.splitlines():
            if not line.lstrip().startswith("{"):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "result":
                if event.get("is_error") is True:
                    continue
                result = event.get("result")
                if isinstance(result, str) and result:
                    last_result = result
                continue
            if event.get("type") != "assistant":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            parts = [
                text
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(text := block.get("text"), str)
                and text
            ]
            if parts:
                assistant_messages.append("".join(parts))
        if last_result is not None:
            return last_result
        if assistant_messages:
            return "\n".join(assistant_messages)
        return raw_stdout


# ----- bwrap-isolated claude cli backend -----

def _resolve_real(p: str) -> Path:
    """Resolve path through symlinks; return Path."""
    return Path(os.path.realpath(p))


class BwrapClaudeCli(ClaudeCli):
    """ClaudeCli wrapped in bubblewrap. Host fs is read-only outside sandbox;
    $HOME is tmpfs w/ only ~/.claude/.credentials.json + claude install bound
    in. Net unrestricted (anthropic api still needs it).

    linux-only. requires `bwrap` and unprivileged user namespaces.

    plugin_mounts: list of (host_path, agent_path) tuples. Each host_path
    is ro-bound at agent_path inside the namespace; agent_path is what's
    passed to claude's `--plugin-dir`. Use to expose a curated subset of
    a plugin source (skills + .claude-plugin) at a neutral mount point
    so the agent can't browse the full host source tree.
    """

    name = "claude"
    binary = "bwrap"

    def __init__(
        self,
        deny=None,
        plugin_mounts: "Sequence[tuple[Path, str]] | None" = None,
    ) -> None:
        # ClaudeCli.plugin_dirs is unused for the sandboxed path -- we add
        # `--plugin-dir <agent_path>` ourselves in build_command below.
        super().__init__(deny=deny, plugin_dirs=None)
        self.plugin_mounts: tuple[tuple[Path, str], ...] = (
            tuple(plugin_mounts) if plugin_mounts else ()
        )
        self._claude_bin = _resolve_real(which("claude") or "claude")
        self._claude_launcher = Path(which("claude") or "")
        # host HOME path is bound back; canonicalise via expanduser.
        self._home = Path(os.path.expanduser("~"))
        self._creds = self._home / ".claude" / ".credentials.json"

    # path the agent sees as its working directory -- masquerades as a
    # plain chisel-releases checkout. host sandbox dir bound here.
    AGENT_ROOT = "/chisel-releases"

    def _bwrap_prefix(self, host_sandbox: Path) -> list[str]:
        host_sandbox = host_sandbox.resolve()
        args: list[str] = ["bwrap"]

        # 1. base layout -- tmpfs for /tmp + fake $HOME. /tmp is wiped so
        #    agent can't pivot via `cd /tmp && clone`. /home likewise.
        args += [
            "--tmpfs", "/tmp",
            "--tmpfs", str(self._home),
            "--proc", "/proc",
            "--dev", "/dev",
        ]

        # 2. ro-bind host system paths needed for binaries + tls
        for p in ("/usr", "/etc", "/bin", "/sbin", "/lib", "/lib64", "/var"):
            if Path(p).exists():
                args += ["--ro-bind-try", p, p]
        # /etc/resolv.conf is usually a symlink to /run/systemd/resolve/...
        if Path("/run/systemd/resolve").exists():
            args += ["--ro-bind", "/run/systemd/resolve", "/run/systemd/resolve"]

        # 3. claude binary install + launcher script
        if self._claude_bin.exists():
            args += ["--ro-bind", str(self._claude_bin), str(self._claude_bin)]
        if self._claude_launcher.exists() and self._claude_launcher != self._claude_bin:
            args += ["--ro-bind", str(self._claude_launcher), str(self._claude_launcher)]

        # 4. credentials -- rw (claude may rotate token)
        if self._creds.exists():
            args += ["--bind", str(self._creds), str(self._creds)]

        # 5. ro-bind plugin sources at neutral agent paths
        for host_path, agent_path in self.plugin_mounts:
            if host_path.exists():
                args += ["--ro-bind", str(host_path), agent_path]

        # 6. writeable sandbox bound to fixed agent path so agent sees
        #    `cwd = /chisel-releases` -- looks like a bare clone (no .git).
        args += ["--bind", str(host_sandbox), self.AGENT_ROOT]

        # 7. namespace + runtime + standardised env
        args += [
            "--unshare-pid",
            "--unshare-uts",
            "--unshare-ipc",
            # net intentionally NOT unshared -- claude api needs internet
            "--die-with-parent",
            "--new-session",
            "--chdir", self.AGENT_ROOT,
            "--clearenv",
            "--setenv", "HOME", str(self._home),
            "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "--setenv", "SHELL", "/bin/bash",
            "--setenv", "TERM", "dumb",
            "--setenv", "LANG", "C.UTF-8",
            "--setenv", "LC_ALL", "C.UTF-8",
            "--",
        ]
        return args

    def build_command(
        self, model: str, effort: str, prompt: str, *, cwd: Path
    ) -> list[str]:
        # build inner argv but inject our plugin_mounts as `--plugin-dir`
        # entries pointing at the in-namespace paths.
        inner = super().build_command(model, effort, prompt, cwd=cwd)
        # find the position right before `--disallowedTools` to inject
        # plugin-dir args (any position before the prompt is fine).
        injection_point = inner.index("--disallowedTools")
        plugin_args: list[str] = []
        for _host, agent_path in self.plugin_mounts:
            plugin_args += ["--plugin-dir", agent_path]
        inner = inner[:injection_point] + plugin_args + inner[injection_point:]
        return [*self._bwrap_prefix(cwd), *inner]


# ----- registry -----

_BACKENDS: dict[str, type[Backend]] = {
    "claude": BwrapClaudeCli,
    "claude-unsandboxed": ClaudeCli,
}


def get_backend(name: str, **kwargs) -> Backend:
    """Instantiate a backend by name. Kwargs forwarded to backend ctor.

    Per-call instantiation -- backends are cheap dataclasses + the
    plugin_mounts / plugin_dirs differ between callers.
    """
    try:
        cls = _BACKENDS[name]
    except KeyError as exc:
        raise EvalError(f"unsupported backend: {name}") from exc
    return cls(**kwargs)


