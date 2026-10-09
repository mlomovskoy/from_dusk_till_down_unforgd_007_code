"""LLM step: one function, chat_json(system, user) -> dict, with selectable backends.

DD_LLM selects the backend:
  claude-cli  (default) local Claude Code CLI:  claude -p --output-format json   (no API key)
  grok-cli    local Grok CLI:                   agent --single <prompt>          (no API key)
  openai      OpenAI Chat Completions over REST (needs OPENAI_API_KEY)
Every backend must yield one JSON object; it is extracted from the reply, so code fences or extra text
around it are tolerated.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import httpx

from . import config

BACKENDS = ("claude-cli", "grok-cli", "openai")
CLI_TOOLS = {"claude-cli": "claude", "grok-cli": "agent"}
TIMEOUT = 240
JSON_ONLY = "\n\nReply with ONE JSON object only. No prose, no code fences."


def backend() -> str:
    return config.llm_backend()


def available() -> tuple[bool, str]:
    """(usable, reason) for the selected backend, without calling it."""
    name = backend()
    if name not in BACKENDS:
        return False, f"unknown DD_LLM '{name}' (choose {', '.join(BACKENDS)})"
    if name == "openai":
        return (True, "openai") if config.openai_key() else (False, "OPENAI_API_KEY is not set")
    tool = CLI_TOOLS[name]
    return (True, f"{name} ({shutil.which(tool)})") if shutil.which(tool) else (False, f"'{tool}' CLI not found")


def extract_json(text: str) -> dict:
    """Return the first complete JSON object in text (tolerates fences and surrounding prose)."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in reply")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("reply JSON is not an object")
    return obj


def _claude_cli(system: str, user: str) -> str:
    cmd = ["claude", "-p", "--output-format", "json", "--system-prompt", system + JSON_ONLY,
           "--disallowedTools", "Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebFetch", "WebSearch"]
    if model := os.getenv("DD_CLAUDE_MODEL"):
        cmd += ["--model", model]
    with tempfile.TemporaryDirectory() as tmp:  # no project instructions are loaded from here
        r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=TIMEOUT, cwd=tmp)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    envelope = json.loads(r.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude CLI error: {str(envelope.get('result'))[:300]}")
    return envelope.get("result", "")


def _grok_cli(system: str, user: str) -> str:
    # `agent -p/--single <PROMPT>` takes the prompt text as its argument (well under ARG_MAX for our prompts).
    prompt = f"{system}{JSON_ONLY}\n\n{user}"
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["agent", "--single", prompt, "--output-format", "plain"],
                           capture_output=True, text=True, timeout=TIMEOUT, cwd=tmp)
    if r.returncode != 0:
        raise RuntimeError(f"grok CLI exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    return r.stdout


def _openai(system: str, user: str, max_tokens: int) -> str:
    key = config.openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    body = {
        "model": config.openai_model(),
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    r = httpx.post("https://api.openai.com/v1/chat/completions",
                   headers={"Authorization": f"Bearer {key}"}, json=body, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def chat_json(system: str, user: str, max_tokens: int = 4000) -> dict:
    name = backend()
    call = {"claude-cli": lambda: _claude_cli(system, user),
            "grok-cli": lambda: _grok_cli(system, user),
            "openai": lambda: _openai(system, user, max_tokens)}.get(name)
    if call is None:
        raise RuntimeError(f"unknown DD_LLM '{name}'")
    last_error = None
    for attempt in range(3):
        try:
            return extract_json(call())
        except (RuntimeError, ValueError, json.JSONDecodeError, httpx.HTTPError, subprocess.TimeoutExpired) as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call via {name} failed: {last_error}")
