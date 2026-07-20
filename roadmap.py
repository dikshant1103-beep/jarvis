"""Reads the Zero → Robot dashboard data so Jarvis knows the real plan.

Read-only. This is the same data/*.json that drives zerotorobot.vercel.app,
so whatever you push to the dashboard, Jarvis sees on its next launch.

The snapshot is kept deliberately compact — a 3B model with a 4096-token
window can't absorb the whole curriculum, so we send the active gate, the
books actually in progress, and the latest log entry, not everything.
"""
import json
from pathlib import Path

DATA = Path.home() / "Desktop/zero_to_robot/data"


def _load(name):
    p = DATA / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def available():
    return DATA.is_dir() and (DATA / "roadmap.json").exists()


def snapshot():
    """A short plain-text briefing on where the plan stands right now."""
    rm = _load("roadmap.json")
    if not rm:
        return ""

    lines = ["ROADMAP (live, from the Zero→Robot dashboard):"]

    # Active gate + its open quests — the thing to work on now.
    phases = rm.get("phases", [])
    active = next((p for p in phases if p.get("status") == "active"), None) or (phases[0] if phases else None)
    if active:
        ms = active.get("milestones", [])
        done = sum(1 for m in ms if m.get("done"))
        lines.append(f"- Active gate {active.get('id')}: {active['name']} ({done}/{len(ms)} quests done)")
        open_q = [m["text"] for m in ms if not m.get("done")][:5]
        for q in open_q:
            lines.append(f"    open: {q}")

    # Gate progress at a glance.
    prog = " | ".join(
        f"{p.get('id')}:{sum(1 for m in p.get('milestones', []) if m.get('done'))}/{len(p.get('milestones', []))}"
        for p in phases
    )
    if prog:
        lines.append(f"- Gate progress: {prog}")

    # Books actually being read (started but not finished) + next core book.
    bk = (_load("books.json") or {}).get("books", [])
    reading = [b for b in bk if 0 < b.get("chaptersRead", 0) < b.get("chaptersTotal", 1)]
    for b in reading[:3]:
        lines.append(f"- Reading: {b['title']} ({b['chaptersRead']}/{b['chaptersTotal']} ch)")
    if not reading:
        nxt = next((b for b in bk if b.get("priority") == "core" and b.get("chaptersRead", 0) == 0), None)
        if nxt:
            lines.append(f"- Next core book (unstarted): {nxt['title']}")

    # Courses in progress.
    co = (_load("courses.json") or {}).get("courses", [])
    doing = [c for c in co if c.get("status") == "in-progress"]
    for c in doing[:3]:
        lines.append(f"- Course in progress: {c['title']} ({c.get('progress', 0)}%)")

    # Latest raid-log entry — recent context on what was last worked on.
    entries = (_load("log.json") or {}).get("entries", [])
    if entries:
        e = entries[0]
        body = (e.get("body", "") or "")[:200]
        lines.append(f"- Latest log ({e.get('date', '?')}): {e.get('title', '')} — {body}")

    return "\n".join(lines)


def book_list():
    """Full book list on demand (for a /books-style query), not in every prompt."""
    bk = (_load("books.json") or {}).get("books", [])
    out = []
    for b in bk:
        tag = "core" if b.get("priority") == "core" else "ref"
        out.append(f"[{tag}] {b['title']} — {b.get('authors', '')} "
                   f"({b.get('chaptersRead', 0)}/{b.get('chaptersTotal', '?')} ch)")
    return "\n".join(out)


def log_entries(n=5):
    entries = (_load("log.json") or {}).get("entries", [])
    return entries[:n]
