"""Flashcards + spaced repetition.

Cards live in data/cards.json. Scheduling is SM-2 (the SuperMemo-2 algorithm
Anki is built on): each card carries an ease factor, an interval in days, and a
due date. Grade a card well and its interval grows; miss it and it resets to be
seen again tomorrow. So the cards you know drift apart in time and the ones you
don't keep coming back — that's the whole point of spaced repetition.
"""
import json
import re
from datetime import date, timedelta

import config

CARDS = config.DATA / "cards.json"


def _load():
    if not CARDS.exists():
        return []
    try:
        return json.loads(CARDS.read_text())
    except json.JSONDecodeError:
        return []


def _save(cards):
    CARDS.write_text(json.dumps(cards, indent=1, ensure_ascii=False))


def add(front, back, source="manual"):
    cards = _load()
    cards.append({
        "id": (max((c["id"] for c in cards), default=0) + 1),
        "front": front.strip(),
        "back": back.strip(),
        "source": source,
        "ease": 2.5,
        "interval": 0,
        "reps": 0,
        "due": date.today().isoformat(),  # new cards are due immediately
    })
    _save(cards)
    return cards[-1]


def due(today=None):
    today = today or date.today().isoformat()
    return [c for c in _load() if c["due"] <= today]


def grade(card_id, quality):
    """Apply SM-2. quality: 0=again, 3=hard, 4=good, 5=easy."""
    cards = _load()
    c = next((x for x in cards if x["id"] == card_id), None)
    if not c:
        return None

    if quality < 3:
        # missed → relearn from tomorrow, keep ease
        c["reps"] = 0
        c["interval"] = 1
    else:
        if c["reps"] == 0:
            c["interval"] = 1
        elif c["reps"] == 1:
            c["interval"] = 6
        else:
            c["interval"] = round(c["interval"] * c["ease"])
        c["reps"] += 1
        # standard SM-2 ease adjustment, floored at 1.3
        c["ease"] = max(1.3, c["ease"] + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

    c["due"] = (date.today() + timedelta(days=c["interval"])).isoformat()
    _save(cards)
    return c


def delete(card_id):
    cards = [c for c in _load() if c["id"] != card_id]
    _save(cards)


def stats():
    cards = _load()
    return {
        "total": len(cards),
        "due": len(due()),
        "learning": sum(1 for c in cards if c["reps"] < 2),
        "mature": sum(1 for c in cards if c["interval"] >= 21),
    }


# ---- generation from a note or topic ----

_QA = re.compile(r"Q:\s*(.+?)\s*A:\s*(.+?)(?=\n\s*Q:|\Z)", re.S | re.I)


def parse_cards(text):
    """Pull Q:/A: pairs out of model output. Robust to a 3B's messy formatting."""
    pairs = []
    for q, a in _QA.findall(text):
        q, a = q.strip(), a.strip()
        if q and a and len(q) < 300:
            pairs.append((q, a))
    return pairs


def gen_prompt(material, n=6):
    return (
        f"Make {n} flashcards from this material. Test understanding, not trivia. "
        f"Output ONLY pairs in exactly this format, nothing else:\n"
        f"Q: <question>\nA: <concise answer>\n\n"
        f"Material:\n{material[:4000]}"
    )
