#!/usr/bin/env python3
"""Run the recompiled Snatcher under a watchdog and log every session, crash, typed stop and hang to Snatcher.log.

  watchdog.py [options] -- PROGRAM [ARGS...]
  watchdog.py --plain [options] -- COMMAND [ARGS...]   any command (build.bat wraps segarecomp with it): no
                                                       --report, exit 0 is success and anything else an error
  watchdog.py --note LEVEL MESSAGE                     append one line to the log

The program runs with `--report` pointed at the incident folder, so its exit report (result, typed stop class,
CPU and PC, both CPUs' registers, Gate Array state) is kept. Its stderr is copied into the log as it arrives.

What it watches for:
  crash       the process ends with a Windows exception code (access violation, stack overflow, ...)
  stop        exit 10: generated code reached something the build did not compile (a typed stop)
  error       any other non-zero exit (disc or backup RAM refused, SDL host failure, ...)
  hang        the window stops responding (Windows' "Not Responding") for --hang-seconds; a minidump is written,
              and the process is ended if it stays hung for --kill-seconds

Every problem gets a folder work/logs/<time>-<kind>/ with report.json, stderr.txt, the minidump (hangs) and the
recorded input (--record). Snatcher.log names the folder. With --record the session's pad input is recorded with
the viewer's --record-input so a break can be replayed headlessly with program.exe --input-script; segarecomp ends
a recording session at 4,096 input events, so it is opt-in.

Options: --log FILE (default Snatcher.log)  --logs-dir DIR (default work/logs)  --hang-seconds N (default 20)
         --kill-seconds N (default 300, 0 = never)  --record  --max-log-bytes N (default 5 MiB; rotates to .1)
"""
import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

EXIT_CODES = {
    0: ("info", "quit"),
    2: ("error", "usage error (bad arguments)"),
    10: ("stop", "typed stop: the game reached code or a device case this build does not cover"),
    11: ("error", "instruction budget or deadline reached"),
    20: ("error", "disc refused at start-up (wrong or changed disc files)"),
    22: ("error", "backup RAM image refused"),
    23: ("error", "input script refused"),
    24: ("error", "host failure (SDL window, audio or input)"),
    25: ("info", "input recording reached its 4,096-event limit; the recorded prefix was kept"),
    26: ("error", "input recorder refused"),
    27: ("error", "input recording could not be written"),
    28: ("error", "backup RAM output could not be written"),
}
NTSTATUS = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000025: "NONCONTINUABLE_EXCEPTION",
    0xC000008C: "ARRAY_BOUNDS_EXCEEDED",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000095: "INTEGER_OVERFLOW",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000135: "DLL_NOT_FOUND (is SDL3.dll beside the program?)",
    0xC0000139: "ENTRYPOINT_NOT_FOUND (mismatched DLL)",
    0xC0000142: "DLL_INIT_FAILED",
    0xC0000409: "STACK_BUFFER_OVERRUN / fail-fast (abort)",
    0xC0000417: "INVALID_CRUNTIME_PARAMETER",
    0x40000015: "FATAL_APP_EXIT (abort)",
    0x80000003: "BREAKPOINT",
}
EXTERNAL = {
    0xFFFFFFFF: "ended from outside (Task Manager or a kill)",
    0xC000013A: "ended by Ctrl+C or by closing the console window",
}


class Log:
    def __init__(self, path: Path, max_bytes: int):
        self.path, self.lock = path, threading.Lock()
        if path.exists() and path.stat().st_size > max_bytes:
            path.replace(path.with_name(path.name + ".1"))

    def write(self, level: str, message: str) -> None:
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = message.rstrip("\n").splitlines() or [""]
        text = "".join(f"{stamp} [{level.upper():5}] {line}\n" for line in lines)
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(text)
            sys.stdout.write(text)
            sys.stdout.flush()


# --- Windows: hang detection and minidumps -------------------------------------------------------------------------

def _user32():
    if os.name != "nt":
        return None
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.IsHungAppWindow.argtypes = [ctypes.c_void_p]
    u.IsWindowVisible.argtypes = [ctypes.c_void_p]
    u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    return u


USER32 = _user32()
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p) if os.name == "nt" else None


def process_windows(pid: int):
    found = []
    if USER32 is None:
        return found

    def visit(hwnd, _):
        owner = ctypes.c_ulong()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and USER32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    USER32.EnumWindows(WNDENUMPROC(visit), None)
    return found


def is_hung(pid: int) -> bool:
    windows = process_windows(pid)
    return bool(windows) and all(USER32.IsHungAppWindow(w) for w in windows)


def write_minidump(proc: subprocess.Popen, path: Path) -> str:
    if os.name != "nt":
        return "minidumps need Windows"
    import msvcrt
    dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)
    dbghelp.MiniDumpWriteDump.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # MiniDumpWithDataSegs | MiniDumpWithHandleData | MiniDumpWithIndirectlyReferencedMemory | MiniDumpWithThreadInfo
    dump_type = 0x0001 | 0x0004 | 0x0040 | 0x1000
    with open(path, "wb") as f:
        ok = dbghelp.MiniDumpWriteDump(int(proc._handle), proc.pid, msvcrt.get_osfhandle(f.fileno()), dump_type,
                                       None, None, None)
    if not ok:
        return f"MiniDumpWriteDump failed (error {ctypes.get_last_error()})"
    return f"minidump {path.name} written ({path.stat().st_size // 1024} KiB, in the incident folder)"


# --- session -----------------------------------------------------------------------------------------------------

def describe_program(exe: Path) -> str:
    try:
        digest = hashlib.sha256(exe.read_bytes()).hexdigest()[:16]
        built = dt.datetime.fromtimestamp(exe.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"{exe} (sha256 {digest}..., built {built})"
    except OSError as e:
        return f"{exe} (unreadable: {e})"


def git_head(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "describe", "--always", "--dirty"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def summarize_report(path: Path) -> list:
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lines = [f"result {r.get('result')}"]
    stop = r.get("stop") or {}
    if stop.get("class") not in (None, "none"):
        cpu = "main" if stop.get("cpu") == 0 else "sub"
        where = f"{cpu} CPU at PC ${stop.get('pc', 0):06X}"
        if stop.get("address") or stop.get("width"):
            where += f", {'write' if stop.get('write') else 'access'} ${stop.get('address', 0):06X}/{stop.get('width')}"
        lines.append(f"stop {stop.get('class')}: {where}, tick {stop.get('tick')}")
    for i, c in enumerate(r.get("cpus") or []):
        lines.append(f"{'main' if i == 0 else 'sub '} pc=${c.get('pc', 0):06X} sr=${c.get('sr', 0):04X} "
                     f"retired={c.get('retired')} stopped={c.get('stopped')}")
    live = r.get("live")
    if isinstance(live, dict):
        lines.append(f"live outcome {live.get('outcome')}, frames {live.get('frames')}, presented {live.get('presented')}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default="Snatcher.log")
    ap.add_argument("--logs-dir", default="work/logs")
    ap.add_argument("--hang-seconds", type=float, default=20.0)
    ap.add_argument("--kill-seconds", type=float, default=300.0)
    ap.add_argument("--max-log-bytes", type=int, default=5 * 1024 * 1024)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--label", default="session")
    ap.add_argument("--note", nargs=2, metavar=("LEVEL", "MESSAGE"))
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.note:
        Log(Path(a.log), a.max_log_bytes).write(a.note[0], a.note[1])
        return 0
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("missing program to run (after --)")

    log = Log(Path(a.log), a.max_log_bytes)
    logs_dir = Path(a.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    session = logs_dir / f"{a.label}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    session.mkdir()
    report, stderr_path, record_path = session / "report.json", session / "stderr.txt", session / "input.txt"
    full = list(cmd)
    if not a.plain:
        full += ["--report", str(report)] + (["--record-input", str(record_path)] if a.record else [])

    exe = Path(cmd[0])
    log.write("info", f"{a.label} start: " + describe_program(exe))
    log.write("info", f"repo {git_head(Path(__file__).resolve().parent.parent)}, watchdog pid {os.getpid()}, "
                      f"hang after {a.hang_seconds:g} s, kill after {a.kill_seconds:g} s"
                      + (", recording input" if a.record else ""))
    log.write("info", "command: " + subprocess.list2cmdline(full))

    start = time.monotonic()
    try:
        proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        log.write("error", f"could not start the program: {e}")
        return 1

    tail = []

    def pump(stream, name):
        with open(stderr_path, "a", encoding="utf-8", errors="replace") as keep:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                keep.write(f"{name}: {line}\n")
                tail.append(line)
                del tail[:-200]
                log.write("prog", f"{name}: {line}")

    threads = [threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True)]
    for t in threads:
        t.start()

    hung_since, dumped, killed = None, False, False
    while proc.poll() is None:
        time.sleep(1.0)
        if proc.poll() is not None:
            break
        if is_hung(proc.pid):
            hung_since = hung_since or time.monotonic()
            hung_for = time.monotonic() - hung_since
            if hung_for >= a.hang_seconds and not dumped:
                dumped = True
                log.write("hang", f"window not responding for {hung_for:.0f} s at "
                                  f"{elapsed(start)} into the session")
                log.write("hang", write_minidump(proc, session / "hang.dmp"))
            if a.kill_seconds > 0 and hung_for >= a.kill_seconds:
                log.write("hang", f"still not responding after {hung_for:.0f} s; ending the process")
                proc.kill()
                killed = True
                break
        elif hung_since is not None:
            log.write("hang" if dumped else "info",
                      f"window responding again after {time.monotonic() - hung_since:.0f} s")
            hung_since = None
    code = proc.wait()
    for t in threads:
        t.join(timeout=5)
    ucode = code & 0xFFFFFFFF

    if a.plain and not killed and ucode < 0x40000000:
        kind, what = ("info", "exit 0: success") if code == 0 else ("error", f"exit {code}: failed")
    elif killed:
        kind, what = "hang", "ended by the watchdog after hanging"
    elif ucode in EXTERNAL:
        kind, what = "error", f"0x{ucode:08X}: {EXTERNAL[ucode]}"
    elif ucode >= 0x40000000 and ucode not in EXIT_CODES:
        kind, what = "crash", f"crashed with 0x{ucode:08X} {NTSTATUS.get(ucode, 'unknown exception')}"
    else:
        kind, what = EXIT_CODES.get(code, ("error", "unexpected exit code"))
        what = f"exit {code}: {what}"
    log.write(kind, f"{a.label} end after {elapsed(start)}: {what}")
    for line in summarize_report(report):
        log.write(kind, "  " + line)

    if kind == "info" and not dumped and not (a.record and record_path.exists()):
        shutil.rmtree(session, ignore_errors=True)  # clean sessions leave only their log lines
        return code
    incident = session.with_name(session.name.replace(a.label, f"{a.label}-{kind}", 1))
    session.rename(incident)
    if kind in ("crash", "error", "hang") and tail:
        log.write(kind, "  last program output:")
        for line in tail[-15:]:
            log.write(kind, "    " + line)
    log.write(kind, f"  incident files: {incident}")
    if record_path.exists():
        log.write(kind, f"  replay headlessly: program.exe --disc-dir DISC --bios BIOS --backup-ram BRAM "
                        f"--input-script {incident / 'input.txt'} --instruction-budget N")
    return 3 if kind == "crash" else code


def elapsed(start: float) -> str:
    s = int(time.monotonic() - start)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
