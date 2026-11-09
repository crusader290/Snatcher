#!/usr/bin/env python3
"""Write a formatted, empty 8 KiB Sega CD internal backup RAM image.

segarecomp's `--backup-ram` wants a formatted image; an unformatted one makes Snatcher stop at its
"initialise the memory" screen. The layout matches what the US v1.10 BIOS writes when it formats internal
RAM (docs/FINDINGS.md section 4): the body stays 0xFF and only the 64-byte directory/format block at the
end changes. Nothing here comes from the BIOS image itself.

usage: make_bram.py OUT.bin
"""
import sys

SIZE = 8192
BLOCKS = 0x7D  # free 64-byte blocks reported by the format


def image() -> bytes:
    tail = bytearray(b"_" * 11)                 # empty directory name field
    tail += bytes(4)
    tail += bytes((0x40,))                      # format flag
    tail += bytes((0x00, BLOCKS)) * 4           # free-block count, stored four times
    tail += bytes(8)
    tail += b"SEGA_CD_ROM" + bytes((0x00, 0x01, 0x00, 0x00, 0x00))
    tail += b"RAM_CARTRIDGE___"
    assert len(tail) == 64
    return b"\xff" * (SIZE - 64) + bytes(tail)


def main() -> int:
    with open(sys.argv[1], "wb") as f:
        f.write(image())
    print(f"{sys.argv[1]}: formatted empty backup RAM ({SIZE} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
