"""Daily task list — plain JSON on disk, no database, no cloud."""
import json
from datetime import date
import config


def _load():
    if not config.TASKS_FILE.exists():
        return {}
    try:
        return json.loads(config.TASKS_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _save(d):
    config.TASKS_FILE.write_text(json.dumps(d, indent=1))


def _today():
    return date.today().isoformat()


def add(text, day=None):
    d = _load()
    day = day or _today()
    d.setdefault(day, []).append({"text": text.strip(), "done": False})
    _save(d)


def list_day(day=None):
    return _load().get(day or _today(), [])


def toggle(index, day=None):
    d = _load()
    day = day or _today()
    items = d.get(day, [])
    if 0 <= index < len(items):
        items[index]["done"] = not items[index]["done"]
        _save(d)
        return items[index]
    return None


def remove(index, day=None):
    d = _load()
    day = day or _today()
    items = d.get(day, [])
    if 0 <= index < len(items):
        gone = items.pop(index)
        _save(d)
        return gone
    return None


def carry_over():
    """Pull yesterday's unfinished items into today. Returns how many moved."""
    d = _load()
    today = _today()
    moved = 0
    for day in sorted(d.keys()):
        if day >= today:
            continue
        keep = []
        for t in d[day]:
            if not t["done"]:
                d.setdefault(today, []).append(t)
                moved += 1
            else:
                keep.append(t)
        d[day] = keep
    if moved:
        _save(d)
    return moved


def summary():
    """One line for the LLM's context, so it knows what's on the plate."""
    items = list_day()
    if not items:
        return "No tasks set for today."
    done = sum(1 for t in items if t["done"])
    lines = [f"{'x' if t['done'] else ' '} {t['text']}" for t in items]
    return f"Today's tasks ({done}/{len(items)} done):\n" + "\n".join(lines)
