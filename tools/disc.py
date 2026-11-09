#!/usr/bin/env python3
"""Snatcher (Sega CD) disc inspection: CUE/BIN reader, ISO9660 listing,
system-area (IP/SP) extraction.  Owned-input tool; writes nothing into the
source tree except under the explicit output directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

RAW = 2352


def msf(text: str) -> int:
    m, s, f = (int(x) for x in text.split(":"))
    return (m * 60 + s) * 75 + f


class Cue:
    def __init__(self, path: Path):
        self.path = path
        self.bin = None
        self.tracks: list[dict] = []
        cur = None
        for line in path.read_text(errors="replace").splitlines():
            tok = line.strip().split()
            if not tok:
                continue
            if tok[0] == "FILE":
                name = re.match(r'\s*FILE\s+"(.*)"\s+\w+', line).group(1)
                cand = path.parent / name
                if not cand.exists():
                    cand = path.parent / (name + ".bin")
                self.bin = cand
            elif tok[0] == "TRACK":
                cur = {"number": int(tok[1]), "mode": tok[2], "index": {}}
                self.tracks.append(cur)
            elif tok[0] == "INDEX":
                cur["index"][int(tok[1])] = msf(tok[2])
        total = self.bin.stat().st_size // RAW
        for i, t in enumerate(self.tracks):
            t["start"] = t["index"][1]
            t["end"] = (self.tracks[i + 1]["index"].get(0, self.tracks[i + 1]["index"][1])
                        if i + 1 < len(self.tracks) else total)


class DataTrack:
    """MODE1/2352 user-data reader for track 1 (file LBA 0 == disc LBA 0)."""

    def __init__(self, cue: Cue):
        self.f = cue.bin.open("rb")
        t = cue.tracks[0]
        assert t["mode"] == "MODE1/2352", t
        self.first, self.end = t["start"], t["end"]

    def sector(self, lba: int) -> bytes:
        self.f.seek((self.first + lba) * RAW)
        raw = self.f.read(RAW)
        if len(raw) != RAW or raw[0:12] != b"\x00" + b"\xff" * 10 + b"\x00" or raw[15] != 1:
            raise ValueError(f"bad MODE1 sector at LBA {lba}")
        return raw[16:16 + 2048]

    def read(self, lba: int, size: int) -> bytes:
        out = bytearray()
        n = (size + 2047) // 2048
        for i in range(n):
            out += self.sector(lba + i)
        return bytes(out[:size])


def iso_walk(dt: DataTrack):
    pvd = dt.sector(16)
    assert pvd[1:6] == b"CD001", "no ISO9660 PVD"
    root = pvd[156:156 + 34]
    files = []

    def walk(lba, size, prefix):
        data = dt.read(lba, size)
        off = 0
        while off < len(data):
            ln = data[off]
            if ln == 0:
                off = (off // 2048 + 1) * 2048
                continue
            rec = data[off:off + ln]
            ext = struct.unpack_from("<I", rec, 2)[0]
            sz = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            nl = rec[32]
            name = rec[33:33 + nl]
            off += ln
            if name in (b"\x00", b"\x01"):
                continue
            nm = name.decode("ascii", "replace").split(";")[0]
            if flags & 2:
                walk(ext, sz, prefix + nm + "/")
            else:
                files.append({"path": prefix + nm, "lba": ext, "size": sz})

    walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
    return pvd, files


def system_area(dt: DataTrack) -> dict:
    hdr = dt.read(0, 0x8000)
    u32 = lambda o: struct.unpack_from(">I", hdr, o)[0]
    info = {
        "disc_id": hdr[0:16].decode("ascii", "replace"),
        "volume": hdr[0x10:0x1B].decode("ascii", "replace"),
        "system": hdr[0x20:0x2B].decode("ascii", "replace"),
        "ip": {"offset": u32(0x30), "size": u32(0x34), "entry": u32(0x38), "work": u32(0x3C)},
        "sp": {"offset": u32(0x40), "size": u32(0x44), "entry": u32(0x48), "work": u32(0x4C)},
        "hardware": hdr[0x100:0x110].decode("ascii", "replace"),
        "copyright": hdr[0x110:0x120].decode("ascii", "replace"),
        "title_domestic": hdr[0x120:0x150].decode("ascii", "replace").strip(),
        "title_overseas": hdr[0x150:0x180].decode("ascii", "replace").strip(),
        "serial": hdr[0x180:0x18E].decode("ascii", "replace"),
        "region": hdr[0x1F0:0x1F3].decode("ascii", "replace"),
    }
    return info, hdr


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cue", type=Path)
    ap.add_argument("--extract", type=Path, help="write system area + every ISO file here")
    a = ap.parse_args(argv)
    cue = Cue(a.cue)
    dt = DataTrack(cue)
    info, hdr = system_area(dt)
    _, files = iso_walk(dt)
    report = {"bin": str(cue.bin), "tracks": [{k: t[k] for k in ("number", "mode", "start", "end")}
                                              for t in cue.tracks],
              "system_area": info, "files": files}
    if a.extract:
        out = a.extract
        (out / "files").mkdir(parents=True, exist_ok=True)
        (out / "system_area.bin").write_bytes(hdr)
        ip, sp = info["ip"], info["sp"]
        (out / "ip.bin").write_bytes(hdr[ip["offset"]:ip["offset"] + ip["size"]])
        (out / "sp.bin").write_bytes(dt.read(sp["offset"] // 2048, sp["offset"] % 2048 + sp["size"])
                                     [sp["offset"] % 2048:])
        for row in files:
            data = dt.read(row["lba"], row["size"])
            row["sha256"] = hashlib.sha256(data).hexdigest()
            dest = out / "files" / row["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        (out / "inventory.json").write_text(json.dumps(report, indent=2) + "\n")
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
