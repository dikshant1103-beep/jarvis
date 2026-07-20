"""Pick the right tool automatically, so you stop typing commands.

The commands still work and still win — this only decides what to do with a
plain sentence. Two stages:

  1. Keyword rules. Cheap, instant, and unambiguous ("paper on X", "github
     repo for Y"). Most real questions land here.
  2. A constrained classifier on the local 3B, but only when the rules are
     silent AND the question actually smells like it needs a tool.

Deliberately biased toward `local`. A wrong route costs a slow network round
trip and a worse answer; a missed route costs one typed command. So anything
the rules don't recognise and the classifier isn't confident about is just a
normal chat turn.
"""
import re

TOOLS = ("paper", "repo", "web", "gemini", "vault", "local")

# Stage 1 — explicit, high-confidence signals. First match wins, so order
# matters: "paper" and "repo" are checked before the vaguer web/vault rules.
_RULES = [
    ("paper", r"\b(arxiv|paper|papers|publication|preprint|literature|"
              r"cite|citation|survey on|sota|state of the art)\b"),
    ("repo", r"\b(repo|repository|github|open ?source|codebase|"
             r"implementation of|clone|library for)\b"),
    ("vault", r"\b(my notes?|in my (vault|brain|notes)|did i (write|note|save)|"
              r"what did i (say|learn|note)|remind me what|my note on)\b"),
    ("web", r"\b(latest|news|today|current|right now|price|release[ds]?|"
            r"version|changelog|who won|weather|as of|202[6-9]|announced)\b"),
    ("gemini", r"\b(derive|prove|proof|explain in depth|deep dive|"
               r"trade-?offs?|design (a|the) |architect|why does|"
               r"step by step|walk me through the math)\b"),
]

# Questions that clearly need no tool: chit-chat, or things about the local
# state Jarvis already has in its system prompt.
_LOCAL = re.compile(
    r"\b(hi|hello|hey|thanks|thank you|good (morning|night)|"
    r"my tasks?|my gate|my roadmap|what should i|how am i doing|"
    r"summari[sz]e (that|this)|rewrite|shorter|again|continue)\b", re.I)

_CLASSIFY = """Classify the user's question into exactly one category.

paper  - wants academic papers or research literature
repo   - wants to find source code or a GitHub project
web    - needs current facts from the internet (news, versions, prices)
gemini - a hard reasoning, maths or design question needing a big model
vault  - asks about the user's own saved notes
local  - anything else: chat, opinions, writing, coding help, explanations

Answer with one word from that list and nothing else.

Question: {q}
Category:"""


def route(question, brain=None, use_model=True):
    """Return (tool, why). `tool` is one of TOOLS."""
    q = question.strip()
    low = q.lower()

    if _LOCAL.search(low):
        return "local", "conversational"

    for tool, pattern in _RULES:
        m = re.search(pattern, low)
        if m:
            return tool, f"matched '{m.group(0)}'"

    # Stage 2 — only bother the model for things shaped like a real question.
    # Short fragments and statements are almost always chat.
    if not (use_model and brain and len(q.split()) >= 4 and
            ("?" in q or low.split()[0] in
             ("what", "who", "when", "where", "why", "how", "which", "find",
              "search", "look", "show", "get", "is", "are", "does", "can"))):
        return "local", "no tool signal"

    try:
        raw = brain.classify(_CLASSIFY.format(q=q), max_tokens=5)
    except Exception:
        return "local", "classifier unavailable"

    word = re.sub(r"[^a-z]", "", (raw or "").strip().lower().split("\n")[0])
    if word in TOOLS and word != "local":
        return word, "model chose it"
    return "local", "model saw no tool need"
