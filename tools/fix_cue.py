#!/usr/bin/env python3
"""Make a CUE sheet usable by segarecomp: every FILE line must name a file that exists beside the CUE.

Some dumps write `FILE "Name" BINARY` without the `.bin` extension. If every FILE line already resolves,
the CUE is printed unchanged; otherwise a corrected `<name>.fixed.cue` is written beside it and printed.

usage: fix_cue.py DISC.cue   -> prints the CUE path to use
"""
import re
import sys
from pathlib import Path

FILE_LINE = re.compile(r'^(\s*FILE\s+)"([^"]+)"(.*)$', re.IGNORECASE)


def main() -> int:
    cue = Path(sys.argv[1]).resolve()
    lines, changed = cue.read_text(encoding="latin-1").splitlines(), False
    for i, line in enumerate(lines):
        m = FILE_LINE.match(line)
        if not m or (cue.parent / m.group(2)).is_file():
            continue
        for ext in (".bin", ".BIN", ".img", ".iso"):
            if (cue.parent / (m.group(2) + ext)).is_file():
                lines[i], changed = f'{m.group(1)}"{m.group(2) + ext}"{m.group(3)}', True
                break
        else:
            print(f"{cue}: FILE \"{m.group(2)}\" not found beside the CUE", file=sys.stderr)
            return 1
    if not changed:
        print(cue)
        return 0
    out = cue.with_name(cue.stem + ".fixed.cue")
    out.write_text("\n".join(lines) + "\n", encoding="latin-1", newline="\r\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
