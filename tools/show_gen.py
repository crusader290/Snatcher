#!/usr/bin/env python3
"""Print generated per-instruction semantics from a segacd_module_recompiler
output directory for one or more PC ranges (diagnostic reading aid).

usage: show_gen.py GEN_DIR PREFIX LO-HI [LO-HI ...]   (hex addresses)
"""
import glob
import re
import sys
from pathlib import Path


def simplify(body: str) -> str:
    body = re.sub(r"\s+", " ", body)
    body = re.sub(r"\{ uint\d+_t _f[^}]*\}", "", body)          # flag blocks
    body = re.sub(r"g_cpu\.SR = \(g_cpu\.SR & ~\(1u<<2\)\)[^;]*;", "Z=..;", body)
    body = body.replace("ctx->charge=", "c=").replace("g_cpu.", "")
    return body.strip()


def main() -> int:
    gen, prefix, ranges = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    src = "".join(Path(f).read_text() for f in sorted(glob.glob(str(gen / f"{prefix}_part*.c"))))
    fns = {int(m.group(1), 16): m.group(2) for m in
           re.finditer(rf"void {prefix}_at_([0-9A-F]{{6}})\(M68kStepContext \*ctx\)\{{(.*?)\n\}}", src, re.S)}
    for r in ranges:
        lo, hi = (int(x, 16) for x in r.split("-"))
        for pc in sorted(p for p in fns if lo <= p < hi):
            print(f"{pc:06X}  {simplify(fns[pc])[:260]}")
        print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
