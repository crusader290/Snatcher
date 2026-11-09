# Snatcher (US) program inventory

Addresses and identities only; no game bytes. Derived from `tools/disc.py`,
`tools/locate_files.py` and probe PC roots (`SEGACD_PROBE_PC_ROOTS=1`).

## Disc

- Track 1 MODE1/2352 (LBA 0–56013), tracks 2–21 CD audio.
- System area: volume `SEGAIPMENU`, system `KONAMI R002`, serial `T-95035`.
  IP at disc offset 0x800 (24,576 bytes), SP at 0x6800 (6,144 bytes).
- ISO9660 root: 100 files.

## Executable images

| Image | CPU | Load base | Evidence |
|---|---|---|---|
| BIOS ROM | Main | `000000` | executed `0000`–`8FFF` |
| BIOS-installed RAM stubs/vectors | Main | `FFFD00`… | executed `FFE000`+ |
| IP (security block + main program) | Main | `FF0000` (program at `FF0600`) | byte match, executed `FF0000`–`FF5FFF` |
| Sub BIOS (PRG RAM) | Sub | `000000` | executed `0000`–`5FFF` (probe capture) |
| SP (boot sub program) | Sub | `006000` | executed `6000`–`8FFF` |
| `SUBCODE.BIN` | Sub | `00D400` | full byte match, executed `D000`–`19FFF` |
| `DATA_*.BIN` (53 files) | Sub | `028000` | every header's pointers fall in `028000`+size; executed `28000`–`29FFF` (`DATA_D2`) |
| Z80 sound program | Z80 | `0000` | to be captured from Z80 RAM |

## Data-only files (no 68000 code expected)

| File | Where | Notes |
|---|---|---|
| `SP00`–`SP38.BIN` | — | Scenario script bytecode, not 68000 code |
| `FMWR_1.BIN` | Word RAM `000000` | FM sound data/driver payload, under investigation |
| `PCMLT_01.BIN` | Sub `050000` | PCM table |
| `PCMDRMDT.BIN` | Sub `055000` | PCM drum samples |
| `PCMLD_01.BIN` | streamed | 84 MB PCM/voice stream |
| `ABS.TXT`, `BIB.TXT`, `CPY.TXT` | — | ISO volume text files |

Every `DATA_*` image shares one load base, so native catalogs for them overlap.
The engine's per-PC guards select the overlay currently resident.
