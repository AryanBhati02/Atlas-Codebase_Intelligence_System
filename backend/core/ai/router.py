import asyncio
import json
import time
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Callable, Optional

import httpx

from core.logger import get_logger
from core.errors import ProviderUnavailableError
from core.ai.free_api import (
    call_groq,
    call_gemini,
    call_mistral,
    call_huggingface,
    is_exhausted,
    has_key,
    get_key,
    get_model,
    mark_exhausted,
    RateLimitError,
    ProviderError,
    reload_keys as _reload_provider_keys,
    reload_models as _reload_provider_models,
)

logger = get_logger("atlas.ai.router")

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
_ollama_model = "phi3:mini"
OLLAMA_MODEL = _ollama_model
OLLAMA_TIMEOUT = 90.0

_OLLAMA_OPTIONS = {
    "num_predict": 2000,
    "stop": ["\n\n\n", "---END---"],
}

_MAX_RATE_LIMIT_RETRIES = 2                                                

def get_ollama_model() -> str:
    return _ollama_model

def set_ollama_model(model: str) -> None:
    global _ollama_model, OLLAMA_MODEL
    _ollama_model = model
    OLLAMA_MODEL = model

PROVIDER_CHAIN: list[str] = ["ollama", "groq", "gemini", "mistral", "huggingface"]

_prefer_local: bool = True

_STATS_DB_PATH = Path(__file__).resolve().parent.parent.parent / "ai_stats.db"

_stats_lock = threading.Lock()

def _get_stats_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_STATS_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            latency_ms REAL NOT NULL,
            success INTEGER NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    return conn

def _log_stat(provider: str, latency_ms: float, success: bool) -> None:
    try:
        with _stats_lock:
            conn = _get_stats_db()
            conn.execute(
                "INSERT INTO provider_stats (provider, latency_ms, success, timestamp) VALUES (?, ?, ?, ?)",
                (provider, latency_ms, 1 if success else 0, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
    except Exception as e:
        logger.debug("Stats logging failed", extra={"provider": provider, "error": str(e)})

def get_provider_stats() -> dict[str, dict]:                          
    result: dict[str, dict] = {}                          
    try:
        conn = _get_stats_db()
        rows = conn.execute("""
            SELECT provider,
                   COUNT(*) as total,
                   SUM(success) as successes,
                   AVG(CASE WHEN success = 1 THEN latency_ms END) as avg_latency
            FROM provider_stats
            WHERE timestamp > datetime('now', '-24 hours')
            GROUP BY provider
        """).fetchall()
        conn.close()
        for row in rows:
            result[row[0]] = {
                "requests_today": row[1],
                "successes": row[2] or 0,
                "avg_latency_ms": round(row[3], 1) if row[3] else 0,
            }
    except Exception as e:
        logger.warning("Failed to read provider stats", extra={"error": str(e)})
    for p in PROVIDER_CHAIN:
        if p not in result:
            result[p] = {"requests_today": 0, "successes": 0, "avg_latency_ms": 0}
    return result

def clear_stats() -> None:
    try:
        conn = _get_stats_db()
        conn.execute("DELETE FROM provider_stats")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to clear stats", extra={"error": str(e)})

def set_prefer_local(prefer: bool) -> None:
    global _prefer_local
    _prefer_local = prefer

def get_prefer_local() -> bool:
    return _prefer_local

def get_ordered_providers() -> list[str]:
    if _prefer_local:
        return list(PROVIDER_CHAIN)
    chain = [p for p in PROVIDER_CHAIN if p != "ollama"]
    chain.append("ollama")
    return chain

def _is_provider_available(provider: str) -> bool:
    if provider == "ollama":
        return True
    if is_exhausted(provider):
        return False
    if not has_key(provider):
        return False
    return True

async def _call_ollama(prompt: str) -> str:
    model = get_ollama_model()
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": _OLLAMA_OPTIONS,
        })
        if resp.status_code == 200:
            text = resp.json().get("response", "")
            if text.strip():
                return text
            raise ProviderError("Ollama returned empty response")
        raise ProviderError(f"Ollama returned {resp.status_code}")

_CALLERS = {
    "ollama": _call_ollama,
    "groq": call_groq,
    "gemini": call_gemini,
    "mistral": call_mistral,
    "huggingface": call_huggingface,
}

async def _call_with_retry(provider: str, prompt: str) -> str:
    caller = _CALLERS.get(provider)
    if not caller:
        raise ProviderError(f"No caller registered for {provider}")

    last_exc: Exception = ProviderError(f"{provider} failed before first attempt")

    for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):           
        start = time.time()
        try:
            result = await caller(prompt)
            _log_stat(provider, (time.time() - start) * 1000, success=True)
            logger.info(
                "AI call succeeded",
                extra={"provider": provider, "duration_ms": round((time.time() - start) * 1000)},
            )
            return result
        except RateLimitError as exc:
            _log_stat(provider, (time.time() - start) * 1000, success=False)
            last_exc = exc
            if attempt < _MAX_RATE_LIMIT_RETRIES:
                wait_secs = 2 ** attempt          
                logger.warning(
                    "Rate limit hit — retrying",
                    extra={"provider": provider, "attempt": attempt + 1, "wait_secs": wait_secs},
                )
                await asyncio.sleep(wait_secs)
            else:
                mark_exhausted(provider)
                logger.warning(
                    "Provider exhausted after retries",
                    extra={"provider": provider},
                )
                raise ProviderUnavailableError(f"{provider} is rate-limited and exhausted") from exc
        except ProviderError as exc:
            _log_stat(provider, (time.time() - start) * 1000, success=False)
            logger.debug("Provider error", extra={"provider": provider, "error": str(exc)})
            raise
        except Exception as exc:
            _log_stat(provider, (time.time() - start) * 1000, success=False)
            logger.warning("Unexpected provider error", extra={"provider": provider, "error": str(exc)})
            raise ProviderError(str(exc)) from exc

    raise ProviderUnavailableError(f"{provider} failed all attempts") from last_exc

async def route_prompt(prompt: str) -> tuple[Optional[str], str]:
    chain = get_ordered_providers()
    errors: list[str] = []

    for provider in chain:
        if not _is_provider_available(provider):
            continue
        try:
            result = await _call_with_retry(provider, prompt)
            return result, provider
        except ProviderUnavailableError:
            errors.append(f"{provider}: exhausted")
            continue
        except ProviderError as e:
            errors.append(f"{provider}: {e}")
            continue
        except Exception as e:
            errors.append(f"{provider}: {e}")
            continue

    logger.error("All AI providers failed", extra={"errors": errors})
    raise ProviderUnavailableError(
        f"All providers failed: {'; '.join(errors)}"
    )

async def _stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
    model = get_ollama_model()
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        async with client.stream(
            "POST", OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "options": _OLLAMA_OPTIONS,
            },
        ) as resp:
            if resp.status_code != 200:
                raise ProviderError(f"Ollama returned {resp.status_code}")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        return
                except json.JSONDecodeError:
                    continue

async def _stream_groq(prompt: str) -> AsyncGenerator[str, None]:
    key = get_key("groq")
    if not key:
        raise ProviderError("Groq API key not configured")
    async with httpx.AsyncClient(timeout=90.0) as client:
        async with client.stream(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": get_model("groq"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.3,
                "stream": True,
            },
        ) as resp:
            if resp.status_code == 429:
                mark_exhausted("groq")
                raise RateLimitError("Groq rate limited")
            if resp.status_code != 200:
                text = await resp.aread()
                raise ProviderError(f"Groq returned {resp.status_code}: {text[:120]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    return
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

async def _stream_gemini(prompt: str) -> AsyncGenerator[str, None]:
    key = get_key("gemini")
    if not key:
        raise ProviderError("Gemini API key not configured")
    model = get_model("gemini")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
    async with httpx.AsyncClient(timeout=90.0) as client:
        async with client.stream(
            "POST", url,
            params={"key": key, "alt": "sse"},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500},
            },
        ) as resp:
            if resp.status_code == 429:
                mark_exhausted("gemini")
                raise RateLimitError("Gemini rate limited")
            if resp.status_code != 200:
                raise ProviderError(f"Gemini returned {resp.status_code}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts") or []
                        if parts:
                            text = parts[0].get("text", "")
                            if text:
                                yield text
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue

async def _stream_mistral(prompt: str) -> AsyncGenerator[str, None]:
    key = get_key("mistral")
    if not key:
        raise ProviderError("Mistral API key not configured")
    async with httpx.AsyncClient(timeout=90.0) as client:
        async with client.stream(
            "POST",
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": get_model("mistral"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.3,
                "stream": True,
            },
        ) as resp:
            if resp.status_code == 429:
                mark_exhausted("mistral")
                raise RateLimitError("Mistral rate limited")
            if resp.status_code != 200:
                raise ProviderError(f"Mistral returned {resp.status_code}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    return
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

async def _stream_huggingface(prompt: str) -> AsyncGenerator[str, None]:
    result = await call_huggingface(prompt)
    if result:
        yield result

StreamCaller = Callable[[str], AsyncGenerator[str, None]]

_STREAM_CALLERS: dict[str, StreamCaller] = {
    "ollama": _stream_ollama,
    "groq": _stream_groq,
    "gemini": _stream_gemini,
    "mistral": _stream_mistral,
    "huggingface": _stream_huggingface,
}

async def route_stream(prompt: str) -> AsyncGenerator[str, None]:
    chain = get_ordered_providers()

    for provider in chain:
        if not _is_provider_available(provider):
            continue

        streamer = _STREAM_CALLERS.get(provider)
        if not streamer:
            continue

        logger.info("Attempting stream", extra={"provider": provider})
        start = time.time()
        chunks_sent = 0

        try:
            async for chunk in streamer(prompt):                            
                yield chunk
                chunks_sent += 1

            _log_stat(provider, (time.time() - start) * 1000, success=True)
            logger.info(
                "Stream completed",
                extra={"provider": provider, "chunks": chunks_sent,
                       "duration_ms": round((time.time() - start) * 1000)},
            )
            return

        except RateLimitError:
            _log_stat(provider, (time.time() - start) * 1000, success=False)
            if chunks_sent > 0:
                return
            logger.warning("Stream rate-limited", extra={"provider": provider})
            continue

        except Exception as e:
            _log_stat(provider, (time.time() - start) * 1000, success=False)
            if chunks_sent > 0:
                return
            logger.warning("Stream failed", extra={"provider": provider, "error": str(e)})
            continue

    yield (
        "\n\n*No AI provider available. Configure API keys in Settings "
        "(Groq, Gemini, Mistral, or HuggingFace) or start Ollama locally.*"
    )

def reload_keys() -> None:
    _reload_provider_keys()
    _reload_provider_models()
