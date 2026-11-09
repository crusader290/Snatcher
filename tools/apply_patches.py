#!/usr/bin/env python3
"""Apply this project's local fixes to the pinned engine submodule (idempotent)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    "segagenesisrecomp": ROOT / "external" / "segagenesisrecomp",
    "segarecomp": ROOT / "external" / "segarecomp",
}


def git(repo: Path, *args: str) -> int:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode


def main() -> int:
    failed = 0
    for name, repo in TARGETS.items():
        for patch in sorted((ROOT / "patches" / name).glob("*.patch")):
            if git(repo, "apply", "--check", "-R", str(patch)) == 0:
                print(f"already applied: {patch.name}")
            elif git(repo, "apply", str(patch)) == 0:
                print(f"applied: {patch.name}")
            else:
                print(f"FAILED: {patch.name}", file=sys.stderr)
                failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
