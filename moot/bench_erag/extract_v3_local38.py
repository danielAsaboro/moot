"""rules-v3-llm on a local qwen3.8:27b, POST-HOC: v3's prompt and v3's pairing rules, unchanged, with the model swapped.

Same model family as v3-groq, run on this machine through ollama (ollama's nvfp4 MLX build, temperature 0, seed 7, thinking off, the
same 700-token answer cap and 6K context as v3). Ollama has no structured output for this model, so the reply is
parsed as JSON after stripping any code fence, instead of ollama's JSON mode. Quantization differs from Groq's, so it is its own labelled arm.
Still blind: the model sees question text and document text only, and it never decides what to drop.
Responses are cached by prompt hash in erag-data/v3_local38_cache.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

from moot.bench_erag import DATA
from moot.bench_erag import extract_v3 as v3

EXTRACTOR_VERSION = "rules-v3-llm-posthoc+qwen3.8-local"
MODEL = os.getenv("MOOT_ERAG_V3_LOCAL38_MODEL", "qwen3.8:27b")
ENDPOINT = os.getenv("MOOT_ERAG_OLLAMA", "http://localhost:11434/api/chat")
CACHE = DATA / "v3_local38_cache"


def cache_path(prompt: str):
    return CACHE / f"{hashlib.sha256(('ollama:' + MODEL + chr(10) + prompt).encode()).hexdigest()}.json"


def ask(prompt: str) -> dict:
    path = cache_path(prompt)
    if path.exists():
        return json.loads(path.read_text())
    body = json.dumps(dict(model=MODEL, stream=False, think=False,
                           options=dict(temperature=0, seed=7, num_ctx=6144, num_predict=700),
                           messages=[dict(role="user", content=prompt)])).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    for attempt in range(4):   # ollama's MLX runner can drop a request on a transient Metal GPU error; retry it
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 3:
                raise
            time.sleep(15)
    raw = resp["message"]["content"]
    try:
        out = json.loads(re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw))
    except json.JSONDecodeError:
        out = {"docs": [], "unparsed": raw[:2000]}
    if isinstance(out, list):   # the model sometimes returns the docs array without its {"docs": ...} wrapper
        out = {"docs": out, "bare_list": True}
    elif not isinstance(out, dict):
        out = {"docs": [], "unparsed": raw[:2000]}
    out["_usage"] = dict(prompt_tokens=resp.get("prompt_eval_count"), completion_tokens=resp.get("eval_count"),
                         seconds=round(resp.get("total_duration", 0) / 1e9, 1))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def edges(question: str, docs: dict[str, str]) -> list:
    """v3.edges with v3's prompt and rules; only the model call differs."""
    real = v3.ask
    v3.ask = ask
    try:
        return v3.edges(question, docs)
    finally:
        v3.ask = real
