"""Thin async client for the Groq API (free tier, OpenAI-compatible)."""
import asyncio
import json
import re

import httpx

from . import config


class LLMError(Exception):
    pass


def available() -> bool:
    return config.groq_ready()


async def _call(messages: list, json_mode: bool, temperature: float, max_tokens: int) -> str:
    if not available():
        raise LLMError("GROQ_API_KEY is not set")
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as client:
        last_err = "unknown error"
        for attempt in range(3):
            try:
                r = await client.post(config.GROQ_URL, headers=headers, json=payload)
            except httpx.HTTPError as e:
                last_err = f"network error: {e}"
                await asyncio.sleep(1.5)
                continue
            if r.status_code == 429:  # free-tier rate limit -> wait and retry
                last_err = "Groq rate limit"
                await asyncio.sleep(2 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise LLMError(f"Groq error {r.status_code}: {r.text[:200]}")
            return r.json()["choices"][0]["message"]["content"]
    raise LLMError(last_err)


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise LLMError("Model did not return valid JSON")


async def chat_json(system: str, user: str, max_tokens: int = 1200) -> dict:
    """Ask the model for a JSON object. (The word 'JSON' must appear in the prompt.)"""
    raw = await _call(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True, temperature=0.1, max_tokens=max_tokens,
    )
    return _parse_json(raw)


async def chat_text(system: str, user: str, max_tokens: int = 400, temperature: float = 0.5) -> str:
    return (await _call(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=False, temperature=temperature, max_tokens=max_tokens,
    )).strip()
