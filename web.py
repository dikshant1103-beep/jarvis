"""Internet search — the one part of Jarvis that reaches outside the laptop.

Everything else here is fully local. This module is the deliberate exception:
when you run /web, your query goes to DuckDuckGo and a few result pages are
fetched. It only ever runs when you explicitly ask — never in the background,
never on a normal chat turn.

No API key: DuckDuckGo via ddgs, pages fetched with httpx, HTML stripped with a
tiny regex cleaner (no scraping framework to keep it light).
"""
import re
import httpx

UA = "Mozilla/5.0 (X11; Linux x86_64) Jarvis/1.0"


def online(timeout=6):
    try:
        httpx.get("https://duckduckgo.com", timeout=timeout,
                  headers={"User-Agent": UA})
        return True
    except Exception:
        return False


def search(query, n=5):
    """Return [{title, url, snippet}] from DuckDuckGo. Empty list on failure."""
    from ddgs import DDGS
    try:
        with DDGS() as d:
            return [
                {"title": r.get("title", ""), "url": r.get("href", ""),
                 "snippet": r.get("body", "")}
                for r in d.text(query, max_results=n)
            ]
    except Exception:
        return []


_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n\s*\n\s*\n+")


def fetch_text(url, cap=3500):
    """Fetch a page and return readable plain text, capped. '' on any failure."""
    try:
        r = httpx.get(url, timeout=12, follow_redirects=True,
                      headers={"User-Agent": UA})
        r.raise_for_status()
    except Exception:
        return ""
    if "text/html" not in r.headers.get("content-type", "") and "<html" not in r.text[:200].lower():
        # plain text / markdown page — use as-is
        return r.text[:cap]
    body = _TAG.sub(" ", r.text)
    body = _HTML.sub(" ", body)
    body = re.sub(r"&[a-z]+;", " ", body)
    body = _WS.sub("\n\n", re.sub(r"[ \t]+", " ", body)).strip()
    return body[:cap]


# Official docs and reputable references outrank SEO-farm pages, which is what
# fools a small model into repeating stale info.
_TRUSTED = ("docs.", ".org", "github.com", "wikipedia.org", "readthedocs",
            "arxiv.org", ".edu", "stackoverflow.com", "pytorch.org")


def _rank(hits):
    def score(h):
        u = h.get("url", "").lower()
        return -sum(2 if t in u else 0 for t in _TRUSTED)
    return sorted(hits, key=score)


def gather(query, pages=3, per_page=2500):
    """Search, fetch the top pages, and format context for the model.

    Returns (context_text, sources[]). Sources are numbered so the model can
    cite them and the user can click through. Authoritative domains are fetched
    first — the biggest lever on answer quality for a small local model.
    """
    hits = _rank(search(query, n=8))
    if not hits:
        return "", []
    chunks, sources = [], []
    for h in hits:
        if len(sources) >= pages:
            break
        text = fetch_text(h["url"], cap=per_page)
        # fall back to the search snippet if the page wouldn't fetch
        body = text or h["snippet"]
        if not body:
            continue
        n = len(sources) + 1
        sources.append({"n": n, "title": h["title"], "url": h["url"]})
        chunks.append(f"[{n}] {h['title']}\n{h['url']}\n{body}\n")
    return "\n".join(chunks), sources
