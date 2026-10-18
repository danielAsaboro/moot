"""rules-v3-llm on Groq, POST-HOC: v3's prompt and v3's pairing rules, unchanged, with the model swapped.

Only `ask` differs from extract_v3: it calls Groq's OpenAI-compatible API (model MOOT_ERAG_V3_GROQ_MODEL, temperature 0,
JSON mode, the same 700-token answer cap) instead of a local ollama. Still blind: the model sees question text and
document text only, and it never decides what to drop.

The free tier is small (30 requests/min, 8K tokens/min, 1K requests/day, 200K tokens/day), so every call waits for
the per-minute token window, every response is cached by prompt hash in erag-data/v3_groq_cache, and a 429 that
names a daily limit raises DailyCap so a run can stop cleanly and resume tomorrow from the cache.
GROQ_API_KEY comes from the environment or moot/.env; it is never logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from moot.bench_erag import DATA, ROOT
from moot.bench_erag import extract_v3 as v3

EXTRACTOR_VERSION = "rules-v3-llm-posthoc+groq"
MODEL = os.getenv("MOOT_ERAG_V3_GROQ_MODEL", "qwen/qwen3.8-27b")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
CACHE = DATA / "v3_groq_cache"
MAX_TOKENS = 700
TPM = int(os.getenv("MOOT_GROQ_TPM", "8000"))
RPM = int(os.getenv("MOOT_GROQ_RPM", "30"))
_sent: list[tuple[float, int]] = []   # (time, tokens charged) in the last minute


class DailyCap(RuntimeError):
    """Groq refused for a per-day limit; nothing more can run until it resets."""


def key() -> str:
    if os.getenv("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    env = ROOT / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("GROQ_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("GROQ_API_KEY not set (environment or moot/.env)")


def cache_path(prompt: str):
    return CACHE / f"{hashlib.sha256(('groq:' + MODEL + chr(10) + prompt).encode()).hexdigest()}.json"


def estimate(prompt: str) -> int:
    return int(len(prompt) / 3.5) + MAX_TOKENS   # Groq charges the answer cap up front; measured ~3.7 chars a token


def throttle(cost: int) -> None:
    while True:
        now = time.time()
        _sent[:] = [(t, c) for t, c in _sent if now - t < 60]
        if sum(c for _, c in _sent) + cost <= TPM and len(_sent) < RPM:
            _sent.append((now, cost))
            return
        time.sleep(max(0.5, 60 - (now - _sent[0][0]) + 0.5))


def wait_seconds(err: urllib.error.HTTPError, body: str) -> float:
    if err.headers.get("retry-after"):
        return float(err.headers["retry-after"])
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", body)
    return (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else 20.0


def ask(prompt: str) -> dict:
    path = cache_path(prompt)
    if path.exists():
        return json.loads(path.read_text())
    body = json.dumps(dict(model=MODEL, temperature=0, seed=7, max_completion_tokens=MAX_TOKENS,
                           response_format={"type": "json_object"},
                           messages=[dict(role="user", content=prompt)])).encode()
    headers = {"Authorization": f"Bearer {key()}", "Content-Type": "application/json", "User-Agent": "moot-bench/1"}
    for attempt in range(8):
        throttle(estimate(prompt))
        try:
            with urllib.request.urlopen(urllib.request.Request(ENDPOINT, data=body, headers=headers), timeout=300) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if e.code == 429 and re.search(r"per day|\bRPD\b|\bTPD\b", text):
                raise DailyCap(re.sub(r"\s+", " ", text)[:300]) from None
            if e.code == 400 and "json_validate_failed" in text:
                # JSON mode rejected the model's output; cache it as unparsed, exactly like v3 does
                resp = {"choices": [{"message": {"content": json.loads(text)["error"].get("failed_generation", "")}}]}
                break
            if e.code in (429, 500, 502, 503) and attempt < 7:
                w = wait_seconds(e, text)
                print(f"groq {e.code}, waiting {w:.0f}s: {re.sub(chr(92) + 's+', ' ', text)[:200]}", file=sys.stderr, flush=True)
                time.sleep(w)
                continue
            raise RuntimeError(f"groq {e.code}: {text[:300]}") from None
    raw = resp["choices"][0]["message"]["content"] or ""
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = {"docs": [], "unparsed": raw[:2000]}
    out["_usage"] = resp.get("usage", {})
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def prompt_for(question: str, docs: dict[str, str]) -> str:
    """Exactly the prompt v3.edges sends (tests/test_erag.py checks the two agree)."""
    ids = list(docs)[:v3.TOP_K]
    rendered = "\n\n".join(f"[Document {i}]\n{v3.window(docs[d], question, v3.WINDOW)}" for i, d in enumerate(ids, 1))
    return v3.PROMPT.format(question=question, n=len(ids), docs=rendered)


def edges(question: str, docs: dict[str, str]) -> list:
    """v3.edges with v3's prompt and rules; only the model call is Groq's."""
    real = v3.ask
    v3.ask = ask
    try:
        return v3.edges(question, docs)
    finally:
        v3.ask = real
