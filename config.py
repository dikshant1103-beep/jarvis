"""Jarvis config — everything runs locally, nothing leaves this laptop."""
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

OLLAMA = "http://localhost:11434"

# Fits entirely in the 1650 Ti's 4 GB, ~60 tok/s. The 7B vision model is
# kept for images only — it spills to CPU and is far too slow to chat with.
TEXT_MODEL = "qwen2.5:3b"
VISION_MODEL = "qwen2.5vl:7b"

# CPU int8 so the GPU stays free for the LLM. Ryzen 4600H has 12 threads.
WHISPER_MODEL = "base.en"
WHISPER_THREADS = 8

TASKS_FILE = DATA / "tasks.json"
HISTORY_FILE = DATA / "history.json"
JOURNAL_FILE = DATA / "journal.md"

# Keep the last N exchanges in context — 3B models degrade fast on long histories.
CONTEXT_TURNS = 8

BASE_RULES = """You are Jarvis, a local assistant running on Dikshant's laptop.
Everything about him and his plan below is real, current context — use it.

How to answer:
- Be direct and concrete. Skip preamble and flattery.
- Short answers for short questions. Depth only when the question needs it.
- You are a study partner, not a cheerleader. If he is avoiding the hard
  thing, say so plainly.
- When you don't know, say you don't know. Never invent a citation, a
  library, an API, or a number.
- When he asks what to do next, use the ROADMAP below — name the concrete
  next step, don't hand him a menu.
"""

PROFILE_FILE = ROOT / "profile.md"
PROJECTS_FILE = ROOT / "projects.md"


def build_system_prompt():
    """Assembled fresh each launch: base rules + your profile + live roadmap.

    This is the grounding that makes Jarvis 'know' the plan — it's the same
    dashboard data that drives the website, plus the profile.md you control.
    Editing either file changes Jarvis with no code and no retraining.
    """
    parts = [BASE_RULES]
    if PROFILE_FILE.exists():
        parts.append("--- PROFILE (how Dikshant wants to be helped) ---\n"
                     + PROFILE_FILE.read_text().strip())
    if PROJECTS_FILE.exists():
        parts.append("--- MY SOFTWARE (things Dikshant has built) ---\n"
                     + PROJECTS_FILE.read_text().strip())
    try:
        import roadmap
        snap = roadmap.snapshot()
        if snap:
            parts.append("--- " + snap)
    except Exception:
        pass
    return "\n\n".join(parts)


# Kept for anything importing the old constant; the live version is the function.
SYSTEM_PROMPT = BASE_RULES


# ---- Obsidian ----
# Which vault Jarvis reads. Defaults to whichever one Obsidian has open.
# Override by writing a path into data/vault.txt (or use /vault in the CLI).
VAULT_PIN = DATA / "vault.txt"


def vault_path():
    if VAULT_PIN.exists():
        p = VAULT_PIN.read_text().strip()
        if p and Path(p).is_dir():
            return p
    return None


def pin_vault(path):
    VAULT_PIN.write_text(str(path))


# Extra vaults searched by /ask and /find but never written to. This is how
# Jarvis reads the project brain without being able to scribble on it —
# captures and saved notes still land in the one active vault.
REFERENCE_PIN = DATA / "reference_vaults.txt"


def reference_vaults():
    if not REFERENCE_PIN.exists():
        return []
    out = []
    for line in REFERENCE_PIN.read_text().splitlines():
        p = line.strip()
        if p and Path(p).is_dir():
            out.append(Path(p))
    return out


def set_reference_vaults(paths):
    REFERENCE_PIN.write_text("\n".join(str(p) for p in paths))


# ---- auto tool-routing ----
# On by default: a plain sentence picks its own tool. Off falls back to plain
# chat for anything that isn't an explicit /command.
AUTO_PIN = DATA / "auto.txt"


def auto_route():
    if AUTO_PIN.exists():
        return AUTO_PIN.read_text().strip() != "off"
    return True


def set_auto(on):
    AUTO_PIN.write_text("on" if on else "off")


# ---- Gemini (optional, cloud) ----
# The one cloud brain. Key lives in .env (gitignored), never in code.
# gemini-flash-latest is an alias Google keeps pointed at the current Flash
# model, so it won't go stale.
GEMINI_MODEL = "gemini-flash-latest"


def _load_env():
    f = ROOT / ".env"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def gemini_key():
    return _load_env().get("GEMINI_API_KEY", "")
