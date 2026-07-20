"""Ollama client — streaming chat with a rolling context window."""
import json
import base64
import httpx
import config


class Brain:
    def __init__(self, model=config.TEXT_MODEL):
        self.model = model
        self.history = []

    def _messages(self, user_text):
        # Rebuilt each turn so an edit to profile.md or a dashboard push shows
        # up without restarting — cheap, it's just reading two small files.
        msgs = [{"role": "system", "content": config.build_system_prompt()}]
        # Only the last N exchanges: a 3B model loses the thread on long context.
        msgs += self.history[-config.CONTEXT_TURNS * 2:]
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def ask(self, user_text, on_token=None, images=None):
        """Streams the reply. Returns the full text; calls on_token per chunk."""
        msgs = self._messages(user_text)
        if images:
            msgs[-1]["images"] = [
                base64.b64encode(open(p, "rb").read()).decode() for p in images
            ]
        payload = {
            "model": config.VISION_MODEL if images else self.model,
            "messages": msgs,
            "stream": True,
            "options": {"temperature": 0.6, "num_ctx": 8192},
        }
        out = []
        try:
            with httpx.stream("POST", f"{config.OLLAMA}/api/chat",
                              json=payload, timeout=180) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    tok = chunk.get("message", {}).get("content", "")
                    if tok:
                        out.append(tok)
                        if on_token:
                            on_token(tok)
                    if chunk.get("done"):
                        break
        except httpx.ConnectError:
            msg = "[Ollama isn't running. Start it with:  ollama serve]"
            if on_token:
                on_token(msg)
            return msg
        except httpx.HTTPStatusError as e:
            msg = f"[Ollama error {e.response.status_code}: {e.response.text[:200]}]"
            if on_token:
                on_token(msg)
            return msg

        reply = "".join(out)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def complete(self, prompt, max_tokens=200, on_token=None, timeout=120):
        """One-shot completion — no history, no system prompt.

        Deliberately isolated from the conversation: the answer must depend
        only on the prompt, and a throwaway turn (a classification, a summary
        of someone else's abstract) must not pollute the chat memory.
        """
        payload = {
            "model": self.model, "prompt": prompt, "stream": bool(on_token),
            "options": {"temperature": 0, "num_predict": max_tokens},
        }
        url = f"{config.OLLAMA}/api/generate"
        if not on_token:
            r = httpx.post(url, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json().get("response", "")

        out = []
        with httpx.stream("POST", url, json=payload, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                tok = chunk.get("response", "")
                if tok:
                    out.append(tok)
                    on_token(tok)
                if chunk.get("done"):
                    break
        return "".join(out)

    def classify(self, prompt, max_tokens=5):
        """Router hook — a one-word answer, kept on a short leash."""
        return self.complete(prompt, max_tokens=max_tokens, timeout=20)

    def reset(self):
        self.history.clear()

    def save(self):
        config.HISTORY_FILE.write_text(json.dumps(self.history, indent=1))

    def load(self):
        if config.HISTORY_FILE.exists():
            try:
                self.history = json.loads(config.HISTORY_FILE.read_text())
            except json.JSONDecodeError:
                self.history = []
