#!/usr/bin/env python3
"""Tile segarecomp canonical frame captures (canon_<onset>.bin) into one PNG contact sheet, ordered by onset.

usage: canon_sheet.py OUT.png DIR [COLUMNS]   (1x scale, 4 px gaps)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canon2png import LEVEL  # noqa: E402
from ppm2png import write_png  # noqa: E402


def load(path):
    data = path.read_bytes()
    w, h = struct.unpack_from("<HH", data, 0)
    return w, h, struct.unpack_from(f"<{w * h}H", data, 4)


def main() -> int:
    out, src = Path(sys.argv[1]), Path(sys.argv[2])
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    frames = sorted(src.glob("canon_*.bin"), key=lambda p: int(p.stem.split("_")[1]))
    if not frames:
        print(f"{src}: no canon_*.bin", file=sys.stderr)
        return 1
    tiles = [load(p) for p in frames]
    tw, th, gap = max(t[0] for t in tiles), max(t[1] for t in tiles), 4
    rows = (len(tiles) + cols - 1) // cols
    W, H = cols * tw + (cols - 1) * gap, rows * th + (rows - 1) * gap
    canvas = bytearray(b"\x40\x40\x40" * W * H)
    for i, (w, h, px) in enumerate(tiles):
        ox, oy = (i % cols) * (tw + gap), (i // cols) * (th + gap)
        for y in range(h):
            row = bytearray()
            for v in px[y * w:(y + 1) * w]:
                c = v & 0x1FF
                row += bytes((LEVEL[c & 7], LEVEL[(c >> 3) & 7], LEVEL[(c >> 6) & 7]))
            o = ((oy + y) * W + ox) * 3
            canvas[o:o + len(row)] = row
    write_png(out, W, H, bytes(canvas), 1)
    print(f"{out}: {' '.join(p.stem.split('_')[1] for p in frames)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
