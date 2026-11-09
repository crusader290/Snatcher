#!/usr/bin/env python3
"""Write a segarecomp Sega CD input script from frame-based button presses.

Each argument is FRAME:DURATION:BUTTONS (BUTTONS = comma list of UP DOWN LEFT RIGHT A B C START), or
`every:START:END:STEP:DURATION:BUTTONS` for a repeated tap. Frames are NTSC vertical periods since reset
(262 lines x 3420 master clocks; segarecomp counts 500,000 ticks per master clock).

usage: make_input_script.py OUT.txt 3100:8:START every:3300:9000:90:6:A
"""
import sys

TICKS_PER_FRAME = 262 * 3420 * 500_000


def parse(args):
    presses = []
    for a in args:
        f = a.split(":")
        if f[0] == "every":
            start, end, step, dur = map(int, f[1:5])
            presses += [(fr, dur, f[5]) for fr in range(start, end, step)]
        else:
            presses.append((int(f[0]), int(f[1]), f[2]))
    return presses


def main() -> int:
    out, presses = sys.argv[1], parse(sys.argv[2:])
    events = []
    for frame, dur, buttons in presses:
        events.append((frame * TICKS_PER_FRAME, 0, "press", buttons))
        events.append(((frame + dur) * TICKS_PER_FRAME, 1, "release", buttons))
    events.sort(key=lambda e: (e[0], e[1]))
    held, lines = set(), ["segarecomp-input-script 1"]
    for tick, _, kind, buttons in events:
        names = [b for b in buttons.split(",") if (b not in held) == (kind == "press")]
        if not names:
            continue  # overlapping taps of the same button: keep the script well-formed
        held.update(names) if kind == "press" else held.difference_update(names)
        lines.append(f"{tick} 1 {kind} {','.join(names)}")
    text = "\n".join(lines) + "\n"
    # segarecomp refuses a script over SCD_INPUT_MAX_SCRIPT_BYTES (65536) or SCD_INPUT_MAX_EVENTS (4096) as "too_large".
    if len(text) > 65536 or len(lines) - 1 > 4096:
        print(f"{out}: {len(lines) - 1} transitions / {len(text)} bytes exceeds segarecomp's 4096 events / 64 KiB", file=sys.stderr)
        return 1
    open(out, "w", newline="\n").write(text)
    print(f"{out}: {len(lines) - 1} transitions, {len(text)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
