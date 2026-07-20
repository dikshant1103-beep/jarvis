#!/usr/bin/env python3
"""Jarvis — a local assistant. Text first, voice on demand.

Everything runs on this laptop: Ollama for the model, faster-whisper for
speech, your Obsidian vault for knowledge. Nothing is sent anywhere.
"""
import sys
from datetime import date
from pathlib import Path

import boot
import config
import tasks
import vault
from brain import Brain

C = {
    "dim": "\033[2m", "b": "\033[1m", "cyan": "\033[38;5;51m",
    "gold": "\033[38;5;220m", "green": "\033[38;5;42m", "red": "\033[38;5;203m",
    "r": "\033[0m",
}


def c(s, k):
    return f"{C[k]}{s}{C['r']}"


HELP = f"""
  {c('just type', 'b')}          talk — the right tool is picked for you
  {c('/auto on|off', 'b')}       automatic tool-routing (on by default)
  {c('/v', 'b')} [secs]          voice input (default 15s, Ctrl-C stops early)

  {c('/t', 'b')}                 today's tasks       {c('/t add <text>', 'dim')}
  {c('/t done <n>', 'b')}        toggle              {c('/t rm <n>  /t carry', 'dim')}
  {c('/robot done <quest>', 'b')} mark a roadmap quest done (updates your site)
  {c('/robot read <book> <n>', 'b')} set chapters read   {c('/robot course <c> <%>', 'dim')}
  {c('/robot log <t> :: <b>', 'b')} add a raid-log entry
  {c('/robot', 'b')}             show pending changes   {c('/robot push   /robot revert', 'dim')}
  {c('/brief', 'b')}             morning briefing — tasks, mail, gate, sites
  {c('/vercel', 'b')}            your Vercel projects — are they live?
  {c('/plan', 'b')}              plan the day around your tasks

  {c('/study', 'b')}             review flashcards due today (spaced repetition)
  {c('/study gen <note>', 'b')}  make cards from a brain note or topic
  {c('/study add', 'b')}         add a card by hand   {c('/study stats', 'dim')}
  {c('/mail', 'b')}              recent inbox (read-only)   {c('/mail unread  /mail sum', 'dim')}
  {c('/ask <question>', 'b')}    answer using your Obsidian notes
  {c('/g <question>', 'b')}      ask Gemini (cloud, strong reasoning)
  {c('/web <question>', 'b')}    search the internet, answer with sources
  {c('/note <name>', 'b')}       read a note
  {c('/paper <query>', 'b')}     find papers on arXiv + a line explaining each
  {c('/paper abs <n>', 'b')}     the real abstract   {c('/paper get <n>  download PDF', 'dim')}
  {c('/repo <name>', 'b')}       find a GitHub repo (verified, not guessed)
  {c('/repo clone <n>', 'b')}    clone a found repo + note it in the brain
  {c('/find <query>', 'b')}      search the vault
  {c('/cap <text>', 'b')}        capture a line into today's daily note
  {c('/save <title>', 'b')}      save the last reply as a new note
  {c('/vault', 'b')}             show / switch vault

  {c('/img <path> [q]', 'b')}    ask about an image (7B vision model, slower)
  {c('/reset', 'b')}   {c('/help', 'b')}   {c('/q', 'b')}
"""


def show_tasks():
    items = tasks.list_day()
    if not items:
        print(c("  no tasks today — add one with /t add <text>", "dim"))
        return
    for i, t in enumerate(items):
        mark = c("✓", "green") if t["done"] else c("○", "dim")
        text = c(t["text"], "dim") if t["done"] else t["text"]
        print(f"  {mark} {c(str(i), 'dim')} {text}")


def handle_tasks(arg):
    parts = arg.split(maxsplit=1)
    cmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    if not cmd:
        show_tasks()
    elif cmd == "add" and rest:
        tasks.add(rest)
        print(c(f"  added: {rest}", "green"))
    elif cmd in ("done", "rm") and rest.strip().isdigit():
        i = int(rest.strip())
        item = tasks.toggle(i) if cmd == "done" else tasks.remove(i)
        if item is None:
            print(c(f"  no task {i}", "red"))
        else:
            verb = ("done" if item["done"] else "reopened") if cmd == "done" else "removed"
            print(c(f"  {verb}: {item['text']}", "green"))
        show_tasks()
    elif cmd == "carry":
        n = tasks.carry_over()
        print(c(f"  carried over {n} unfinished task(s)", "green" if n else "dim"))
        show_tasks()
    else:
        print(c("  usage: /t | /t add <text> | /t done <n> | /t rm <n> | /t carry", "dim"))


def stream_reply(brain, prompt, images=None):
    print(c("jarvis ", "cyan"), end="", flush=True)
    reply = brain.ask(prompt, on_token=lambda t: print(t, end="", flush=True), images=images)
    print("\n")
    return reply


class Session:
    def __init__(self):
        self.brain = Brain()
        self.brain.load()
        pinned = config.vault_path()
        vaults = vault.list_vaults()
        self.vault = Path(pinned) if pinned else (vaults[0]["path"] if vaults else None)
        self.last_reply = ""
        self.auto = config.auto_route()


def handle_vault(s, arg):
    vaults = vault.list_vaults()
    if not vaults:
        print(c("  no Obsidian vaults found", "red"))
        return
    if not arg:
        print()
        for i, v in enumerate(vaults):
            here = c(" ← active", "green") if s.vault and v["path"] == s.vault else ""
            n = vault.stats(v["path"])["notes"]
            print(f"  {c(str(i), 'dim')} {v['name']} {c(f'({n} notes)', 'dim')}{here}")
        print(c("\n  switch with /vault <n>\n", "dim"))
        return
    if arg.strip().isdigit():
        i = int(arg.strip())
        if 0 <= i < len(vaults):
            s.vault = vaults[i]["path"]
            config.pin_vault(s.vault)
            print(c(f"  active vault: {vaults[i]['name']}", "green"))
        else:
            print(c(f"  no vault {i}", "red"))


def handle_ask(s, question):
    """Answer grounded in the vault, and say which notes were used."""
    if not s.vault:
        print(c("  no vault configured — /vault", "red"))
        return
    ctx, names = vault.context_for(s.vault, question)
    if not ctx:
        print(c("  nothing relevant in the vault — answering from the model alone", "dim"))
        s.last_reply = stream_reply(s.brain, question)
        return
    print(c(f"  reading: {', '.join(names)}", "dim"))
    prompt = (
        f"Notes from my Obsidian vault:\n\n{ctx}\n\n"
        f"Question: {question}\n\n"
        "Answer using those notes where they're relevant. If they don't cover "
        "it, say so plainly rather than guessing."
    )
    s.last_reply = stream_reply(s.brain, prompt)


def run_web(s, q):
    """Search the internet and answer with cited sources."""
    import web
    if not web.online():
        print(c("  offline — /web needs the internet", "red"))
        return
    print(c("  ↗ searching the web (this query leaves the laptop)…", "dim"))
    ctx, sources = web.gather(q, pages=3)
    if not ctx:
        print(c("  no usable results", "dim"))
        return
    for src in sources:
        print(c(f"    [{src['n']}] {src['title'][:60]}", "dim"))
    s.last_reply = stream_reply(s.brain, (
        f"Web search results for: {q}\n\n{ctx}\n\n"
        "Answer the question using these sources. Cite them inline like "
        "[1], [2]. If the sources disagree or don't answer it, say so — "
        "don't fill the gap from memory."))
    # keep the links so /save preserves them with the answer
    s.last_reply += "\n\nSources:\n" + "\n".join(
        f"[{x['n']}] {x['url']}" for x in sources)


def run_gemini(s, q):
    """Ask Gemini — the only command that sends your context off the laptop."""
    import gemini
    if not gemini.available():
        print(c("  no Gemini key — add GEMINI_API_KEY to .env", "red"))
        return
    print(c("  ↗ asking Gemini (leaves the laptop)…", "dim"))
    print(c("gemini ", "cyan"), end="", flush=True)
    s.last_reply = gemini.ask(
        q, system=config.build_system_prompt(),
        on_token=lambda t: print(t, end="", flush=True))
    print("\n")


def run_auto(s, line):
    """A plain sentence: pick the tool, say which, run it.

    Routing is always announced. If it picks wrong you can see why in one
    glance and rerun with the explicit command — that transparency is what
    makes automatic routing safe to leave on.
    """
    if not s.auto:
        s.last_reply = stream_reply(s.brain, line)
        return

    import router
    tool, why = router.route(line, brain=s.brain)
    if tool == "local":
        s.last_reply = stream_reply(s.brain, line)
        return

    print(c(f"  → /{tool}  ({why})", "dim"))
    if tool == "paper":
        run_paper(s, line)
    elif tool == "repo":
        run_repo(s, line)
    elif tool == "web":
        run_web(s, line)
    elif tool == "gemini":
        run_gemini(s, line)
    elif tool == "vault":
        handle_ask(s, line)


def run_paper(s, arg):
    import paper
    parts = arg.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "get":
        if not rest.strip().isdigit():
            print(c("  usage: /paper get <number>", "dim"))
            return
        i = int(rest.strip())
        hits = getattr(s, "paper_hits", [])
        if not (0 <= i < len(hits)):
            print(c("  no such result — run /paper <query> first", "red"))
            return
        print(c(f"  ↗ downloading {hits[i]['id']}…", "dim"))
        path, ok, detail = paper.download(hits[i])
        print(c(f"  {'✓ ' if ok else '✗ '}{detail}" + (f" → {path}" if ok else ""),
                "green" if ok else "red"))
        return

    if cmd == "abs":
        if not rest.strip().isdigit():
            print(c("  usage: /paper abs <number>", "dim"))
            return
        i = int(rest.strip())
        hits = getattr(s, "paper_hits", [])
        if not (0 <= i < len(hits)):
            print(c("  no such result — run /paper <query> first", "red"))
            return
        p = hits[i]
        print(f"\n{c(p['title'], 'b')}")
        print(c(f"{', '.join(p['authors'])} · {p['year']} · {p['url']}", "dim"))
        print(c("─" * 60, "dim"))
        print(p["summary"] + "\n")
        return

    if not arg:
        print(c("  usage: /paper <query>   then   /paper get <n>", "dim"))
        return
    from spinner import Spinner
    with Spinner(f"searching arXiv for '{arg[:40]}'"):
        hits = paper.search(arg)
    if not hits:
        print(c("  no results (arXiv may be slow — try again)", "red"))
        return
    s.paper_hits = hits
    # The list prints immediately — it's free and it's the grounded part.
    for i, p in enumerate(hits):
        auth = ", ".join(p["authors"][:2]) + (" et al." if len(p["authors"]) > 2 else "")
        print(f"  {c(str(i), 'gold')} {c('[' + p['year'] + ']', 'dim')} {c(p['title'][:66], 'b')}")
        print(c(f"      {auth} · {p['url']}", "dim"))

    explain_papers(s, hits, arg)
    print(c("\n  /paper abs <n> for the real abstract · /paper get <n> for the PDF\n", "dim"))


def explain_papers(s, hits, query):
    """Gloss each abstract in plain English — Gemini if we can, local if not.

    Gemini gets the profile as system context, so "who it's for" comes back
    aimed at you rather than at robotics researchers in general. It's a cloud
    call, so it's announced; any failure falls back to the local model rather
    than leaving you with a bare list.
    """
    import gemini
    import paper
    from spinner import Spinner
    prompt = paper.explain_prompt(hits, query)

    if gemini.available():
        print(c("\n  reading the abstracts (Gemini — leaves the laptop)", "dim"))
        sp = Spinner("thinking").start()
        state = {"started": False, "failed": False}

        def emit(tok):
            # Errors arrive as one whole "[Gemini …]" chunk, so checking the
            # first token is enough to decide whether to fall back quietly.
            if not state["started"]:
                state["started"] = True
                if tok.lstrip().startswith("[Gemini"):
                    state["failed"] = True
                    return
                sp.stop()
            if not state["failed"]:
                print(tok, end="", flush=True)

        try:
            gemini.ask(prompt, system=config.build_system_prompt(), on_token=emit)
        except Exception:
            state["failed"] = True
        sp.stop()
        if not state["failed"]:
            print()
            return
        print(c("  Gemini unavailable — using the local model instead", "dim"))

    print(c("\n  reading the abstracts…", "dim"))
    sp = Spinner("thinking").start()
    first = {"seen": False}

    def emit_local(tok):
        if not first["seen"]:
            first["seen"] = True
            sp.stop()
        print(tok, end="", flush=True)

    try:
        s.brain.complete(prompt, max_tokens=320, on_token=emit_local)
        print()
    except Exception as e:
        print(c(f"  (couldn't summarize: {str(e)[:80]})", "dim"))
    finally:
        sp.stop()


def run_repo(s, arg):
    import repos
    parts = arg.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "clone":
        if not rest.strip().isdigit():
            print(c("  usage: /repo clone <number from the list>", "dim"))
            return
        i = int(rest.strip())
        cands = getattr(s, "repo_hits", [])
        if not (0 <= i < len(cands)):
            print(c("  no such result — run /repo <name> first", "red"))
            return
        repo = cands[i]
        print(c(f"  ↗ cloning {repo['slug']}…", "dim"))
        path, ok, detail = repos.clone(repo)
        if not ok:
            print(c(f"  clone failed: {detail}", "red"))
            return
        print(c(f"  ✓ {detail} → {path}", "green"))
        # remember it in the brain, grounded in the real README
        if s.vault:
            summary = repos.readme_summary(path)
            body = (f"**Repo:** {repo['url'].replace('.git','')}  "
                    f"({repo['stars']}★, {repo['lang']})\n"
                    f"**Cloned to:** {path}\n\n{repo['desc']}\n\n{summary}\n\n"
                    f"Status: cloned, not yet set up. Decide how to use it later.")
            rel = vault.write_note(s.vault, repo["slug"].split("/")[-1], body)
            if rel:
                print(c(f"  noted in brain → {rel}", "dim"))
        return

    if not arg:
        print(c("  usage: /repo <name>   then   /repo clone <n>", "dim"))
        return

    print(c(f"  ↗ searching GitHub for '{arg}' (verifying each result)…", "dim"))
    hits = repos.search(arg)
    if not hits:
        print(c("  no verified repos found — try a more specific name", "red"))
        return
    s.repo_hits = hits
    for i, r in enumerate(hits):
        meta = f"{r['stars']}★ {r['lang']}"
        print(f"  {c(str(i), 'gold')} {c(r['slug'], 'b')} {c(meta, 'dim')}")
        if r["desc"]:
            print(c(f"     {r['desc'][:80]}", "dim"))
    print(c("\n  clone one with /repo clone <n>\n", "dim"))


def run_robot(s, arg):
    import robot
    if not robot.available():
        print(c("  Zero→Robot repo not found at ~/Desktop/zero_to_robot", "red"))
        return
    parts = arg.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    def report(r):
        if not r:
            print(c("  no matching item — check the name and try again", "red"))
            return
        arrow = f"{r['from']} → {r['to']}" if r["from"] else r["to"]
        print(c(f"  ✓ {r['what']}: {arrow}", "green"))
        print(c("  (local only — run /robot push to make it live)", "dim"))

    if cmd in ("", "status"):
        pend = robot.pending()
        if not pend:
            print(c("  no pending changes — dashboard is in sync", "dim"))
        else:
            print(c(f"  {len(pend)} file(s) with unpushed edits:", "b"))
            print(c("  " + robot.diff_summary().replace("\n", "\n  "), "dim"))
            print(c("  → /robot push to deploy, or /robot revert to discard", "dim"))
        return

    if cmd == "revert":
        if robot.pending() and input(c("  discard all local edits? [y/N] ", "gold")).strip().lower() == "y":
            robot.revert()
            print(c("  reverted", "green"))
        else:
            print(c("  kept", "dim"))
        return

    if cmd == "push":
        pend = robot.pending()
        if not pend:
            print(c("  nothing to push", "dim"))
            return
        print(c("  about to commit + push these to your LIVE site:", "b"))
        print(c("  " + robot.diff_summary().replace("\n", "\n  "), "dim"))
        if input(c("  push to production? [y/N] ", "gold")).strip().lower() != "y":
            print(c("  cancelled — changes stay local", "dim"))
            return
        msg = rest.strip() or "Update dashboard progress (via Jarvis)"
        print(c("  ↗ pushing…", "dim"))
        ok, detail = robot.push(msg)
        print(c(f"  {'✓ ' if ok else '✗ '}{detail}", "green" if ok else "red"))
        return

    if cmd in ("done", "undone"):
        report(robot.set_quest(rest, done=(cmd == "done")))
    elif cmd == "read":
        toks = rest.rsplit(maxsplit=1)
        if len(toks) == 2 and toks[1].isdigit():
            report(robot.set_chapters(toks[0], int(toks[1])))
        else:
            print(c("  usage: /robot read <book> <chapters>", "dim"))
    elif cmd == "course":
        toks = rest.rsplit(maxsplit=1)
        if len(toks) == 2 and toks[1].isdigit():
            report(robot.set_course(toks[0], int(toks[1])))
        else:
            print(c("  usage: /robot course <name> <percent>", "dim"))
    elif cmd == "log":
        if "::" in rest:
            title, body = rest.split("::", 1)
            report(robot.add_log(title, body))
        else:
            print(c("  usage: /robot log <title> :: <body>", "dim"))
    else:
        print(c("  unknown — try: done / undone / read / course / log / push / revert", "dim"))


def run_study(s, arg):
    import study
    parts = arg.split(maxsplit=1)
    cmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "stats":
        st = study.stats()
        print(c(f"  {st['total']} cards · {st['due']} due · {st['learning']} learning · {st['mature']} mature", "dim"))
        return

    if cmd == "add":
        try:
            front = input(c("  front (question): ", "gold")).strip()
            back = input(c("  back (answer):   ", "gold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if front and back:
            study.add(front, back)
            print(c("  card added", "green"))
        return

    if cmd == "gen":
        if not rest:
            print(c("  usage: /study gen <note name or topic>", "dim"))
            return
        # material = a brain note if it matches, else treat the text as a topic
        material, label = rest, f"gen:{rest[:30]}"
        if s.vault:
            rel, text = vault.read_note(s.vault, rest)
            if rel:
                material, label = text, f"note:{rel}"
                print(c(f"  from {rel}", "dim"))
        # Gemini writes better cards when available; fall back to local.
        prompt = study.gen_prompt(material, n=6)
        import gemini
        print(c("  drafting cards…", "dim"))
        raw = (gemini.ask(prompt, system="You write precise study flashcards.")
               if gemini.available() else s.brain.ask(prompt))
        pairs = study.parse_cards(raw)
        if not pairs:
            print(c("  couldn't parse any cards — try a clearer note/topic", "red"))
            return
        print(c(f"\n  {len(pairs)} draft cards:", "b"))
        for i, (q, a) in enumerate(pairs):
            print(f"  {c(str(i), 'dim')} Q: {q}\n     {c('A: ' + a, 'dim')}")
        try:
            keep = input(c("\n  save these? [Y/n, or space-separated numbers to keep]: ", "gold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if keep.lower() == "n":
            print(c("  discarded", "dim"))
            return
        idxs = ([int(x) for x in keep.split() if x.isdigit()] if keep and keep.lower() != "y"
                else range(len(pairs)))
        n = 0
        for i in idxs:
            if 0 <= i < len(pairs):
                study.add(pairs[i][0], pairs[i][1], source=label)
                n += 1
        print(c(f"  saved {n} cards", "green"))
        return

    # default: review session
    cards = study.due()
    if not cards:
        st = study.stats()
        if st["total"] == 0:
            print(c("  no cards yet — make some with /study gen <note> or /study add", "dim"))
        else:
            print(c(f"  nothing due today. {st['total']} cards, all scheduled ahead. ✓", "green"))
        return

    print(c(f"\n  {len(cards)} cards due. Enter reveals the answer; then rate a/g/e. q quits.\n", "dim"))
    GRADES = {"a": 0, "again": 0, "h": 3, "g": 4, "good": 4, "e": 5, "easy": 5, "": 4}
    reviewed = 0
    for card in cards:
        print(c(f"  Q: {card['front']}", "b"))
        try:
            r = input(c("     [enter to reveal, q to stop] ", "dim"))
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if r.strip().lower() == "q":
            break
        print(c(f"  A: {card['back']}", "cyan"))
        try:
            g = input(c("     rate  a)gain  g)ood  e)asy: ", "gold")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if g == "q":
            break
        study.grade(card["id"], GRADES.get(g, 4))
        reviewed += 1
        print()
    print(c(f"  reviewed {reviewed} card(s). {len(study.due())} still due.\n", "green"))


def do_brief(s):
    """One-shot morning briefing: date, tasks, mail, active gate, live sites.

    Composes what Jarvis already knows into the single command you'd run each
    morning. Every part degrades gracefully — a section that can't load is
    skipped, not fatal.
    """
    from datetime import date as _date
    print(c(f"\n  ┌─ BRIEFING · {_date.today():%A %d %B} " + "─" * 20, "cyan"))

    # tasks
    items = tasks.list_day()
    if items:
        done = sum(1 for t in items if t["done"])
        print(c(f"  │ TASKS  {done}/{len(items)} done", "b"))
        for t in items:
            if not t["done"]:
                print(c(f"  │   ○ {t['text']}", "dim"))
    else:
        print(c("  │ TASKS  none set — add with /t add <text>", "dim"))

    # active gate
    try:
        import roadmap
        rm = roadmap._load("roadmap.json")
        phases = rm.get("phases", []) if rm else []
        active = next((p for p in phases if p.get("status") == "active"), phases[0] if phases else None)
        if active:
            ms = active.get("milestones", [])
            nxt = next((m["text"] for m in ms if not m.get("done")), "all quests cleared")
            done = sum(1 for m in ms if m.get("done"))
            print(c(f"  │ GATE   {active['name']} ({done}/{len(ms)})", "b"))
            print(c(f"  │   next: {nxt}", "dim"))
    except Exception:
        pass

    # study — due flashcards
    try:
        import study
        d = len(study.due())
        if d:
            print(c(f"  │ STUDY  {d} cards due — run /study", "b"))
    except Exception:
        pass

    # mail
    try:
        import mail
        if mail.configured():
            n = mail.unread_count()
            print(c(f"  │ MAIL   {n} unread", "b"))
            if n:
                for m in mail.fetch(n=3, unread_only=True):
                    print(c(f"  │   • {m['from'][:22]}: {m['subject'][:44]}", "dim"))
    except Exception as e:
        print(c(f"  │ MAIL   couldn't check ({str(e)[:40]})", "dim"))

    # vercel liveness (from cache — fast; refresh with /vercel)
    try:
        import vercel
        live = vercel.liveness()
        if live:
            up = sum(1 for p in live if p["up"])
            print(c(f"  │ SITES  {up}/{len(live)} live", "b"))
            for p in live:
                if not p["up"]:
                    print(c(f"  │   ○ DOWN: {p['name']} {p['url']}", "red"))
    except Exception:
        pass

    print(c("  └" + "─" * 46, "cyan"))
    # a one-line nudge from the model, grounded in all of the above
    print(c("  jarvis ", "cyan"), end="", flush=True)
    s.brain.ask(
        "Give me a single sharp sentence to start the day — what's the one thing "
        "to focus on, based on my tasks and current gate. No preamble.",
        on_token=lambda t: print(t, end="", flush=True))
    print("\n")


def main():
    fast = "--fast" in sys.argv
    boot.boot(fast=fast)

    s = Session()
    n = tasks.carry_over()
    if n:
        print(c(f"  carried over {n} unfinished task(s)", "gold"))
    print(c(f"  {date.today():%A %d %B}", "dim"))
    show_tasks()
    print(c("  /help for commands", "dim") + "\n")

    while True:
        try:
            line = input(c("you ", "gold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue

        if line in ("/q", "/quit", "/exit"):
            break
        elif line == "/help":
            print(HELP)
        elif line == "/reset":
            s.brain.reset()
            print(c("  memory cleared", "dim"))
        elif line.startswith("/t"):
            handle_tasks(line[2:].strip())
        elif line.startswith("/vault"):
            handle_vault(s, line[6:].strip())
        elif line.startswith("/ask"):
            q = line[4:].strip()
            if q:
                handle_ask(s, q)
            else:
                print(c("  usage: /ask <question>", "dim"))
        elif line.startswith("/paper"):
            run_paper(s, line[6:].strip())
        elif line.startswith("/repo"):
            run_repo(s, line[5:].strip())
        elif line.startswith("/robot"):
            run_robot(s, line[6:].strip())
        elif line.startswith("/study"):
            run_study(s, line[6:].strip())
        elif line.startswith("/mail"):
            import mail
            if not mail.configured():
                print(c("  mail not set up — add MAIL_USER and MAIL_APP_PASSWORD to .env", "red"))
                print(c("  (Gmail app password: myaccount.google.com/apppasswords)", "dim"))
                continue
            arg = line[5:].strip()
            print(c("  ↗ checking mail (read-only)…", "dim"))
            try:
                msgs = mail.fetch(n=8, unread_only=(arg == "unread"))
            except Exception as e:
                print(c(f"  couldn't reach Gmail: {e}", "red"))
                continue
            if not msgs:
                print(c("  inbox empty" if arg != "unread" else "  no unread mail", "dim"))
                continue
            for m in msgs:
                print(f"  {c('•', 'cyan')} {c(m['from'][:26].ljust(26), 'b')} {m['subject'][:52]}")
                if m["snippet"]:
                    print(c(f"      {m['snippet'][:90]}", "dim"))
            if arg == "sum":
                digest = "\n".join(
                    f"- From {m['from']}: {m['subject']} — {m['snippet']}" for m in msgs)
                print()
                s.last_reply = stream_reply(
                    s.brain,
                    f"Here are my recent emails:\n{digest}\n\n"
                    "Summarize what needs my attention in 3-4 lines. Flag anything "
                    "time-sensitive. Don't invent senders or details.")
            else:
                print()
        elif line.startswith("/g "):
            run_gemini(s, line[3:].strip())
        elif line.startswith("/web"):
            q = line[4:].strip()
            if not q:
                print(c("  usage: /web <question>", "dim"))
                continue
            run_web(s, q)
        elif line.startswith("/find"):
            q = line[5:].strip()
            if not q or not s.vault:
                print(c("  usage: /find <query>", "dim"))
                continue
            hits = vault.search(s.vault, q)
            if not hits:
                print(c("  no matches", "dim"))
            for score, p, _ in hits:
                print(f"  {c(str(score).rjust(4), 'dim')}  {p.relative_to(s.vault)}")
            print()
        elif line.startswith("/note"):
            name = line[5:].strip()
            if not name or not s.vault:
                print(c("  usage: /note <name>", "dim"))
                continue
            rel, text = vault.read_note(s.vault, name)
            if not rel:
                print(c(f"  no note matching '{name}'", "red"))
            else:
                print(f"\n{c(str(rel), 'cyan')}\n{c('─' * 50, 'dim')}")
                print(text[:2500] + (c("\n  …truncated", "dim") if len(text) > 2500 else ""))
                print()
        elif line.startswith("/cap"):
            text = line[4:].strip()
            if not text or not s.vault:
                print(c("  usage: /cap <text>", "dim"))
                continue
            rel = vault.capture(s.vault, text)
            print(c(f"  captured → {rel}", "green"))
        elif line.startswith("/save"):
            title = line[5:].strip()
            if not title or not s.vault:
                print(c("  usage: /save <title>", "dim"))
                continue
            if not s.last_reply:
                print(c("  nothing to save yet", "dim"))
                continue
            rel = vault.write_note(s.vault, title, s.last_reply)
            if rel is None:
                print(c(f"  a note named '{title}' already exists — not overwriting", "red"))
            else:
                print(c(f"  saved → {rel}", "green"))
        elif line.startswith("/auto"):
            arg = line[5:].strip().lower()
            if arg in ("on", "off"):
                s.auto = (arg == "on")
                config.set_auto(s.auto)
            print(c(f"  auto tool-routing is {'ON' if s.auto else 'OFF'}"
                    + ("" if arg in ("on", "off") else "  — /auto on|off"), "dim"))
        elif line == "/brief":
            do_brief(s)
        elif line == "/vercel":
            import vercel
            print(c("  ↗ checking Vercel…", "dim"))
            projs = vercel.refresh()
            if not projs:
                print(c("  no projects found (is the vercel CLI logged in?)", "red"))
                continue
            for p in vercel.liveness(projs):
                dot = c("● up", "green") if p["up"] else c("○ down", "red")
                print(f"  {dot}  {c(p['name'].ljust(20), 'b')} {c(p['url'], 'dim')}")
            print()
        elif line == "/plan":
            s.last_reply = stream_reply(
                s.brain,
                f"{tasks.summary()}\n\nGiven these, what should I focus on today? "
                "Be specific and brief — pick an order and say why in one line each.")
        elif line.startswith("/img"):
            arg = line[4:].strip()
            if not arg:
                print(c("  usage: /img <path> [question]", "dim"))
                continue
            parts = arg.split(maxsplit=1)
            img, q = parts[0], (parts[1] if len(parts) > 1 else "What is in this image?")
            try:
                open(img, "rb").close()
            except OSError as e:
                print(c(f"  can't read {img}: {e}", "red"))
                continue
            print(c("  (7B vision model — slower, spills to CPU)", "dim"))
            s.last_reply = stream_reply(s.brain, q, images=[img])
        elif line.startswith("/v"):
            arg = line[2:].strip()
            secs = int(arg) if arg.isdigit() else 15
            import voice
            if not voice.mic_available():
                print(c("  no microphone found", "red"))
                continue
            print(c(f"  recording {secs}s — Ctrl-C to stop early…", "gold"))
            text, dur, took = voice.listen(secs)
            if not text:
                print(c("  (heard nothing)", "dim"))
                continue
            print(f"  {c('heard:', 'dim')} {text}  {c(f'[{took:.1f}s]', 'dim')}")
            s.last_reply = stream_reply(s.brain, text)
        else:
            run_auto(s, line)

    s.brain.save()
    print(c("saved. bye.", "dim"))


if __name__ == "__main__":
    main()
