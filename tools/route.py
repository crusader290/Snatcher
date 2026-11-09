#!/usr/bin/env python3
"""Compile a Snatcher menu route into a segarecomp input script.

A route file holds one step per line (# starts a comment):

  at FRAME:DUR:BUTTONS            absolute press (prefix steps, e.g. the title menu)
  every START:END:STEP:DUR:BUTTONS absolute repeated tap
  clock FRAME                     set the running clock (frame the next menu is ready)
  nav KEY...                      cursor moves, NAV_GAP frames apart
  sel                             press C on the highlighted item, then wait SEL_WAIT
  text N                          N C taps, TEXT_GAP apart (one per text page), then wait TEXT_GAP
  wait N                          advance the clock N frames
  measure N                       N taps like `text`, and print a capture onset just before each tap

The game only advances text on C, and C on a menu reselects the highlighted item, so every action needs
its exact page count: `measure` with --capture-onset finds it (canon_sheet.py tiles the frames).

usage: route.py ROUTE OUT.txt   -> prints the end frame and the measure onsets
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

NAV_GAP, NAV_DUR = 40, 3
SEL_WAIT, TAP_DUR = 160, 4
TEXT_GAP = 220


def compile_route(lines):
    presses, onsets, clock = [], [], 0
    for raw in lines:
        line = raw.split("#", 1)[0].split()
        if not line:
            continue
        op, args = line[0], line[1:]
        if op == "at":
            presses.append(args[0])
        elif op == "every":
            presses.append("every:" + args[0])
        elif op == "clock":
            clock = int(args[0])
        elif op == "nav":
            for key in args:
                presses.append(f"{clock}:{NAV_DUR}:{key}")
                clock += NAV_GAP
        elif op == "sel":
            presses.append(f"{clock}:{TAP_DUR}:C")
            clock += SEL_WAIT
        elif op in ("text", "measure"):
            for _ in range(int(args[0])):
                clock += TEXT_GAP
                if op == "measure":
                    onsets.append(clock - 5)
                presses.append(f"{clock}:{TAP_DUR}:C")
            clock += TEXT_GAP
        elif op == "wait":
            clock += int(args[0])
        else:
            raise SystemExit(f"unknown step: {raw.strip()}")
    return presses, onsets, clock


def main() -> int:
    src, out = sys.argv[1], sys.argv[2]
    presses, onsets, clock = compile_route(Path(src).read_text().splitlines())
    import make_input_script
    sys.argv = ["make_input_script.py", out, *presses]
    rc = make_input_script.main()
    print(f"end {clock}")
    if onsets:
        print("onsets " + " ".join(map(str, onsets)))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
