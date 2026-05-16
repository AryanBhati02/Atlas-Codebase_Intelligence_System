import logging
import time
import httpx
from typing import Optional

from utils.env_writer import read_env, write_key

logger = logging.getLogger("codebase-intel.ai")

GROQ_API_KEY: Optional[str] = None
GEMINI_API_KEY: Optional[str] = None
MISTRAL_API_KEY: Optional[str] = None
HUGGINGFACE_API_KEY: Optional[str] = None

_exhausted: dict[str, float] = {}

_RATE_LIMIT_COOLDOWN = 3600.0

_TIMEOUT = 45.0

_http_client: httpx.AsyncClient | None = None

_provider_models: dict[str, str] = {}

_MODEL_ENV_KEYS: dict[str, str] = {
    "groq": "GROQ_MODEL",
    "gemini": "GEMINI_MODEL",
    "mistral": "MISTRAL_MODEL",
    "huggingface": "HUGGINGFACE_MODEL",
}


def get_model(provider: str) -> str:
    """Return the currently selected model for *provider* (may be empty)."""
    return _provider_models.get(provider, "")


def set_model(provider: str, model: str) -> None:
    """Set the active model for *provider* in memory and persist to .env."""
    _provider_models[provider] = model
    env_key = _MODEL_ENV_KEYS.get(provider)
    if env_key:
        write_key(env_key, model)


def reload_models() -> None:
    """Load persisted model selections from .env."""
    env = read_env()
    for provider, env_key in _MODEL_ENV_KEYS.items():
        val = env.get(env_key, "").strip()
        if val:
            _provider_models[provider] = val

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

async def list_models_groq() -> list[dict]:
    """Fetch available models from Groq's OpenAI-compatible endpoint."""
    if not GROQ_API_KEY:
        return []
    try:
        client = _get_client()
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            return [
                {"id": m["id"], "owned_by": m.get("owned_by", "")}
                for m in models
                if m.get("id")
            ]
    except Exception as exc:
        logger.debug("Failed to list Groq models: %s", exc)
    return []


async def list_models_gemini() -> list[dict]:
    """Fetch available models from Google Generative Language API."""
    if not GEMINI_API_KEY:
        return []
    try:
        client = _get_client()
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": GEMINI_API_KEY},
        )
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            return [
                {
                    "id": m.get("name", "").replace("models/", ""),
                    "name": m.get("displayName", ""),
                    "owned_by": "google",
                }
                for m in models
                if "generateContent" in str(m.get("supportedGenerationMethods", []))
            ]
    except Exception as exc:
        logger.debug("Failed to list Gemini models: %s", exc)
    return []


async def list_models_mistral() -> list[dict]:
    """Fetch available models from Mistral API."""
    if not MISTRAL_API_KEY:
        return []
    try:
        client = _get_client()
        resp = await client.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            return [
                {"id": m["id"], "owned_by": m.get("owned_by", "")}
                for m in models
                if m.get("id")
            ]
    except Exception as exc:
        logger.debug("Failed to list Mistral models: %s", exc)
    return []


async def list_models_huggingface() -> list[dict]:
    """HuggingFace does not have a clean model-list API for inference.
    Return empty — the UI will allow freeform input."""
    return []


_MODEL_LISTERS = {
    "groq": list_models_groq,
    "gemini": list_models_gemini,
    "mistral": list_models_mistral,
    "huggingface": list_models_huggingface,
}


async def list_provider_models(provider: str) -> list[dict]:
    """Return available models for *provider* via dynamic API discovery."""
    lister = _MODEL_LISTERS.get(provider)
    if not lister:
        return []
    try:
        return await lister()
    except Exception as exc:
        logger.warning("Model listing failed for %s: %s", provider, exc)
        return []

async def call_groq(prompt: str, model: str | None = None) -> str:
    if not GROQ_API_KEY:
        raise ProviderError("Groq API key not configured")

    resolved_model = model or get_model("groq")
    if not resolved_model:
        raise ProviderError("No model selected for Groq — select one in Settings")

    client = _get_client()
    resp = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
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


async def call_gemini(prompt: str, model: str | None = None) -> str:
    if not GEMINI_API_KEY:
        raise ProviderError("Gemini API key not configured")

    resolved_model = model or get_model("gemini")
    if not resolved_model:
        raise ProviderError("No model selected for Gemini — select one in Settings")

    client = _get_client()
    resp = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent",
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


async def call_mistral(prompt: str, model: str | None = None) -> str:
    if not MISTRAL_API_KEY:
        raise ProviderError("Mistral API key not configured")

    resolved_model = model or get_model("mistral")
    if not resolved_model:
        raise ProviderError("No model selected for Mistral — select one in Settings")

    client = _get_client()
    resp = await client.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
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


async def call_huggingface(prompt: str, model: str | None = None) -> str:
    if not HUGGINGFACE_API_KEY:
        raise ProviderError("HuggingFace API key not configured")

    resolved_model = model or get_model("huggingface")
    if not resolved_model:
        raise ProviderError("No model selected for HuggingFace — select one in Settings")

    client = _get_client(timeout=60.0)
    resp = await client.post(
        f"https://api-inference.huggingface.co/models/{resolved_model}",
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

    model = get_model(provider)
    if not model:
        return {"available": False, "latency_ms": 0, "error": "No model selected — choose one in Settings"}

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
reload_models()
