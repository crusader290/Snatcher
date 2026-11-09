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

## 2. Program inventory

See [PROGRAM_INVENTORY.md](PROGRAM_INVENTORY.md).
