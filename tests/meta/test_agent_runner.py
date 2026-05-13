"""Tests for backend abstraction + command building."""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.agent_runner import (
    BwrapClaudeCli,
    ClaudeCli,
    EvalError,
    _SANDBOX_DENY,
    get_backend,
)


def test_get_backend_unknown_raises() -> None:
    with pytest.raises(EvalError, match="unsupported backend"):
        get_backend("does-not-exist")


def test_get_backend_returns_fresh_instance() -> None:
    a = get_backend("claude-unsandboxed")
    b = get_backend("claude-unsandboxed")
    assert isinstance(a, ClaudeCli)
    assert a is not b  # factory style, not singleton


def test_claude_cli_command_basic() -> None:
    b = ClaudeCli()
    cmd = b.build_command("model-x", "low", "hello", cwd=Path("/tmp/sb"))
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--model" in cmd and "model-x" in cmd
    assert "--effort" in cmd and "low" in cmd
    assert "--disallowedTools" in cmd
    # deny list passed through
    assert "Bash(curl)" in cmd
    assert "WebFetch" in cmd
    assert cmd[-1] == "hello"


def test_claude_cli_includes_plugin_dirs() -> None:
    b = ClaudeCli(plugin_dirs=[Path("/x/y"), Path("/a/b")])
    cmd = b.build_command("m", "low", "p", cwd=Path("/tmp"))
    # each plugin dir gets a --plugin-dir arg
    idxs = [i for i, x in enumerate(cmd) if x == "--plugin-dir"]
    assert len(idxs) == 2
    assert cmd[idxs[0] + 1] == "/x/y"
    assert cmd[idxs[1] + 1] == "/a/b"


def test_bwrap_command_wraps_inner() -> None:
    b = BwrapClaudeCli(plugin_mounts=[(Path("/tmp"), "/mason-plugin")])
    cmd = b.build_command("m", "low", "p", cwd=Path("/tmp"))
    assert cmd[0] == "bwrap"
    # the inner claude command appears after `--`
    sep = cmd.index("--")
    inner = cmd[sep + 1:]
    assert inner[0] == "claude"
    # plugin mount injected in inner
    assert "--plugin-dir" in inner
    plugin_idx = inner.index("--plugin-dir")
    assert inner[plugin_idx + 1] == "/mason-plugin"


def test_bwrap_chdir_to_agent_root() -> None:
    b = BwrapClaudeCli()
    cmd = b.build_command("m", "low", "p", cwd=Path("/tmp/whatever"))
    chdir_idx = cmd.index("--chdir")
    assert cmd[chdir_idx + 1] == BwrapClaudeCli.AGENT_ROOT


def test_bwrap_clearenv_present() -> None:
    """Standardised env -- never inherit host TERM/SHELL/etc."""
    b = BwrapClaudeCli()
    cmd = b.build_command("m", "low", "p", cwd=Path("/tmp"))
    assert "--clearenv" in cmd
    # baseline envs always set
    setenv_pairs = [
        (cmd[i + 1], cmd[i + 2])
        for i, x in enumerate(cmd)
        if x == "--setenv" and i + 2 < len(cmd)
    ]
    keys = {k for k, _ in setenv_pairs}
    assert {"HOME", "PATH", "SHELL", "TERM", "LANG", "LC_ALL"} <= keys
    term = dict(setenv_pairs)["TERM"]
    assert term == "dumb"
    shell = dict(setenv_pairs)["SHELL"]
    assert shell == "/bin/bash"


def test_sandbox_deny_includes_network_egress() -> None:
    assert "Bash(curl)" in _SANDBOX_DENY
    assert "Bash(curl *)" in _SANDBOX_DENY
    assert "Bash(wget *)" in _SANDBOX_DENY
    assert "Bash(git clone *)" in _SANDBOX_DENY
    assert "WebFetch" in _SANDBOX_DENY
    assert "WebSearch" in _SANDBOX_DENY


def test_sandbox_deny_allows_apt_dpkg_chisel() -> None:
    """Agent legitimately needs these to inspect packages + self-test slicing."""
    for cmd in ("Bash(apt *)", "Bash(dpkg *)", "Bash(chisel cut *)"):
        assert cmd not in _SANDBOX_DENY, f"{cmd} should not be denied"
