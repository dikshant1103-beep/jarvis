#!/usr/bin/env bash
# Starts Ollama if it isn't already up, then launches Jarvis.
cd "$(dirname "$0")"
if ! curl -s -o /dev/null http://localhost:11434/api/tags; then
  echo "starting ollama…"
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  until curl -s -o /dev/null http://localhost:11434/api/tags; do sleep 1; done
fi
exec .venv/bin/python jarvis.py
