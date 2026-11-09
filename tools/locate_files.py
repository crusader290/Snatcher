#!/usr/bin/env python3
"""Locate where disc files are resident in probe memory snapshots.

For every extracted ISO file (and the IP/SP system-area programs) this
searches main RAM (FF0000), sub PRG RAM (000000) and Word RAM snapshots for
chunks of the file, and reports the implied load address and how many bytes
match contiguously.  Output is JSON; it is evidence for the recipe, not code.

usage: locate_files.py EXTRACT_DIR PROBE_DIR [PROBE_DIR ...] > located.json
"""
import json
import re
import sys
from pathlib import Path

REGIONS = {  # dump-name pattern -> (cpu view, base address)
    "main-ram": ("MAIN", 0xFF0000),
    "sub-prg": ("SUB", 0x000000),
    "word-ram": ("WORD2M", 0x000000),  # offset inside 256 KiB Word RAM
}
CHUNK = 64


def dumps(probe_dirs):
    for d in probe_dirs:
        for p in sorted(Path(d).glob("*.bin")):
            for key, (view, base) in REGIONS.items():
                if p.name.endswith(key + ".bin") and "selfloop" not in p.name:
                    yield p, view, base


def match_len(mem: bytes, at: int, data: bytes, start: int) -> int:
    n = 0
    while start + n < len(data) and at + n < len(mem) and mem[at + n] == data[start + n]:
        n += 1
    return n


def main() -> int:
    extract, probe_dirs = Path(sys.argv[1]), sys.argv[2:]
    files = {p.relative_to(extract / "files").as_posix(): p.read_bytes()
             for p in (extract / "files").rglob("*") if p.is_file()}
    files["<IP>"] = (extract / "ip.bin").read_bytes()
    files["<SP>"] = (extract / "sp.bin").read_bytes()
    mems = [(p, view, base, p.read_bytes()) for p, view, base in dumps(probe_dirs)]
    result = {}
    for name, data in sorted(files.items()):
        if len(data) > 4 * 1024 * 1024:
            continue  # streamed media
        hits = {}
        for start in range(0, len(data) - CHUNK, 0x800):
            chunk = data[start:start + CHUNK]
            if len(set(chunk)) < 8:
                continue  # skip low-entropy padding
            for path, view, base, mem in mems:
                for m in re.finditer(re.escape(chunk), mem):
                    addr = base + m.start() - start
                    key = (view, addr)
                    length = match_len(mem, m.start(), data, start)
                    best = hits.get(key)
                    span = (start, start + length)
                    if not best or length > best["bytes"]:
                        hits[key] = {"view": view, "load_address": f"0x{addr:06X}",
                                     "file_offset": start, "bytes": length,
                                     "snapshot": path.parent.name + "/" + path.name}
        if hits:
            result[name] = {"size": len(data),
                            "placements": sorted(hits.values(), key=lambda h: -h["bytes"])[:6]}
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
