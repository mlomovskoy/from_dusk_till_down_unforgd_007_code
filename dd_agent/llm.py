"""Minimal OpenAI Chat Completions client returning JSON."""
import json
import time

import httpx

from . import config


def chat_json(system: str, user: str, max_tokens: int = 4000) -> dict:
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
    last_error = None
    for attempt in range(3):
        try:
            r = httpx.post("https://api.openai.com/v1/chat/completions",
                           headers={"Authorization": f"Bearer {key}"}, json=body, timeout=180)
            if r.status_code in (429, 500, 502, 503):
                raise httpx.HTTPStatusError(r.text, request=r.request, response=r)
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"OpenAI call failed: {last_error}")
