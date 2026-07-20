"""Obsidian bridge — read and search your notes, capture new ones.

Safety rules, deliberately strict because these are your real notes:
  - Jarvis NEVER overwrites or edits an existing note.
  - New notes are only ever created under JARVIS_SUBDIR.
  - Daily notes are appended to, never rewritten.
Everything else is read-only.
"""
import json
import re
from datetime import date
from pathlib import Path

OBSIDIAN_CONFIG = Path.home() / ".config/obsidian/obsidian.json"
DAILY_DIR = "00-Daily"            # captures land here
CONCEPTS_DIR = "01-Concepts"      # saved notes land here
JARVIS_SUBDIR = "01-Concepts"     # the folder Jarvis writes new notes in
SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules", ".venv"}


def list_vaults():
    """All vaults Obsidian knows about; the open one first."""
    if not OBSIDIAN_CONFIG.exists():
        return []
    try:
        cfg = json.loads(OBSIDIAN_CONFIG.read_text())
    except json.JSONDecodeError:
        return []
    out = []
    for meta in cfg.get("vaults", {}).values():
        p = Path(meta["path"])
        if p.is_dir():
            out.append({"path": p, "name": p.name, "open": bool(meta.get("open"))})
    out.sort(key=lambda v: (not v["open"], v["name"]))
    return out


def default_vault():
    v = list_vaults()
    return v[0]["path"] if v else None


def _notes(root):
    for p in root.rglob("*.md"):
        if not any(part in SKIP_DIRS for part in p.parts):
            yield p


def search(root, query, limit=6):
    """Rank notes by how often the query terms appear. Title hits weigh most.

    Deliberately plain keyword scoring — no embedding index to build or keep
    fresh, and it stays fast enough on a 1000-note vault.
    """
    terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
    if not terms:
        return []
    hits = []
    for p in _notes(root):
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        low = text.lower()
        title = p.stem.lower()
        score = sum(low.count(t) + 12 * title.count(t) for t in terms)
        if score:
            hits.append((score, p, text))
    hits.sort(key=lambda h: -h[0])
    return hits[:limit]


def context_for(root, query, budget=6000, limit=4):
    """Relevant note excerpts, formatted for the model's context window.

    Spends the budget greedily from the best match down, so the top note
    arrives whole rather than every note arriving truncated. Splitting the
    budget evenly is what makes RAG answers vague — each note gets a fragment
    too small to reason from.
    """
    hits = search(root, query, limit=limit)
    if not hits:
        return "", []
    chunks, used, names = [], 0, []
    for score, p, text in hits:
        rel = p.relative_to(root)
        left = budget - used
        if left < 400:                     # too little room to be worth including
            break
        body = text.strip()
        if len(body) > left:
            body = body[:left].rsplit("\n", 1)[0] + "\n…(truncated)"
        block = f"--- note: {rel} ---\n{body}\n"
        chunks.append(block)
        names.append(str(rel))
        used += len(block)
    return "\n".join(chunks), names


def read_note(root, name):
    """Find a note by fuzzy name match and return (relative_path, text)."""
    name = name.lower().removesuffix(".md")
    best = None
    for p in _notes(root):
        stem = p.stem.lower()
        if stem == name:
            best = p
            break
        if name in stem and best is None:
            best = p
    if not best:
        return None, None
    return best.relative_to(root), best.read_text(errors="ignore")


def capture(root, text):
    """Append a timestamped line to today's daily note. Never overwrites."""
    d = root / DAILY_DIR
    d.mkdir(parents=True, exist_ok=True)
    note = d / f"{date.today().isoformat()}.md"
    if not note.exists():
        note.write_text(f"# {date.today():%A, %d %B %Y}\n\n")
    with note.open("a") as f:
        f.write(f"- {text.strip()}\n")
    return note.relative_to(root)


def write_note(root, title, body):
    """Create a new note under JARVIS_SUBDIR. Refuses to clobber."""
    safe = re.sub(r"[^\w\s-]", "", title).strip()[:80] or "untitled"
    d = root / JARVIS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{safe}.md"
    if p.exists():
        return None  # caller reports the collision; we never overwrite
    p.write_text(f"# {title}\n\n{body}\n")
    return p.relative_to(root)


def stats(root):
    n = sum(1 for _ in _notes(root))
    return {"notes": n, "name": root.name}
