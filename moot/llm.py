"""The one place Moot calls a language model: picking an answer tool and narrating an audit's rows.

Backend (MOOT_LLM): `groq` (GROQ_API_KEY, model MOOT_GROQ_MODEL, default openai/gpt-oss-120b), `anthropic`
(ANTHROPIC_API_KEY, model MOOT_MODEL) or `off`. Unset: Groq when its key is set, else Anthropic when its key is set, else
off. Off, or any failure, means the caller falls back to its rules or its template: verdicts never depend on a model.

Spend cap: every call is priced from the tokens the provider reports, and a call is refused before it is sent when the
day's spend plus a worst-case estimate for this call would pass MOOT_LLM_DAILY_USD (default 1.00). The running total is
kept in memory and, where the filesystem is writable, in MOOT_LLM_SPEND_FILE (default /tmp/moot_llm_spend.json), so
one serverless instance cannot spend more than the cap in a day. Set a hard limit in the provider's console as well:
a per-instance cap is not a per-account one.

Replay: with MOOT_LLM_CACHE pointing at a .jsonl file, each reply is recorded under a hash of (model, system, user,
tools); with MOOT_LLM_REPLAY=1 as well, only recorded replies are served and nothing is sent, which is how the tests
and the router eval run in CI.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# USD per million tokens (input, output), from groq.com/pricing; an unlisted model is priced high so the cap errs safe.
PRICES = {"openai/gpt-oss-120b": (0.15, 0.60), "openai/gpt-oss-20b": (0.075, 0.30), "qwen/qwen3.8-27b": (0.30, 0.90),
          "claude-sonnet-5-5": (3.0, 15.0), "claude-opus-5-5": (5.0, 25.0), "claude-haiku-5-5": (1.0, 5.0)}
UNLISTED = (5.0, 25.0)

_spend: dict = dict(day="", usd=0.0, calls=0, refused=0)


def _env_key(name: str) -> str | None:
    if os.getenv(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip() or None
    return None


def backend() -> str | None:
    choice = os.getenv("MOOT_LLM", "").lower()
    if choice == "off":
        return None
    if os.getenv("MOOT_LLM_REPLAY") == "1":
        return "groq" if choice in ("", "groq") else choice
    if choice in ("", "groq") and _env_key("GROQ_API_KEY"):
        return "groq"
    if choice in ("", "anthropic") and os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def model() -> str:
    if backend() == "anthropic":
        return os.getenv("MOOT_MODEL", "claude-sonnet-5-5")
    return os.getenv("MOOT_GROQ_MODEL", "openai/gpt-oss-120b")


def cap_usd() -> float:
    return float(os.getenv("MOOT_LLM_DAILY_USD", "1.00"))


def price(m: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICES.get(m, UNLISTED)
    return (tokens_in * pin + tokens_out * pout) / 1e6


def _spend_file() -> Path:
    return Path(os.getenv("MOOT_LLM_SPEND_FILE", "/tmp/moot_llm_spend.json"))


def spend() -> dict:
    """Today's spend for this instance: {day, usd, calls, refused, cap_usd}."""
    today = date.today().isoformat()
    if _spend["day"] != today:
        _spend.update(day=today, usd=0.0, calls=0, refused=0)
        try:
            saved = json.loads(_spend_file().read_text())
            if saved.get("day") == today:
                _spend.update(usd=float(saved["usd"]), calls=int(saved["calls"]), refused=int(saved.get("refused", 0)))
        except Exception:
            pass
    return dict(_spend, cap_usd=cap_usd())


def _record(cost: float, refused: bool = False) -> None:
    spend()
    if refused:
        _spend["refused"] += 1
    else:
        _spend["usd"] += cost
        _spend["calls"] += 1
    try:
        _spend_file().write_text(json.dumps(_spend))
    except Exception:
        pass


def _cache_key(m: str, system: str, user: str, tools: list | None) -> str:
    return hashlib.sha256(json.dumps([m, system, user, tools], sort_keys=True).encode()).hexdigest()[:24]


def _cache_read(key: str) -> dict | None:
    path = os.getenv("MOOT_LLM_CACHE")
    if not path or not Path(path).exists():
        return None
    for line in Path(path).read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            if row["key"] == key:
                return row["reply"]
    return None


def _cache_write(key: str, reply: dict) -> None:
    path = os.getenv("MOOT_LLM_CACHE")
    if path and os.getenv("MOOT_LLM_REPLAY") != "1":
        with open(path, "a") as f:
            f.write(json.dumps(dict(key=key, reply=reply), sort_keys=True) + "\n")


def chat(system: str, user: str, tools: list[dict] | None = None, max_tokens: int = 600, timeout: float = 20) -> dict | None:
    """One model call. tools: [{name, description, parameters (JSON schema)}]; with tools the model must call one.
    Returns {text, tool: {name, input} | None, model, tokens_in, tokens_out, usd, ms, cached} or None (off, over the
    cap, or failed): the caller then uses its rules."""
    b = backend()
    if b is None:
        return None
    m = model()
    key = _cache_key(m, system, user, tools)
    hit = _cache_read(key)
    if hit is not None:
        return dict(hit, cached=True, usd=0.0)
    if os.getenv("MOOT_LLM_REPLAY") == "1":
        return None
    worst = price(m, (len(system) + len(user) + len(json.dumps(tools or []))) // 3, max_tokens)
    if spend()["usd"] + worst > cap_usd():
        _record(0.0, refused=True)
        return None
    t0 = time.perf_counter()
    try:
        out = _groq(m, system, user, tools, max_tokens, timeout) if b == "groq" else _anthropic(m, system, user, tools, max_tokens)
    except Exception:
        return None
    out.setdefault("ms", round((time.perf_counter() - t0) * 1000))
    out.update(model=m, usd=price(m, out["tokens_in"], out["tokens_out"]))
    _record(out["usd"])
    _cache_write(key, {k: v for k, v in out.items() if k != "usd"})
    return dict(out, cached=False)


def _groq(m: str, system: str, user: str, tools: list | None, max_tokens: int, timeout: float) -> dict:
    body: dict = dict(model=m, temperature=0, seed=7, max_tokens=max_tokens,
                      messages=[dict(role="system", content=system), dict(role="user", content=user)])
    if tools:
        body["tools"] = [dict(type="function", function=t) for t in tools]
        body["tool_choice"] = "required"
    if m.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    # A rate limit (429) is waited out only when the wait is short, or always under MOOT_LLM_PATIENT=1 (the evals);
    # a user's question would rather fall back to the rules than wait.
    patient = os.getenv("MOOT_LLM_PATIENT") == "1"
    for attempt in range(8 if patient else 2):
        req = urllib.request.Request(GROQ_URL, data=json.dumps(body).encode(), headers={
            "content-type": "application/json", "authorization": f"Bearer {_env_key('GROQ_API_KEY')}", "user-agent": "moot"})
        t0 = time.perf_counter()
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            ms = round((time.perf_counter() - t0) * 1000)  # the request that answered, not the rate-limit waits before it
            break
        except urllib.error.HTTPError as e:
            wait = float(e.headers.get("retry-after") or 5)
            if e.code != 429 or (not patient and wait > 3) or attempt == (7 if patient else 1):
                raise
            time.sleep(wait)
    msg = r["choices"][0]["message"]
    call = (msg.get("tool_calls") or [None])[0]
    tool = None
    if call:
        try:
            tool = dict(name=call["function"]["name"], input=json.loads(call["function"].get("arguments") or "{}"))
        except json.JSONDecodeError:
            tool = None
    u = r.get("usage") or {}
    return dict(text=(msg.get("content") or "").strip(), tool=tool, tokens_in=int(u.get("prompt_tokens", 0)),
                tokens_out=int(u.get("completion_tokens", 0)), ms=ms)


def _anthropic(m: str, system: str, user: str, tools: list | None, max_tokens: int) -> dict:
    import anthropic
    kw: dict = dict(model=m, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    if tools:
        kw["tools"] = [dict(name=t["name"], description=t["description"], input_schema=t["parameters"]) for t in tools]
        kw["tool_choice"] = {"type": "any"}
    resp = anthropic.Anthropic().messages.create(**kw)
    if resp.stop_reason == "refusal":
        raise RuntimeError("refused")
    call = next((b for b in resp.content if b.type == "tool_use"), None)
    return dict(text="".join(b.text for b in resp.content if b.type == "text").strip(),
                tool=dict(name=call.name, input=dict(call.input or {})) if call else None,
                tokens_in=resp.usage.input_tokens, tokens_out=resp.usage.output_tokens)
