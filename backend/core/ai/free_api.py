import logging
import time
import httpx
from typing import Optional

from utils.env_writer import read_env

logger = logging.getLogger("codebase-intel.ai")

GROQ_API_KEY: Optional[str] = None
GEMINI_API_KEY: Optional[str] = None
MISTRAL_API_KEY: Optional[str] = None
HUGGINGFACE_API_KEY: Optional[str] = None

_exhausted: dict[str, float] = {}

_RATE_LIMIT_COOLDOWN = 3600.0

_TIMEOUT = 45.0

_http_client: httpx.AsyncClient | None = None

def _get_client(timeout: float = _TIMEOUT) -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client

async def async_cleanup() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None

PROVIDER_MODELS: dict[str, str] = {
    "groq": "llama3-8b-8192",
    "gemini": "gemini-1.5-flash",
    "mistral": "open-mistral-7b",
    "huggingface": "mistralai/Mistral-7B-Instruct-v0.3",
}

class RateLimitError(Exception):
    pass

class ProviderError(Exception):
    pass

def reload_keys() -> None:
    global GROQ_API_KEY, GEMINI_API_KEY, MISTRAL_API_KEY, HUGGINGFACE_API_KEY
    env = read_env()
    GROQ_API_KEY = env.get("GROQ_API_KEY") or None
    GEMINI_API_KEY = env.get("GEMINI_API_KEY") or None
    MISTRAL_API_KEY = env.get("MISTRAL_API_KEY") or None
    HUGGINGFACE_API_KEY = env.get("HUGGINGFACE_API_KEY") or None

def get_key(provider: str) -> Optional[str]:
    key_map = {
        "groq": GROQ_API_KEY,
        "gemini": GEMINI_API_KEY,
        "mistral": MISTRAL_API_KEY,
        "huggingface": HUGGINGFACE_API_KEY,
    }
    return key_map.get(provider)

def has_key(provider: str) -> bool:
    return bool(get_key(provider))

def mark_exhausted(provider: str) -> None:
    _exhausted[provider] = time.time() + _RATE_LIMIT_COOLDOWN

def is_exhausted(provider: str) -> bool:
    expiry = _exhausted.get(provider, 0)
    if time.time() >= expiry:
        _exhausted.pop(provider, None)
        return False
    return True

def clear_exhaustion(provider: str) -> None:
    _exhausted.pop(provider, None)

async def call_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise ProviderError("Groq API key not configured")

    client = _get_client()
    resp = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": PROVIDER_MODELS["groq"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.3,
        },
    )
    if resp.status_code == 429:
        mark_exhausted("groq")
        raise RateLimitError("Groq rate limit exceeded")
    if resp.status_code != 200:
        raise ProviderError(f"Groq API error: {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]

async def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise ProviderError("Gemini API key not configured")

    client = _get_client()
    resp = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{PROVIDER_MODELS['gemini']}:generateContent",
        params={"key": GEMINI_API_KEY},
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            },
        },
    )
    if resp.status_code == 429:
        mark_exhausted("gemini")
        raise RateLimitError("Gemini rate limit exceeded")
    if resp.status_code != 200:
        raise ProviderError(f"Gemini API error: {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise ProviderError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ProviderError("Gemini returned empty content")
    return parts[0].get("text", "")

async def call_mistral(prompt: str) -> str:
    if not MISTRAL_API_KEY:
        raise ProviderError("Mistral API key not configured")

    client = _get_client()
    resp = await client.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": PROVIDER_MODELS["mistral"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.3,
        },
    )
    if resp.status_code == 429:
        mark_exhausted("mistral")
        raise RateLimitError("Mistral rate limit exceeded")
    if resp.status_code != 200:
        raise ProviderError(f"Mistral API error: {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]

async def call_huggingface(prompt: str) -> str:
    if not HUGGINGFACE_API_KEY:
        raise ProviderError("HuggingFace API key not configured")

    client = _get_client(timeout=60.0)
    resp = await client.post(
        f"https://api-inference.huggingface.co/models/{PROVIDER_MODELS['huggingface']}",
        headers={
            "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 2048,
                "temperature": 0.3,
                "return_full_text": False,
            },
        },
    )
    if resp.status_code == 429:
        mark_exhausted("huggingface")
        raise RateLimitError("HuggingFace rate limit exceeded")
    if resp.status_code == 503:
        raise ProviderError("HuggingFace model is loading — try again shortly")
    if resp.status_code != 200:
        raise ProviderError(f"HuggingFace API error: {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    if isinstance(data, list) and len(data) > 0:
        return data[0].get("generated_text", "")
    raise ProviderError("HuggingFace returned unexpected response format")

_PROVIDER_CALLERS = {
    "groq": call_groq,
    "gemini": call_gemini,
    "mistral": call_mistral,
    "huggingface": call_huggingface,
}

_TEST_PROMPT = "Respond with exactly one word: Hello"

async def test_provider(provider: str) -> dict:
    if provider == "ollama":
        return await _test_ollama()

    caller = _PROVIDER_CALLERS.get(provider)
    if not caller:
        return {"available": False, "latency_ms": 0, "error": f"Unknown provider: {provider}"}

    if not has_key(provider):
        return {"available": False, "latency_ms": 0, "error": "API key not set"}

    start = time.time()
    try:
        await caller(_TEST_PROMPT)
        latency = (time.time() - start) * 1000
        clear_exhaustion(provider)
        return {"available": True, "latency_ms": round(latency, 1), "error": None}
    except RateLimitError:
        latency = (time.time() - start) * 1000
        return {"available": False, "latency_ms": round(latency, 1), "error": "Rate limited (429)"}
    except ProviderError as e:
        latency = (time.time() - start) * 1000
        return {"available": False, "latency_ms": round(latency, 1), "error": str(e)}
    except Exception as e:
        latency = (time.time() - start) * 1000
        return {"available": False, "latency_ms": round(latency, 1), "error": f"Connection failed: {str(e)[:100]}"}

async def _test_ollama() -> dict:
    from core.ai.router import get_ollama_model
    model = get_ollama_model()
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": _TEST_PROMPT, "stream": False},
            )
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return {"available": True, "latency_ms": round(latency, 1), "error": None}
            return {"available": False, "latency_ms": round(latency, 1), "error": f"Ollama returned {resp.status_code}"}
    except Exception as e:
        latency = (time.time() - start) * 1000
        return {"available": False, "latency_ms": round(latency, 1), "error": f"Ollama not reachable: {str(e)[:80]}"}

async def get_provider_status() -> dict[str, dict]:
    providers = ["ollama", "groq", "gemini", "mistral", "huggingface"]
    status: dict[str, dict] = {}
    for p in providers:
        if p != "ollama" and not has_key(p):
            status[p] = {"available": False, "latency_ms": 0, "error": "API key not set"}
        elif is_exhausted(p):
            remaining = _exhausted.get(p, 0) - time.time()
            status[p] = {"available": False, "latency_ms": 0, "error": f"Rate limited — {int(remaining / 60)}m remaining"}
        else:
            status[p] = await test_provider(p)
    return status

reload_keys()
