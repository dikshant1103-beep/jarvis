"""Gemini — the optional cloud brain for hard questions.

Local qwen2.5:3b handles chat, notes, and tasks. When you want real
reasoning power, /gemini routes the question to Google's Gemini API instead.
The same profile + roadmap context is sent, so its answer is personal to you.

Cloud, not local: the question you ask leaves the laptop. Only when you invoke
it, never in the background.
"""
import json
import httpx
import config

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def available():
    return bool(config.gemini_key())


def ask(question, system=None, on_token=None):
    """Ask Gemini, streaming tokens via on_token. Returns full text.

    Streams over SSE so the answer appears as it's written, matching the local
    model's feel.
    """
    key = config.gemini_key()
    if not key:
        msg = "[No Gemini key — put GEMINI_API_KEY in ~/Desktop/jarvis/.env]"
        if on_token:
            on_token(msg)
        return msg

    body = {"contents": [{"parts": [{"text": question}]}]}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}

    url = f"{BASE}/{config.GEMINI_MODEL}:streamGenerateContent?alt=sse"
    out = []
    try:
        with httpx.stream(
            "POST", url,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body, timeout=90,
        ) as r:
            if r.status_code != 200:
                detail = r.read().decode()[:300]
                msg = f"[Gemini error {r.status_code}: {detail}]"
                if on_token:
                    on_token(msg)
                return msg
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                for cand in chunk.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        tok = part.get("text", "")
                        if tok:
                            out.append(tok)
                            if on_token:
                                on_token(tok)
    except httpx.HTTPError as e:
        msg = f"[Gemini unreachable: {e}]"
        if on_token:
            on_token(msg)
        return msg
    return "".join(out)
