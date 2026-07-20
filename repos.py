"""Find and clone GitHub repos — grounded in real data, never guessed.

This is the answer to the hallucinated-URL problem: the model is never asked
where a repo lives. We search the web, then confirm every candidate against the
GitHub API (real stars, description, default branch). What you see is verified
to exist. Cloning is a plain `git clone`; a note goes into the brain so Jarvis
remembers what it is.
"""
import subprocess
from pathlib import Path

import httpx

DEST = Path.home() / "Desktop"


def search(query, limit=6):
    """Web-search GitHub, then verify each hit against the GitHub API.

    Returns only repos the API confirms exist — so no invented URLs.
    """
    from ddgs import DDGS
    seen, out = set(), []
    try:
        with DDGS() as d:
            hits = list(d.text(f"github {query}", max_results=15))
    except Exception:
        hits = []
    for h in hits:
        url = h.get("href", "")
        if "github.com/" not in url:
            continue
        parts = url.split("github.com/", 1)[1].strip("/").split("/")
        if len(parts) < 2:
            continue
        slug = f"{parts[0]}/{parts[1]}"
        if slug.lower() in seen or parts[1] in ("topics", "search", "orgs"):
            continue
        seen.add(slug.lower())
        meta = _verify(slug)
        if meta:
            out.append(meta)
        if len(out) >= limit:
            break
    # sort by stars — the real one is usually the popular one
    out.sort(key=lambda r: -r["stars"])
    return out


def _verify(slug):
    try:
        r = httpx.get(f"https://api.github.com/repos/{slug}", timeout=10,
                      headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            "slug": d["full_name"],
            "url": d["clone_url"],
            "desc": d.get("description") or "",
            "stars": d.get("stargazers_count", 0),
            "lang": d.get("language") or "",
            "branch": d.get("default_branch", "main"),
        }
    except Exception:
        return None


def clone(repo, shallow=True):
    """Clone into ~/Desktop. Returns (path, ok, detail). Won't overwrite."""
    name = repo["slug"].split("/")[-1]
    dest = DEST / name
    if dest.exists():
        return dest, True, "already present"
    cmd = ["git", "clone"] + (["--depth", "1"] if shallow else []) + [repo["url"], str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return dest, False, (r.stderr or r.stdout)[:200]
    return dest, True, "cloned"


def readme_summary(path, cap=600):
    for name in ("README.md", "readme.md", "README.rst", "README"):
        f = Path(path) / name
        if f.exists():
            text = f.read_text(errors="ignore")
            # first substantial non-heading, non-markup paragraph
            for para in text.split("\n\n"):
                p = " ".join(para.split())
                if len(p) > 80 and not p.startswith(("#", "<", "![", "[!")):
                    return p[:cap]
            return text[:cap]
    return ""
