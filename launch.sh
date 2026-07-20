#!/usr/bin/env bash
# Launched by the desktop icon. Ensures Ollama is up, then hands off to the CLI.
# Kept separate from run.sh so the .desktop file has one stable entry point.
cd "$(dirname "$0")" || exit 1

if ! curl -s -o /dev/null http://localhost:11434/api/tags 2>/dev/null; then
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -s -o /dev/null http://localhost:11434/api/tags 2>/dev/null && break
    sleep 1
  done
fi

exec .venv/bin/python jarvis.py

# When Jarvis exits, drop to a shell prompt so the window doesn't vanish
# mid-error — handled by the desktop entry's `bash -c "...; exec bash"`.
