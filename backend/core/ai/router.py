"""
AI Router — orchestrates prompt routing across providers with fallback chain.

Priority chain: Cache → Ollama (local) → Groq → Gemini → Mistral → HuggingFace
Tracks per-provider stats (request count, latency) in a SQLite stats table.
Automatically skips exhausted (rate-limited) providers.
"""

import time
import logging
import sqlite3
import threading

logger = logging.getLogger("codebase-intel.router")
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from core.ai.free_api import (
    call_groq,
    call_gemini,
    call_mistral,
    call_huggingface,
    is_exhausted,
    has_key,
    RateLimitError,
    ProviderError,
    reload_keys as _reload_provider_keys,
)



OLLAMA_URL = "http://localhost:11434/api/generate"
_ollama_model = "phi3:mini"
OLLAMA_MODEL = _ollama_model
OLLAMA_TIMEOUT = 60.0


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
    """Get or create the global stats database."""
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
    """Log a provider call result to the stats database."""
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
        logger.debug(f"Stats logging failed for {provider}: {e}")


def get_provider_stats() -> dict[str, dict]:
    """
    Get aggregated stats per provider.
    Returns: { provider: { requests: int, successes: int, avg_latency_ms: float } }
    """
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
        logger.warning(f"Failed to read provider stats: {e}")

    
    for p in PROVIDER_CHAIN:
        if p not in result:
            result[p] = {"requests_today": 0, "successes": 0, "avg_latency_ms": 0}

    return result


def clear_stats() -> None:
    """Clear all provider stats."""
    try:
        conn = _get_stats_db()
        conn.execute("DELETE FROM provider_stats")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to clear stats: {e}")




def set_prefer_local(prefer: bool) -> None:
    """Set whether to prefer local Ollama over API providers."""
    global _prefer_local
    _prefer_local = prefer


def get_prefer_local() -> bool:
    """Get current local preference setting."""
    return _prefer_local


def get_ordered_providers() -> list[str]:
    """Get the provider chain in current priority order."""
    if _prefer_local:
        return list(PROVIDER_CHAIN)
    else:
        
        chain = [p for p in PROVIDER_CHAIN if p != "ollama"]
        chain.append("ollama")
        return chain


def _is_provider_available(provider: str) -> bool:
    """Check if a provider is currently usable."""
    if provider == "ollama":
        return True  
    if is_exhausted(provider):
        return False
    if not has_key(provider):
        return False
    return True




async def _call_ollama(prompt: str) -> str:
    """Call Ollama local inference."""
    model = get_ollama_model()
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
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


async def route_prompt(prompt: str) -> tuple[Optional[str], str]:
    """
    Route a prompt through the provider chain with automatic fallback.

    Returns: (response_text, provider_name) on success.
             (None, "none") if all providers failed.

    The caller should fall back to template-based responses when (None, "none")
    is returned.
    """
    chain = get_ordered_providers()
    last_error = ""

    for provider in chain:
        if not _is_provider_available(provider):
            continue

        caller = _CALLERS.get(provider)
        if not caller:
            continue

        start = time.time()
        try:
            result = await caller(prompt)
            latency = (time.time() - start) * 1000
            _log_stat(provider, latency, success=True)
            return result, provider

        except RateLimitError:
            latency = (time.time() - start) * 1000
            _log_stat(provider, latency, success=False)
            last_error = f"{provider} rate limited"
            continue  

        except ProviderError as e:
            latency = (time.time() - start) * 1000
            _log_stat(provider, latency, success=False)
            last_error = f"{provider}: {str(e)[:80]}"
            continue

        except Exception as e:
            latency = (time.time() - start) * 1000
            _log_stat(provider, latency, success=False)
            last_error = f"{provider}: {str(e)[:80]}"
            continue

    return None, "none"


def reload_keys() -> None:
    """Hot-reload API keys from .env (delegates to free_api module)."""
    _reload_provider_keys()
