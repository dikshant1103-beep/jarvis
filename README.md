# Jarvis — a local assistant

A study partner that runs on your own laptop. The model, the speech
recognition and the memory are all local — sized deliberately for a 4 GB
laptop GPU, not a datacentre. Nothing leaves the machine unless you invoke one
of the handful of commands that reach the network, and it says so when it does.

    ./run.sh            # boot animation
    ./run.sh --fast     # skip straight to the prompt

Any keypress during the boot skips the animation. The ten boot checks are
real — each one queries the actual subsystem, so a red line means something
genuinely is not working.

## Setup

Needs [Ollama](https://ollama.com) and Python 3.10+.

    ollama pull qwen2.5:3b                  # the chat model, 1.9 GB
    python3 -m venv .venv
    .venv/bin/pip install httpx faster-whisper ddgs
    cp profile.example.md profile.md        # then edit — this is the big lever
    cp projects.example.md projects.md      # optional: teach it your own work
    ./run.sh

`profile.md` is worth ten minutes of your time. It's how the assistant learns
your level, your goals and how blunt you want it to be, and it's read fresh
every launch — no retraining, just edit the file.

Optional extras, all off unless you configure them: a Gemini key for harder
reasoning (`/g`), Gmail app-password for read-only mail (`/mail`), and
`qwen2.5vl:7b` for images (`/img`).

## What's inside

- **Ollama + `qwen2.5:3b`** — the chat model. 1.9 GB, fits fully in the GTX
  1650 Ti's 4 GB VRAM, ~60 tokens/sec once warm.
- **`qwen2.5vl:7b`** — vision, for `/img` only. It does *not* fit in VRAM and
  spills to CPU, so it's slow. Use it deliberately, not for chat.
- **faster-whisper `base.en`** — speech, on CPU int8 so the GPU stays free for
  the model.

## Obsidian

Jarvis is pinned to its brain vault (`~/Desktop/Jarvis_Brain`). `/vault` lists
every vault Obsidian knows about and `/vault <n>` switches to another — e.g. to
read your Motorbike project notes. The choice is remembered.

**It cannot damage your notes.** Existing notes are read-only — Jarvis never
edits or overwrites one. It writes only into `00-Daily/` and `01-Concepts/`,
refuses to overwrite even its own notes, and sanitises titles so nothing can
escape those folders.

## The brain — how Jarvis remembers

Jarvis writes to a dedicated Obsidian vault at `~/Desktop/Jarvis_Brain` (open
it in Obsidian directly — it's registered). Everything you capture or save
lands there as plain Markdown and stays:

- **00-Daily/** — `/cap <text>` appends to today's note
- **01-Concepts/** — `/save <title>` saves the last reply; link notes with
  `[[brackets]]` and Obsidian's graph shows the connections
- `/ask` searches across the whole brain and answers grounded in it, telling
  you which notes it read — that's how it "connects the dots"

The more you put in, the better the recall. It never edits or overwrites an
existing note.

## What Jarvis knows about your plan

The system prompt is assembled fresh each launch from three sources:

1. **Base rules** — how to answer (in `config.py`)
2. **`profile.md`** — who you are and how you want help. **Edit this file** to
   tune Jarvis to you; no code, no retraining.
3. **`projects.md`** — the software you've built, so it can answer "how does X
   work" or "what have I made". Edit it as you ship new things.
4. **Live roadmap** — read straight from `~/Desktop/zero_to_robot/data/`, so it
   knows your active gate, open quests, current book, and latest log entry.
   Push to the dashboard and Jarvis sees it next launch.

## Dashboard write-back

`/robot` edits your live Zero → Robot dashboard by talking to Jarvis. It's
built so you can't fumble your public site:

- Edits are **local first** — they change `~/Desktop/zero_to_robot/data/*.json`
  and nothing more. `/robot` shows what's pending.
- **Nothing goes live until `/robot push`**, which shows the diff and asks
  y/N before committing and pushing. Vercel then redeploys in ~30s.
- `/robot revert` throws away local edits — the undo button.
- Commits use the required GitHub noreply email, and roadmap edits are done
  as a surgical one-line change so the diff stays clean.

Example: finish a chapter → `/robot read "modern robotics" 3` → `/robot push`
→ your site shows 3/13 chapters a moment later.

## Mail (read-only)

`/mail` reads your Gmail inbox — it can look, never touch. The mailbox is opened
read-only, so even viewing a message doesn't mark it read, and there's no code
that could send, delete, or move anything.

Setup (one time): Gmail needs an **app password** (not your real password).
With 2-Step Verification on, make one at **myaccount.google.com/apppasswords**,
then add two lines to `~/Desktop/jarvis/.env`:

    MAIL_USER=you@gmail.com
    MAIL_APP_PASSWORD=the16charapppassword

Like `/g` and `/web`, this reaches the network only when you run it.

## A note on privacy

Everything runs locally except the commands that reach out by design: `/web`
(DuckDuckGo + a few pages), `/g` (Gemini), `/mail`, `/vercel`, `/paper`,
`/repo`. Normal chat, `/ask`, tasks, and the brain never touch the network.

**One caveat with auto-routing on:** since a plain sentence can now route to
`/web` or `/g`, a sentence can leave the laptop without you typing a slash
command. The route is always printed before the request goes out, and
`/auto off` restores the old "nothing leaves unless I type it" behaviour.

`/web` is only as good as the pages it finds. It prefers official docs and
reputable sources and cites them inline, but a 3B model can still be misled by
a stale page — check the linked sources for anything that matters.

## Finding papers

`/paper <query>` searches arXiv itself — the model is never asked what a paper
is called. You get the real title, authors, year and link, then **one plain
line explaining each one**, so you can tell which is worth your evening
without opening six tabs. It ends with a `START:` pick.

Only that explanation comes from a model, and only from the abstract it was
handed. Gemini writes it when a key is set (it gets your profile, so "who it's
for" is aimed at you); otherwise the local model does, and if Gemini is down it
falls back silently. For the unparaphrased truth, `/paper abs <n>` prints the
real abstract straight from arXiv.

arXiv is slow (up to ~20s) and rate-limits rapid repeats — if it returns
nothing, wait a minute rather than assuming it's broken.

## Automatic tool-routing

You don't have to remember the commands. Just type the sentence — Jarvis picks
the tool itself and tells you which one it picked:

    you  find me papers on tactile sensing for grasping
      → /paper  (matched 'papers')
      ↗ searching arXiv…

Two stages, biased toward doing nothing clever: obvious keywords route
instantly ("arxiv/paper" → arXiv, "github/repo" → GitHub, "latest/news" → web,
"my notes" → vault, "derive/prove" → Gemini). Only if the rules are silent
*and* the sentence looks like a real question does the local 3B get asked to
classify it — and if it isn't confident, you get an ordinary chat reply.

That bias is deliberate: a wrong route costs a slow network trip and a worse
answer, a missed route costs you typing one command. **The route is always
printed**, so a bad pick is visible immediately and you can rerun with the
explicit command. Turn the whole thing off with `/auto off` (it's remembered).
Explicit `/commands` always win over routing.

## Commands

| Command | Does |
|---|---|
| *(just type)* | talk — the right tool is picked automatically |
| `/auto on\|off` | toggle automatic tool-routing (on by default) |
| `/v [secs]` | voice input, default 15s, Ctrl-C stops early |
| `/t` | today's tasks |
| `/t add <text>` | add a task |
| `/t done <n>` / `/t rm <n>` | toggle / remove |
| `/t carry` | pull unfinished tasks forward (also runs at startup) |
| `/img <path> [question]` | ask about an image |
| `/robot done <quest>` | mark a roadmap quest done (fuzzy-matched) |
| `/robot read <book> <n>` | set chapters read on a book |
| `/robot course <name> <%>` | set a course's progress |
| `/robot log <t> :: <b>` | add a raid-log entry |
| `/robot` / `/robot push` / `/robot revert` | pending changes / deploy / undo |
| `/brief` | morning briefing: tasks, mail, active gate, live sites + a nudge |
| `/vercel` | your Vercel projects — checks each production URL is live |
| `/plan` | plan the day around your task list |
| `/study` | review flashcards due today (spaced repetition) |
| `/study gen <note>` | generate cards from a brain note or topic |
| `/study add` / `/study stats` | add a card by hand / see counts |
| `/mail` | recent inbox, read-only (`/mail unread`, `/mail sum` to summarize) |
| `/ask <question>` | answer using your Obsidian notes |
| `/g <question>` | ask **Gemini** (cloud) — strong reasoning, knows your context |
| `/web <question>` | **search the internet**, answer with cited sources |
| `/paper <query>` | find papers on arXiv — real results, each explained in a line |
| `/paper abs <n>` | the paper's **real** abstract, verbatim from arXiv |
| `/paper get <n>` | download the PDF to `~/Desktop/papers/` |
| `/repo <name>` | find a GitHub repo — **verified via GitHub API, never guessed** |
| `/repo clone <n>` | clone a found repo to ~/Desktop + note it in the brain |
| `/find <query>` | search the vault |
| `/note <name>` | read a note |
| `/cap <text>` | append a line to today's daily note |
| `/save <title>` | save the last reply as a new note |
| `/vault [n]` | show / switch vault |
| `/reset` | clear conversation memory |
| `/q` | quit |

Tasks and history live in `data/` as plain JSON — readable, greppable, yours.

## When the new PC arrives

The GPU is the only real constraint. On a card with 12–24 GB you can swap
`TEXT_MODEL` in `config.py` for `qwen2.5:14b` or `qwen2.5:32b` and move
Whisper to `device="cuda"` with `compute_type="float16"`. Nothing else changes.
