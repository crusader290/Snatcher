#!/usr/bin/env python3
"""Convert segarecomp Sega CD canonical frame captures (canon_<onset>.bin) to PNG.

Format (platforms/sega-cd/runtime/scd_vdp.c, scd_canonical_frame): u16le width, u16le height, then one
u16le per pixel: bit 9 set, bits 8-0 = BBBGGGRRR (3 bits each, Genesis CRAM levels).
usage: canon2png.py canon_600.bin [...]   -> canon_600.png beside each input (2x scale)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ppm2png import write_png  # noqa: E402

LEVEL = [0, 36, 73, 109, 146, 182, 219, 255]


def convert(path: Path) -> Path:
    data = path.read_bytes()
    w, h = struct.unpack_from("<HH", data, 0)
    words = struct.unpack_from(f"<{w * h}H", data, 4)
    rgb = bytearray()
    for v in words:
        c = v & 0x1FF
        rgb += bytes((LEVEL[c & 7], LEVEL[(c >> 3) & 7], LEVEL[(c >> 6) & 7]))
    out = path.with_suffix(".png")
    write_png(out, w, h, bytes(rgb), 2)
    return out


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(convert(Path(name)))
