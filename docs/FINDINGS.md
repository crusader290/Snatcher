# Bring-up findings

## 1. Boot hang: VINT asserted at the same instant as the VBLANK flag

**Symptom.** With the qualified v1.10 BIOS, the probe showed the BIOS screens
and the disc's licence screen, then a black screen forever. Only about 226
sectors were read in 70 s of machine time and no CDDA played.

**Diagnosis**, from the probe trace (`SEGACD_PROBE_TRACE_MODE=1`):

- The Main vertical-interrupt handler (IP, entry `FF06C8`) runs the game's frame
  logic, guarded by a busy byte at `FFE028`. While that logic is in progress,
  each later VINT only bumps a comm counter, raises Sub INT2 and returns.
- The interrupted frame logic polls `btst #3,$C00005` / `beq` at `FF2D34`,
  waiting for the VDP VBLANK status bit.
- The engine set the VBLANK flag and raised IRQ6 at the same host event.
  The nested handler is taken before the next poll and outlasts the blanking
  period, so the poll never observes bit 3 set.
- The frame logic therefore never completes and Main never re-requests
  Word RAM (DMNA). The Sub CPU, inside its INT2 handler at `D648` with SR mask
  level 2, waits forever for DMNA.

**Fix**
([patches/segagenesisrecomp/0001](../patches/segagenesisrecomp/0001-delay-vint-after-vblank-flag.patch)).
The VDP raises VBLANK at the start of line 224 and asserts the level-6
interrupt 788 master clocks later, about 112 main-CPU cycles. This window is
what lets original polling loops see the flag. The Z80 interrupt keeps its
previous timing. The same model is in the diagnostic probe (patch 0002).

**Result.** The probe proceeds through the intro: 1,823 sectors read and 719
CDDA sectors played in the same window. No game-specific code was added.

The fix uses 788 master clocks in H40 and 770 in H32, selected from VDP
register 12. segarecomp's VDP model (`SCD_VINT_H40_MCLK` / `SCD_VINT_H32_MCLK`)
uses the same values independently.

## 2. Program inventory

See [PROGRAM_INVENTORY.md](PROGRAM_INVENTORY.md).

## 3. segarecomp self-service build of Snatcher

[segarecomp](https://github.com/marinocg/segarecomp) (`external/segarecomp`)
builds with MSYS2 MinGW after
[patch 0001](../patches/segarecomp/0001-mingw-gnu-ld-stack-reservation.patch):
GNU ld spells the 8 MiB stack reservation `--stack`, not `/STACK:`.

| Build | Stop | What it showed |
|---|---|---|
| no backup RAM | `backup_ram_unsupported` (sub) | segarecomp requires a backup RAM image; any access without one is a typed stop |
| `--backup-ram` blank (`0xFF`) | `cdc_destination_unsupported` (sub `$7598`, destination 5) | the boot `SP` loads `SUBCODE.BIN` to PRG RAM `$D400` by CDC DMA, which segarecomp did not implement |
| + [patch 0002](../patches/segarecomp/0002-cdc-dma-to-prg-and-pcm-ram.patch) (CDC DMA to PRG and PCM RAM) | `entry_not_compiled` (main `$FFE100` → `$FFE290`) | `SUBCODE` is now admitted from the disc (sub `$CC00`–`$1A3FF`) and runs native |
| + SP-tail extent, developer driver (no main Z80) | `main_device_unsupported` (main `$FF5832` reads `$A04000`) | 27 M instructions; Snatcher's main CPU reads the YM2612 status port directly, which needs segarecomp's attached Z80 and FM devices |
| + self-service build, main Z80 + YM2612/PSG, SDL3 viewer | `entry_not_compiled` (sub `$E16E` → `$285CE`) | 56.7 M instructions and a playable `program-viewer`; the next frontier is the `DATA_*` overlays at `$28000` |

Patch 0002 gives destinations 5 (PRG RAM, register × 8, honours write protect,
notes overlay writes) and 4 (PCM wave bank, register × 4, low byte at even
address) writers on segarecomp's existing DMA timing and transfer-end
interrupt. The address semantics match the engine's ares-derived `dma.c`.

The main-CPU stop is code copied from the tail of the system-area `SP`, disc
user-data offsets `$7B00`–`$7FFF`, into main RAM `$FFE100`–`$FFE5FF` through
Word RAM (`$37800`). Extent discovery does not trace that indirect path, so the
span is admitted explicitly with `--disc-image main:31488:16769280:1280`.

### Toolchain notes

- Build segarecomp and the generated programs with MSYS2 **UCRT64**
  (`C:/msys64/ucrt64/bin/gcc.exe`). The mingw64 (msvcrt) C runtime lacks
  C11 `timespec_get`, which the viewer uses. Do not mix a mingw64-built
  segarecomp CLI with UCRT64 DLLs on PATH; it fails to start (exit 127).
- SDL3 for the viewer: `pacman -S mingw-w64-ucrt-x86_64-sdl3`, then
  `--viewer 1 --sdl3-include C:/msys64/ucrt64/include --sdl3-lib C:/msys64/ucrt64/lib`.
- GCC links need `--link-arg -Wl,--stack,8388608`
  ([patch 0003](../patches/segarecomp/0003-mingw-gcc-program-builds.patch)
  limits the MSVC-only `#pragma comment` to MSVC/clang and adds the flag to
  the developer driver).
- Admit the SP-tail main code with
  `--emit-arg --disc-image --emit-arg main:31488:16769280:1280`.

Current command (`work/` holds owned inputs and outputs, never committed):

```sh
segarecomp sega-cd build --cue "Rom/Snatcher (Sega CD).fixed.cue" --bios <bios>   --output work/scd-build --runtime-dir external/segarecomp   --cc C:/msys64/ucrt64/bin/gcc.exe --cxx C:/msys64/ucrt64/bin/g++.exe   --cache-dir work/scd-cache-ucrt --jobs 8 --backup-ram work/probe/blank-bram.bin   --budget 400000000 --link-arg -Wl,--stack,8388608   --emit-arg --disc-image --emit-arg main:31488:16769280:1280   --viewer 1 --sdl3-include C:/msys64/ucrt64/include --sdl3-lib C:/msys64/ucrt64/lib
```
