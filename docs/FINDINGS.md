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
segarecomp sega-cd build --cue "Rom/Snatcher (Sega CD).fixed.cue" --bios <bios> \
  --output work/scd-build --runtime-dir external/segarecomp \
  --cc C:/msys64/ucrt64/bin/gcc.exe --cxx C:/msys64/ucrt64/bin/g++.exe \
  --cache-dir work/scd-cache-ucrt --jobs 8 --backup-ram work/probe/blank-bram.bin \
  --budget 400000000 --link-arg -Wl,--stack,8388608 \
  --emit-arg --disc-image --emit-arg main:31488:16769280:1280 \
  --viewer 1 --sdl3-include C:/msys64/ucrt64/include --sdl3-lib C:/msys64/ucrt64/lib
```

## 4. A formatted backup RAM image, made by the BIOS

With the `0xFF` image, the file-first build runs its whole 400 M-instruction
budget with no typed stop: the Konami logo renders natively at about 30 s.
At about 60 s Snatcher shows its "initialise the memory first" screen, because
the internal backup RAM is unformatted. segarecomp expects a *formatted* empty
image, so the BIOS formats one in the diagnostic probe (no disc mounted, from
the blank image). The pad script drives the v1.10 control panel:
panel → Down → Right (OPTION) → C → any button → Up (FORMAT, built-in) → C →
Left (YES) → C.

```sh
SEGACD_PROBE_BRAM_IMAGE=work/probe/blank-bram.bin SEGACD_PROBE_PAD_EVENTS_OVERRIDE_START=1 \
SEGACD_PROBE_PAD_EVENTS="1400:2:0x20,1500:2:0x2,1540:2:0x8,1580:2:0x20,1700:2:0x20,1800:2:0x1,1840:2:0x20,1900:2:0x4,1940:2:0x20" \
  build/tools/segacd_bios_floor_probe <bios> 460000000 work/probe/bram-format
cp work/probe/bram-format/backup-ram.bin work/probe/formatted-bram.bin
```

Only the 64-byte directory header at the end of RAM changes; it ends in
`SEGA_CD_ROM` … `RAM_CARTRIDGE___`. Pass the result as `--backup-ram`. Like
every BIOS-derived file, it stays in ignored local storage.

`tools/canon2png.py` converts segarecomp's `--capture-dir` frames
(`canon_<onset>.bin`) to PNG for checking.

## 5. Title screen, input scripts and the one-word Word RAM DMA

With the BIOS-formatted backup RAM, the file-first build boots natively through
the Konami logo to Snatcher's title screen (NEW GAME menu, about 50 s) and
waits there for input.

`tools/make_input_script.py` writes segarecomp input scripts from frame-based
presses. One NTSC frame is 262 × 3420 master clocks × 500,000 ticks. Example:
`make_input_script.py work/input-title.txt 3100:8:START every:3300:12000:90:6:A`
presses Start on the title, then taps A every 90 frames.

Pressing Start stopped the game with `vdp_dma_unsupported` (main `$FF1AB6`): a
VDP DMA of length 1 from 2M Word RAM `$23A002`, owned by main. The Word RAM
source arrives one bus cycle late, so a one-word transfer leaves only the stale
bus word, which is not written. The destination advances by the
auto-increment and the transfer ends.
[Patch 0004](../patches/segarecomp/0004-vdp-dma-single-word-from-word-ram.patch)
models exactly that, in the 2M and 1M branches. It sets the length counter to 0,
moves the source one word, rewrites the command address and clears the
command's DMA bit, so the VDP only latches the address. Subtracting one would
be wrong: a length of 0 means 65,536 words on this VDP.

### Getting from the title into a new game

On the title (about frame 3000) neither A nor C starts a game, and Start
opens OPTIONS. Inside OPTIONS, Down moves the cursor. GUN ADJUST is skipped
with "joypad only", so QUIT is three Downs away, and C on QUIT starts a new
game; the opening disclaimer appears at about frame 4300. The pad model is
fine: Start and A, and C and the directions, each work in their own read phase.

```sh
python tools/make_input_script.py work/input-story.txt \
  3400:3:START 3600:3:DOWN 3640:3:DOWN 3680:3:DOWN 3800:3:C every:4400:60000:90:6:C
```

The trailing C taps advance the opening text so a build pass covers the first
chapter's code.

### Word RAM DMA ending exactly at the window edge

Following that route, the build ran 870 M instructions and bound three
`DATA_*` scene overlays at `$28000` before the same DMA routine
(`$FF1AB6`) stopped. It was a 16-word transfer from `$23FFE2` in 2M mode,
owned by main. segarecomp bounded the range by the full length
(`$240002`), but with the one-cycle source delay the last source word is
never fetched, so the transfer reads only `$23FFE2`–`$23FFFF`.
[Patch 0005](../patches/segarecomp/0005-vdp-dma-word-ram-bound-on-read-words.patch)
bounds the 2M branch by the words actually read. A transfer that truly
crosses the window still stops.

## 6. Through the intro to the first scene

segarecomp refuses an input script over 64 KiB or 4,096 events as
`input_refused too_large` before the first pass; `make_input_script.py` now
checks both limits when it writes. C taps every 120 frames fit:

```sh
python tools/make_input_script.py work/input-story-long.txt   3400:3:START 3600:3:DOWN 3640:3:DOWN 3680:3:DOWN 3800:3:C every:4400:110000:120:6:C
```

With patches 0001 to 0005, the self-service build with `--budget 10000000000`
finishes in six rounds with `budget_exhausted` and no typed stop. File-first
admission binds 87 images (18,362 entry offsets). Replaying the program with
`--capture-onset` (at most eight onsets per run) shows the following:

| Frame | Screen |
|---|---|
| 20,000 | Opening credits over the city |
| 35,000 | Junker HQ lobby: Mika's dialogue in the text window |
| 50,000 to 130,000 | Junker HQ lobby, command menu (ENTER, LOOK, INVESTIGATE, TALK) |

The repeated C taps keep choosing ENTER, which Mika refuses, so the scene
loops. Going further needs a script that moves through the command menu.

## 7. A scripted route through the Junker HQ lobby

The game advances text only on C (A and B do nothing), and C on a menu
reselects the highlighted item. So a blind stream of C taps loops on whatever
the cursor is on. In the lobby that is ENTER, which Mika refuses forever. A
route therefore needs the exact number of text pages for each action.

- `tools/route.py` compiles a route file into an input script. Its steps are
  `nav` (cursor moves), `sel` (C on the item), `text N` (one C per page) and
  `measure N`. `measure N` also prints a capture onset just before each tap.
- A probe replays the built program with `--until-tick` and those onsets. It
  reaches the lobby in about 3 minutes, so several probes run in parallel.
- `tools/canon_sheet.py` tiles the captures into one PNG. The capture just
  before each tap shows whether the game still waits on text or is back at
  the menu.

Menu behaviour that matters for routing:
- The top-level cursor keeps its index, and items can be inserted above it.
- A submenu's cursor starts at the top again.
- The cursor wraps at both ends.

The lobby route
([routes/act1-chief.route](../routes/act1-chief.route)) follows the order
in the [LP Archive walkthrough](https://lparchive.org/Snatcher-(Screenshot)/Update%202/):

| Step | Pages |
|---|---|
| Lobby ENTER (Mika asks for ID; TALK appears) | timed taps |
| Lobby TALK (close-up; menu ready at about frame 35,400) | none |
| ASK about Mika, first time | 4 |
| ASK about Mika, second time | 2 |
| ASK about Junkers (adds ENTER at the top of the close-up menu) | 3 |
| ENTER (Mika opens the doors, then shows the tour menu) | the 6th tap picks CHIEF'S OFFICE |

At about frame 42,000 the Chief's office is on screen. Its menu is EXIT, LOOK,
INVESTIGATE, ASK. With the cursor on EXIT, steady taps make Mika repeat that
the Chief has not finished, so the next stretch needs ASK.

A self-service build along this route (`--budget 10000000000`, input script
from `route.py routes/act1-chief.route`) finished in six rounds (59 minutes)
with `budget_exhausted` and no typed stop. The lobby close-up, the tour and
the Chief's office need no images beyond the 87 that file-first admission
already binds.
