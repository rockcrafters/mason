"""View log / prompt / metadata files for a cached run."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools._common import _die, resolve

_WHICH = {
    "run": "run.log",
    "stdout": "stdout.log",
    "stderr": "stderr.log",
    "prompt": "prompt.txt",
    "meta": "metadata.json",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="cat log / prompt / metadata for a cached run")
    ap.add_argument("spec", nargs="?", default=None, help="substring of <model>/<case>")
    ap.add_argument(
        "--which",
        default="run",
        choices=sorted(_WHICH.keys()),
        help="which file to view (default: run)",
    )
    args = ap.parse_args(argv)

    run_dir = resolve(args.spec)
    path = run_dir / _WHICH[args.which]
    if not path.exists():
        _die(f"{path} missing")
    sys.stdout.write(f"==> {path} <==\n")
    sys.stdout.flush()
    sys.stdout.buffer.write(path.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
