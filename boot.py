"""Boot sequence.

Every line on screen reflects a check that actually ran. Nothing here is a
decorative progress bar — if a subsystem is down, the boot says so and the
colour changes. Press any key to skip the animation; `--fast` skips it always.
"""
import os
import select
import shutil
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path

import config

ESC = "\033["
HIDE, SHOW = f"{ESC}?25l", f"{ESC}?25h"
CLEAR = f"{ESC}2J{ESC}H"

CY = "\033[38;5;51m"    # arc-reactor cyan
CY_D = "\033[38;5;31m"
GD = "\033[38;5;220m"
GN = "\033[38;5;42m"
RD = "\033[38;5;203m"
DM = "\033[2m"
BD = "\033[1m"
R = "\033[0m"

LOGO = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""

SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Skip:
    """Any keypress aborts the animation; the checks still run."""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.ok = sys.stdin.isatty()
        self.old = None

    def __enter__(self):
        if self.ok:
            self.old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def pressed(self):
        if not self.ok:
            return False
        return bool(select.select([sys.stdin], [], [], 0)[0]) and bool(sys.stdin.read(1))

    def __exit__(self, *a):
        if self.ok and self.old:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


def _w():
    return shutil.get_terminal_size((80, 24)).columns


def _center(s, width=None):
    return s.center(width or _w())


def reveal_logo(skip, delay=0.012):
    """Wipe the logo in left-to-right with a bright leading edge."""
    lines = [l for l in LOGO.split("\n") if l.strip()]
    pad = max(0, (_w() - max(len(l) for l in lines)) // 2)
    width = max(len(l) for l in lines)
    print()
    base = len(lines)
    for col in range(width + 2):
        out = []
        for l in lines:
            shown = l[:col]
            edge = l[col:col + 1]
            out.append(" " * pad + CY_D + shown + R + (BD + CY + edge + R if edge.strip() else edge))
        sys.stdout.write("\n".join(out) + f"{ESC}{base - 1}A\r")
        sys.stdout.flush()
        if skip.pressed():
            delay = 0
        if delay:
            time.sleep(delay)
    # settle on the final frame, full brightness
    print("\n".join(" " * pad + CY + l + R for l in lines))


def reactor(skip, cycles=2):
    """A small arc-reactor pulse under the logo."""
    frames = ["·", "○", "◎", "◉", "◎", "○"]
    for i in range(cycles * len(frames)):
        f = frames[i % len(frames)]
        col = CY if i % len(frames) in (2, 3) else CY_D
        sys.stdout.write("\r" + _center(f"{col}{f}{R}") + "\r")
        sys.stdout.flush()
        if skip.pressed():
            break
        time.sleep(0.055)
    sys.stdout.write("\r" + " " * _w() + "\r")


# ---- real checks -------------------------------------------------------

def check_gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6)
        if out.returncode != 0:
            return False, "no NVIDIA GPU"
        name, total, used = [x.strip() for x in out.stdout.strip().split("\n")[0].split(",")]
        return True, f"{name}  {int(total)-int(used)}/{total} MB free"
    except Exception:
        return False, "nvidia-smi unavailable"


def check_ollama():
    try:
        import httpx
        r = httpx.get(f"{config.OLLAMA}/api/tags", timeout=4)
        models = [m["name"] for m in r.json().get("models", [])]
        return True, f"{len(models)} model(s) available"
    except Exception:
        return False, "not running — start with: ollama serve"


def check_model():
    try:
        import httpx
        r = httpx.get(f"{config.OLLAMA}/api/tags", timeout=4)
        names = [m["name"] for m in r.json().get("models", [])]
        if any(n.startswith(config.TEXT_MODEL.split(":")[0]) and config.TEXT_MODEL in n
               for n in names):
            return True, f"{config.TEXT_MODEL} ready"
        return False, f"{config.TEXT_MODEL} not pulled"
    except Exception:
        return False, "unreachable"


def check_whisper():
    try:
        import faster_whisper  # noqa: F401
        return True, f"{config.WHISPER_MODEL} (loads on first /v)"
    except ImportError:
        return False, "faster-whisper not installed"


def check_mic():
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5)
        if "card" not in out.stdout:
            return False, "no capture device"
        first = [l for l in out.stdout.splitlines() if l.startswith("card")][0]
        return True, first.split(":")[1].split("[")[0].strip() if ":" in first else "ready"
    except Exception:
        return False, "arecord unavailable"


def check_vault():
    try:
        import vault
        vs = vault.list_vaults()
        if not vs:
            return False, "no Obsidian vault found"
        root = Path(config.vault_path() or vs[0]["path"])
        st = vault.stats(root)
        return True, f"{st['name']} — {st['notes']} notes"
    except Exception as e:
        return False, f"error: {e}"


def check_tasks():
    try:
        import tasks
        items = tasks.list_day()
        done = sum(1 for t in items if t["done"])
        if not items:
            return True, "none set for today"
        return True, f"{done}/{len(items)} done today"
    except Exception:
        return False, "task file unreadable"


def check_gemini():
    # Local only — presence of a key, no network call, so boot stays fast/offline.
    try:
        return (True, "key set — /g ready") if config.gemini_key() \
            else (True, "no key (optional) — /g disabled")
    except Exception:
        return True, "optional"


def check_mail():
    # Local presence check only — no IMAP login on boot.
    try:
        import mail
        return (True, "read-only, /mail ready") if mail.configured() \
            else (True, "not set up (optional)")
    except Exception:
        return True, "optional"


def check_study():
    try:
        import study
        d = len(study.due())
        st = study.stats()
        if st["total"] == 0:
            return True, "no cards yet"
        return True, (f"{d} due" if d else "all reviewed") + f" · {st['total']} total"
    except Exception:
        return True, "—"


CHECKS = [
    ("GPU", check_gpu),
    ("OLLAMA", check_ollama),
    ("MODEL", check_model),
    ("SPEECH", check_whisper),
    ("MIC", check_mic),
    ("VAULT", check_vault),
    ("GEMINI", check_gemini),
    ("MAIL", check_mail),
    ("STUDY", check_study),
    ("TASKS", check_tasks),
]


def run_checks(skip, animate=True):
    """Spinner runs while the check genuinely executes."""
    results = {}
    pad = max(0, (_w() - 54) // 2)
    for label, fn in CHECKS:
        line = f"{' ' * pad}{DM}[{R}{CY}%s{R}{DM}]{R} {BD}{label:<7}{R} "
        if animate and not skip.pressed():
            sys.stdout.write(line % SPIN[0])
            sys.stdout.flush()
        t0 = time.time()
        ok, detail = fn()
        el = time.time() - t0
        # spin for whatever the check didn't take, so fast checks still read
        if animate and not skip.pressed():
            i = 0
            while time.time() - t0 < min(0.34, max(0.1, el)):
                sys.stdout.write("\r" + line % SPIN[i % len(SPIN)])
                sys.stdout.flush()
                i += 1
                time.sleep(0.05)
        mark = f"{GN}✓{R}" if ok else f"{RD}✗{R}"
        col = DM if ok else RD
        sys.stdout.write(
            f"\r{' ' * pad}{DM}[{R}{mark}{DM}]{R} {BD}{label:<7}{R} {col}{detail}{R}"
            + " " * 8 + "\n")
        sys.stdout.flush()
        results[label] = ok
    return results


def boot(fast=False):
    animate = not fast and sys.stdout.isatty()
    with Skip() as skip:
        try:
            if animate:
                sys.stdout.write(HIDE + CLEAR)  # cursor restored in finally
                reveal_logo(skip)
                print(_center(f"{DM}local · offline · yours{R}") + "\n")
                reactor(skip)
            else:
                print(f"\n{CY}JARVIS{R} {DM}· local · offline{R}\n")
            results = run_checks(skip, animate)
        finally:
            if animate:            # only restore what we actually hid
                sys.stdout.write(SHOW)
    print()
    return results
