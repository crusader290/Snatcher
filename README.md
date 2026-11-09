# Snatcher Recompiled (Sega CD) — work in progress

A static recompilation of Konami's **Snatcher** for the Sega CD (US release,
serial `T-95035`) into native C, built on the same reusable Sega CD backend as
[SonicCDRecomp](https://github.com/mstan/SonicCDRecomp).

The original Main 68000, Sub 68000 and Z80 programs are translated ahead of
time into guarded C. The runtime models the Sega CD hardware: buses, Word RAM,
CDC/CDD, PCM, stamp graphics, VDP, FM/PSG audio and backup RAM.

> **Status: bring-up.** The disc is fully inventoried, the engine is pinned and
> builds with MinGW, and the diagnostic probe boots Snatcher past the licence
> screens into its intro after a VDP interrupt-timing fix (see
> [docs/FINDINGS.md](docs/FINDINGS.md)). Native catalog generation and a
> playable `Snatcher` executable are not done yet.

## You supply the inputs

Nothing from the game or the BIOS is in this repository, and nothing derived
from them (extracted files, captures, generated C) is ever committed.

| Input | Expected identity |
|---|---|
| Sega CD BIOS | US Model 1 v1.10, 131,072 bytes, SHA-256 `807384678ef259494d943eddb6954dfc7069693d0dde0c424e2028488d88e81a` |
| Snatcher disc | US CUE/BIN: one MODE1/2352 data track and 20 audio tracks |

## Layout

```
external/segagenesisrecomp   pinned engine (mstan, feature/segacd-backend @ a5d5007)
  └─ external/m68k-recomp-core, external/z80-recomp-core  (pinned by the engine)
external/z80-frontend        pinned SmsRecomp Z80 frontend (smsggrecomp @ 224d5bb)
patches/segagenesisrecomp    local engine fixes, applied to the pinned submodule
tools/                       Snatcher-owned tooling (disc reader, locators, viewers)
docs/                        program inventory and bring-up findings
work/, build/, Rom/          private, ignored: owned inputs and everything derived
```

## Bring-up so far

Requirements: Git, Python 3.10+, and MSYS2 MinGW-w64 (`gcc`, `cmake`, `ninja`,
`SDL2`) on Windows. Keep `build/` and `work/` off `C:`; the engine tools refuse
generated data there.

```sh
git clone --recursive https://github.com/crusader290/Snatcher.git
cd Snatcher
git -C external/segagenesisrecomp submodule update --init external/m68k-recomp-core external/z80-recomp-core
python tools/apply_patches.py
```

Inspect and convert your disc. If your CUE's `FILE` line omits the `.bin`
extension, write a corrected copy of the CUE beside the BIN first:

```sh
python tools/disc.py "Rom/Snatcher (Sega CD).cue" --extract work/extract
python external/segagenesisrecomp/tools/segacd/disc_image.py "Rom/Snatcher (Sega CD).cue" work/snatcher.sgcd
```

Build the engine's generator and discovery probe:

```sh
cmake -S external/segagenesisrecomp/tests/segacd -B build/tools -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/tools --target segacd_module_recompiler segacd_bios_floor_probe
```

Run the probe for about 70 seconds of machine time, with an 8 KiB blank
(`0xFF`-filled) backup RAM image:

```sh
SEGACD_PROBE_PC_ROOTS=1 SEGACD_PROBE_BRAM_IMAGE=work/probe/blank-bram.bin \
  build/tools/segacd_bios_floor_probe BIOS.bin 875000000 work/probe/run work/snatcher.sgcd
python tools/ppm2png.py work/probe/run/*.ppm
python tools/locate_files.py work/extract work/probe/run > work/located.json
```

## Roadmap

1. ~~Disc inventory, engine pin, MinGW build, boot unblocked~~
2. Snatcher recipe: BIOS, IP, SP, SUBCODE and the 53 `DATA_*` sub overlays,
   plus Z80 sound driver captures → guarded native catalogs
3. `Snatcher` runtime target (strict native, no interpreter fallback)
4. Playthrough coverage: boot → title → first save/load → chapter transitions
5. Packaging and release notes

## Credits

- **Matthew Stanley ([mstan](https://github.com/mstan))**: the
  [segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) Sega CD
  backend, [m68k-recomp-core](https://github.com/mstan/m68k-recomp-core),
  [z80-recomp-core](https://github.com/mstan/z80-recomp-core),
  [smsggrecomp](https://github.com/mstan/smsggrecomp) and the reference
  integration [SonicCDRecomp](https://github.com/mstan/SonicCDRecomp), which
  this project follows.
- **ares team / Near and contributors**: Sega CD device algorithms adapted by
  the engine (ISC).
- **ymfm** by Aaron Giles (BSD-3-Clause), **SDL2** (zlib).

## Licensing

The engine, CPU cores and frontend are submodules under their own licenses,
mostly PolyForm Noncommercial 1.0.0. The files under `patches/segagenesisrecomp`
modify that engine and therefore fall under its terms. Snatcher and its assets
belong to Konami; this is an unofficial, noncommercial fan project and grants
no rights to the game, its BIOS or any trademarks.
