#!/usr/bin/env python3
"""Convert binary PPM (P6) probe frames to PNG with optional integer scale. No dependencies."""
import struct
import sys
import zlib
from pathlib import Path


def read_ppm(path: Path):
    data = path.read_bytes()
    fields, pos = [], 0
    while len(fields) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[pos:end])
        pos = end
    assert fields[0] == b"P6" and int(fields[3]) == 255
    w, h = int(fields[1]), int(fields[2])
    return w, h, data[pos + 1:pos + 1 + w * h * 3]


def write_png(path: Path, w: int, h: int, rgb: bytes, scale: int = 1):
    rows = bytearray()
    for y in range(h):
        line = rgb[y * w * 3:(y + 1) * w * 3]
        if scale > 1:
            line = b"".join(line[x * 3:x * 3 + 3] * scale for x in range(w))
        for _ in range(scale):
            rows += b"\x00" + line

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b"")
    path.write_bytes(png)


if __name__ == "__main__":
    scale = 2
    for name in sys.argv[1:]:
        p = Path(name)
        w, h, rgb = read_ppm(p)
        write_png(p.with_suffix(".png"), w, h, rgb, scale)
