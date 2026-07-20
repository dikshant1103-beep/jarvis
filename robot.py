"""Write-back to the Zero → Robot dashboard.

Talk to Jarvis, and your public site updates. Edits are made to the local
data/*.json first — nothing goes live until you run /robot push, which commits
and pushes (Vercel then auto-deploys in ~30s).

Safety, because this touches a live public site:
  - every edit names exactly what it changed (old → new), so a fuzzy-match to
    the wrong item is obvious before you push;
  - edits are local and git-tracked, so any mistake is one `git checkout` away;
  - push is a separate, explicit, confirmed step — never automatic;
  - commits use the required GitHub noreply email.
"""
import difflib
import json
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path.home() / "Desktop/zero_to_robot"
DATA = ROOT / "data"
NOREPLY = "261631710+dikshant1103-beep@users.noreply.github.com"


def available():
    return (DATA / "roadmap.json").exists() and (ROOT / ".git").is_dir()


def _load(name):
    return json.loads((DATA / name).read_text())


def _save(name, obj):
    # trailing newline so the diff is clean and matches how the app writes it
    (DATA / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _match(query, items, key):
    """Best fuzzy match of query against items[key]. Returns (item, score)."""
    q = query.lower().strip()
    best, best_score = None, 0.0
    for it in items:
        text = str(it[key]).lower()
        if q in text:                       # substring wins
            score = 0.6 + 0.4 * (len(q) / len(text))
        else:
            score = difflib.SequenceMatcher(None, q, text).ratio()
        if score > best_score:
            best, best_score = it, score
    return best, best_score


# ---- edits (local) ----

import re as _re

# roadmap.json keeps each milestone on a single compact line, so we edit that
# one line in place rather than reserialising the whole file (which would
# reformat every milestone and bury the real change in a 160-line diff).
_MS_LINE = _re.compile(r'"text":\s*"(.*?)".*?"done":\s*(true|false)')


def set_quest(query, done=True):
    path = DATA / "roadmap.json"
    lines = path.read_text().split("\n")
    q = query.lower().strip()

    best_i, best_text, best_score = None, None, 0.0
    for i, line in enumerate(lines):
        m = _MS_LINE.search(line)
        if not m:
            continue
        text = m.group(1)
        low = text.lower()
        score = 0.6 + 0.4 * (len(q) / max(len(low), 1)) if q in low \
            else difflib.SequenceMatcher(None, q, low).ratio()
        if score > best_score:
            best_i, best_text, best_score = i, text, score

    if best_i is None or best_score < 0.4:
        return None

    old = '"done": true' in lines[best_i] or '"done":true' in lines[best_i]
    lines[best_i] = _re.sub(r'("done":\s*)(true|false)',
                            lambda mm: mm.group(1) + ("true" if done else "false"),
                            lines[best_i])
    # nearest preceding gate name, for the confirmation message
    gate = "?"
    for j in range(best_i, -1, -1):
        gm = _re.search(r'"name":\s*"(.*?)"', lines[j])
        if gm:
            gate = gm.group(1)
            break
    path.write_text("\n".join(lines))
    return {"what": f"quest \"{best_text[:60]}\"", "gate": gate,
            "from": "done" if old else "open", "to": "done" if done else "open"}


def set_chapters(query, n):
    bk = _load("books.json")
    match, score = _match(query, bk["books"], "title")
    if not match or score < 0.4:
        return None
    old = match["chaptersRead"]
    match["chaptersRead"] = max(0, min(int(n), match["chaptersTotal"]))
    _save("books.json", bk)
    return {"what": f"book \"{match['title'][:50]}\"", "from": f"{old} ch",
            "to": f"{match['chaptersRead']}/{match['chaptersTotal']} ch"}


def set_course(query, pct):
    co = _load("courses.json")
    match, score = _match(query, co["courses"], "title")
    if not match or score < 0.4:
        return None
    old = match["progress"]
    p = max(0, min(int(pct), 100))
    match["progress"] = p
    match["status"] = "done" if p >= 100 else "in-progress" if p > 0 else "not-started"
    _save("courses.json", co)
    return {"what": f"course \"{match['title'][:50]}\"", "from": f"{old}%", "to": f"{p}%"}


def add_log(title, body):
    lg = _load("log.json")
    rm = _load("roadmap.json")
    active = next((p for p in rm["phases"] if p.get("status") == "active"), rm["phases"][0])
    lg["entries"].insert(0, {
        "date": date.today().isoformat(),
        "title": title.strip(),
        "phase": active.get("id", 0),
        "body": body.strip(),
        "links": [],
    })
    _save("log.json", lg)
    return {"what": f"log entry \"{title[:50]}\"", "from": "", "to": "added"}


# ---- git ----

def pending():
    """List of data files with uncommitted changes."""
    out = subprocess.run(["git", "-C", str(ROOT), "status", "--short", "data/"],
                         capture_output=True, text=True)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def diff_summary():
    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--stat", "data/"],
                         capture_output=True, text=True)
    return out.stdout.strip()


def revert():
    """Throw away all local data edits — the undo button."""
    subprocess.run(["git", "-C", str(ROOT), "checkout", "--", "data/"],
                   capture_output=True, text=True)


def push(message):
    """Commit the data changes with the noreply email, then push."""
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args],
                              capture_output=True, text=True)
    git("add", "data/")
    r = git("-c", f"user.email={NOREPLY}", "-c", "user.name=dikshant",
            "commit", "-m", message)
    if "nothing to commit" in (r.stdout + r.stderr):
        return False, "nothing to commit"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[:300]
    p = git("push", "origin", "main")
    if p.returncode != 0:
        return False, (p.stderr or p.stdout)[:300]
    return True, "pushed → Vercel will redeploy in ~30s"
