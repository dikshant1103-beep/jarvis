"""Find papers on arXiv — real results from the arXiv API, never guessed.

Same principle as the repo finder: the model is never asked what a paper is
called or where it lives. We query arXiv's official API and show what actually
exists — title, authors, year, abstract, and the real PDF link.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}
DEST = Path.home() / "Desktop"


def search(query, n=6):
    """Return real arXiv papers for the query. Empty list on failure.

    arXiv's API is often slow (10-30s) and occasionally rate-limits, so we
    retry a couple of times before giving up.
    """
    root = None
    for attempt in range(3):
        try:
            r = httpx.get(API, params={
                "search_query": f"all:{query}",
                "start": 0, "max_results": n,
                "sortBy": "relevance", "sortOrder": "descending",
            }, timeout=45, follow_redirects=True, headers={"User-Agent": "Jarvis/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.text)
            break
        except Exception:
            if attempt < 2:
                import time
                time.sleep(3)  # arXiv asks for 3s between requests
    if root is None:
        return []

    out = []
    for e in root.findall("a:entry", NS):
        aid = (e.findtext("a:id", "", NS) or "").rsplit("/", 1)[-1]
        title = " ".join((e.findtext("a:title", "", NS) or "").split())
        summary = " ".join((e.findtext("a:summary", "", NS) or "").split())
        published = e.findtext("a:published", "", NS)[:4]
        authors = [a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)]
        pdf = next((l.get("href") for l in e.findall("a:link", NS)
                    if l.get("title") == "pdf"), f"https://arxiv.org/pdf/{aid}")
        out.append({
            "id": aid, "title": title, "authors": authors,
            "year": published, "summary": summary,
            "url": f"https://arxiv.org/abs/{aid}", "pdf": pdf,
        })
    return out


EXPLAIN = """Below are {n} papers found on arXiv for the search: "{query}"

{digest}

Write exactly one line per paper, in this format:

[0] what it does, plainly — who it's for

Rules:
- One line each, under 20 words. No blank line between them.
- Plain English. Don't reuse the wording of the title.
- Use only what that paper's abstract says.

Then one last line, in this format:

START: [n] because <reason>

Pick the number most directly useful to someone searching "{query}". Give a
reason specific to that paper — do not repeat its line from above."""


def explain_prompt(hits, query, cap=500):
    """Prompt asking the model to gloss each abstract in plain English.

    Only the gloss comes from the model — title, authors, year and link are
    printed straight from arXiv. Same rule as everywhere else here: the model
    may paraphrase what it was given, never source the facts.
    """
    digest = "\n\n".join(
        f"[{i}] {p['title']}\n{p['summary'][:cap]}" for i, p in enumerate(hits))
    return EXPLAIN.format(n=len(hits), query=query, digest=digest)


def _safe(name):
    return re.sub(r"[^\w\s-]", "", name).strip()[:80] or "paper"


def download(paper):
    """Save the PDF to ~/Desktop/papers. Returns (path, ok, detail)."""
    d = DEST / "papers"
    d.mkdir(exist_ok=True)
    dest = d / f"{paper['id']} {_safe(paper['title'])[:60]}.pdf"
    if dest.exists():
        return dest, True, "already saved"
    try:
        with httpx.stream("GET", paper["pdf"], timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dest, True, "downloaded"
    except Exception as e:
        return dest, False, str(e)[:150]
