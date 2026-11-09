# Snatcher Recompiled (Sega CD) — work in progress

A static recompilation of Konami's **Snatcher** for the Sega CD (US release,
serial `T-95035`) into native C, built on the same reusable Sega CD backend as
[SonicCDRecomp](https://github.com/mstan/SonicCDRecomp).

The original Main 68000, Sub 68000 and Z80 programs are translated ahead of
time into guarded C. The runtime models the Sega CD hardware: buses, Word RAM,
CDC/CDD, PCM, stamp graphics, VDP, FM/PSG audio and backup RAM.

> **Status: first playable scene.** segarecomp's Sega CD pipeline builds
> Snatcher from your BIOS and CUE into a generated-native program with an SDL3
> viewer. Driven by an input script, the program boots through the Konami logo,
> the title and OPTIONS, plays the opening cinematic and credits, and reaches
> the first scene: the Junker HQ lobby with its command menu and dialogue. A
> 10-billion-instruction pass has no typed stop. Details are in
> [docs/FINDINGS.md](docs/FINDINGS.md). The game is not playable end to end yet.

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
external/segarecomp          pinned segarecomp (marinocg @ 8fa9f66): second, generic Sega CD pipeline
patches/<submodule>/         local fixes, applied to the pinned submodules by tools/apply_patches.py
tools/                       Snatcher-owned tooling (disc reader, locators, viewers)
docs/                        program inventory and bring-up findings
work/, build/, Rom/          private, ignored: owned inputs and everything derived
```

## Bring-up so far

Requirements: Git, Python 3.10+, and MSYS2 with the UCRT64 toolchain plus `SDL3`
(mingw64 `cmake`/`ninja` work as build drivers) on Windows. Keep `build/` and `work/` off `C:`; the engine tools refuse
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
- **marinocg**: [segarecomp](https://github.com/marinocg/segarecomp) (MPL-2.0),
  whose generic Sega CD build (extent discovery, file-first AOT) is used as a
  second pipeline and as a cross-check. Its VDP model independently uses the
  same 788/770 master-clock VINT delay this project patched into the engine.
- **ares team / Near and contributors**: Sega CD device algorithms adapted by
  the engine (ISC).
- **ymfm** by Aaron Giles (BSD-3-Clause), **SDL2** (zlib).

## Licensing

The engine, CPU cores and frontend are submodules under their own licenses:
segagenesisrecomp and its cores use PolyForm Noncommercial 1.0.0, and segarecomp
uses MPL-2.0. Each file under `patches/<submodule>` modifies that submodule and
falls under its terms. Snatcher and its assets
belong to Konami; this is an unofficial, noncommercial fan project and grants
no rights to the game, its BIOS or any trademarks.
