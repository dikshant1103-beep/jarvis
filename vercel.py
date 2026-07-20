"""Vercel status — read-only, via the already-logged-in `vercel` CLI.

No token to manage: the CLI is authenticated on this machine, so Jarvis just
shells out to it. Read-only — it lists projects and checks whether the live
sites respond. It never deploys, changes, or removes anything.
"""
import json
import re
import subprocess

import httpx
import config

CACHE = config.DATA / "vercel_projects.json"
_URL = re.compile(r"https://[\w.-]+\.vercel\.app")


def refresh():
    """Ask the CLI for the project list and cache it. Returns [{name, url}]."""
    try:
        out = subprocess.run(["vercel", "projects", "ls"],
                             capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return cached()
    projects = []
    # The CLI prints its table to stderr, not stdout — read both.
    for line in (out.stdout + "\n" + out.stderr).splitlines():
        m = _URL.search(line)
        if m:
            name = line.strip().split()[0]
            projects.append({"name": name, "url": m.group(0)})
    if projects:
        CACHE.write_text(json.dumps(projects, indent=1))
    return projects


def cached():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def projects():
    return cached() or refresh()


def liveness(projects=None):
    """Curl each project's production URL. Fast — for the daily briefing."""
    out = []
    for p in (projects if projects is not None else cached()):
        entry = {"name": p["name"], "url": p["url"]}
        try:
            r = httpx.head(p["url"], timeout=8, follow_redirects=True)
            entry["up"] = r.status_code < 400
            entry["code"] = r.status_code
        except Exception:
            entry["up"] = False
            entry["code"] = None
        out.append(entry)
    return out


def available():
    try:
        subprocess.run(["vercel", "--version"], capture_output=True, timeout=8)
        return True
    except Exception:
        return False
