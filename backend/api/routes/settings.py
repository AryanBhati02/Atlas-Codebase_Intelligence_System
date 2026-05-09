
import os
import sqlite3
import subprocess
import httpx
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from utils.env_writer import write_key, read_env, mask_key
from core.ai.free_api import (
    reload_keys,
    has_key,
    get_key,
    is_exhausted,
    clear_exhaustion,
    test_provider,
    PROVIDER_MODELS,
)
from core.ai.router import (
    get_provider_stats,
    get_prefer_local,
    set_prefer_local,

    clear_stats,
    get_ollama_model,
    set_ollama_model,
)
from config import SESSIONS_DIR

router = APIRouter(prefix="/settings", tags=["Settings"])

class KeyUpdateRequest(BaseModel):
    provider: str
    key: str

class KeyUpdateResponse(BaseModel):
    valid: bool
    latency_ms: float
    error: Optional[str] = None

class TestProviderRequest(BaseModel):
    provider: str

class TestProviderResponse(BaseModel):
    available: bool
    latency_ms: float
    model: Optional[str] = None
    error: Optional[str] = None

class PreferenceRequest(BaseModel):
    prefer_local: bool

class ProviderInfo(BaseModel):
    name: str
    enabled: bool
    key_required: bool
    key_set: bool
    key_masked: str
    status: str  
    model: str
    requests_today: int
    avg_latency_ms: float

class SettingsResponse(BaseModel):
    providers: list[ProviderInfo]
    active_model: str
    prefer_local: bool
    cache_entries: int
    cache_size_mb: float

class StatusResponse(BaseModel):
    ollama: bool
    groq: bool
    gemini: bool
    mistral: bool
    huggingface: bool
    active_provider: str
    cache_size: int

class ClearCacheRequest(BaseModel):
    session_id: Optional[str] = None

class ClearCacheResponse(BaseModel):
    cleared_entries: int
    message: str

_PROVIDER_KEY_MAP: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "huggingface": "HUGGINGFACE_API_KEY",
}

def _get_provider_status_label(provider: str) -> str:
    if provider == "ollama":
        try:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
            if resp.status_code == 200:
                return "online"
            return "offline"
        except Exception:
            return "offline"
    if not has_key(provider):
        return "no_key"
    if is_exhausted(provider):
        return "rate_limited"
    return "unknown"

def _count_cache_entries() -> tuple[int, float]:
    total_entries = 0
    total_bytes = 0

    if not SESSIONS_DIR.exists():
        return 0, 0.0

    for session_dir in SESSIONS_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        cache_db = session_dir / "ai_cache.db"
        if cache_db.exists():
            try:
                total_bytes += cache_db.stat().st_size
                conn = sqlite3.connect(str(cache_db))
                row = conn.execute("SELECT COUNT(*) FROM ai_cache").fetchone()
                if row:
                    total_entries += row[0]
                conn.close()
            except Exception:
                pass

    return total_entries, round(total_bytes / (1024 * 1024), 2)

def _clear_session_cache(session_dir: Path) -> int:
    cache_db = session_dir / "ai_cache.db"
    if not cache_db.exists():
        return 0
    try:
        conn = sqlite3.connect(str(cache_db))
        row = conn.execute("SELECT COUNT(*) FROM ai_cache").fetchone()
        count = row[0] if row else 0
        conn.execute("DELETE FROM ai_cache")
        conn.commit()
        conn.close()
        return count
    except Exception:
        return 0

def _determine_active_provider() -> str:
    if get_prefer_local():
        return "ollama"
    for provider in ["groq", "gemini", "mistral", "huggingface"]:
        if has_key(provider) and not is_exhausted(provider):
            return provider
    return "ollama"

@router.get("", response_model=SettingsResponse)
async def get_settings():
    stats = get_provider_stats()
    cache_entries, cache_size_mb = _count_cache_entries()

    providers_info: list[ProviderInfo] = []

    ollama_stats = stats.get("ollama", {})
    providers_info.append(ProviderInfo(
        name="ollama",
        enabled=True,
        key_required=False,
        key_set=False,
        key_masked="",
        status=_get_provider_status_label("ollama"),
        model=get_ollama_model(),
        requests_today=ollama_stats.get("requests_today", 0),
        avg_latency_ms=ollama_stats.get("avg_latency_ms", 0),
    ))

    for provider_name in ["groq", "gemini", "mistral", "huggingface"]:
        env_key = _PROVIDER_KEY_MAP[provider_name]
        raw_key = get_key(provider_name) or ""
        p_stats = stats.get(provider_name, {})

        providers_info.append(ProviderInfo(
            name=provider_name,
            enabled=has_key(provider_name),
            key_required=True,
            key_set=bool(raw_key),
            key_masked=mask_key(raw_key) if raw_key else "",
            status=_get_provider_status_label(provider_name),
            model=PROVIDER_MODELS.get(provider_name, ""),
            requests_today=p_stats.get("requests_today", 0),
            avg_latency_ms=p_stats.get("avg_latency_ms", 0),
        ))

    active_model = get_ollama_model() if get_prefer_local() else PROVIDER_MODELS.get(
        _determine_active_provider(), get_ollama_model()
    )

    return SettingsResponse(
        providers=providers_info,
        active_model=active_model,
        prefer_local=get_prefer_local(),
        cache_entries=cache_entries,
        cache_size_mb=cache_size_mb,
    )

@router.post("/keys", response_model=KeyUpdateResponse)
async def update_key(request: KeyUpdateRequest):
    provider = request.provider.lower()

    if provider not in _PROVIDER_KEY_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider}. Valid: {', '.join(_PROVIDER_KEY_MAP.keys())}",
        )

    key = request.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    env_var = _PROVIDER_KEY_MAP[provider]
    write_key(env_var, key)

    reload_keys()

    clear_exhaustion(provider)

    result = await test_provider(provider)

    return KeyUpdateResponse(
        valid=result["available"],
        latency_ms=result["latency_ms"],
        error=result.get("error"),
    )

@router.post("/test", response_model=TestProviderResponse)
async def test_provider_endpoint(request: TestProviderRequest):
    provider = request.provider.lower()

    valid_providers = {"ollama", "groq", "gemini", "mistral", "huggingface"}
    if provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider}. Valid: {', '.join(valid_providers)}",
        )

    result = await test_provider(provider)

    model = get_ollama_model() if provider == "ollama" else PROVIDER_MODELS.get(provider, "")

    return TestProviderResponse(
        available=result["available"],
        latency_ms=result["latency_ms"],
        model=model if result["available"] else None,
        error=result.get("error"),
    )

@router.get("/status", response_model=StatusResponse)
async def get_status():
    cache_entries, _ = _count_cache_entries()

    ollama_status = True  
    groq_status = has_key("groq") and not is_exhausted("groq")
    gemini_status = has_key("gemini") and not is_exhausted("gemini")
    mistral_status = has_key("mistral") and not is_exhausted("mistral")
    huggingface_status = has_key("huggingface") and not is_exhausted("huggingface")

    return StatusResponse(
        ollama=ollama_status,
        groq=groq_status,
        gemini=gemini_status,
        mistral=mistral_status,
        huggingface=huggingface_status,
        active_provider=_determine_active_provider(),
        cache_size=cache_entries,
    )

@router.post("/prefer", response_model=dict)
async def set_preference(request: PreferenceRequest):
    set_prefer_local(request.prefer_local)
    return {
        "prefer_local": request.prefer_local,
        "active_provider": _determine_active_provider(),
    }

@router.post("/clear-cache", response_model=ClearCacheResponse)
async def clear_cache(request: ClearCacheRequest):
    total_cleared = 0

    if request.session_id:
        session_dir = SESSIONS_DIR / request.session_id
        if session_dir.exists():
            total_cleared = _clear_session_cache(session_dir)
        else:
            raise HTTPException(status_code=404, detail="Session not found.")
    else:
        
        if SESSIONS_DIR.exists():
            for session_dir in SESSIONS_DIR.iterdir():
                if session_dir.is_dir():
                    total_cleared += _clear_session_cache(session_dir)

    return ClearCacheResponse(
        cleared_entries=total_cleared,
        message=f"Cleared {total_cleared} cached AI responses.",
    )

class SelectModelRequest(BaseModel):
    model: str

@router.get("/ollama-models")
async def list_ollama_models():
    models = []
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                reachable = True
                data = resp.json()
                for m in data.get("models", []):
                    name = m.get("name", "")
                    size_bytes = m.get("size", 0)
                    if size_bytes > 0:
                        size_gb = size_bytes / (1024 ** 3)
                        size_str = f"{size_gb:.1f} GB"
                    else:
                        size_str = "unknown"
                    models.append({
                        "name": name,
                        "size": size_str,
                        "modified_at": m.get("modified_at", ""),
                    })
    except Exception:
        pass

    return {"models": models, "reachable": reachable}

@router.post("/select-model")
async def select_model(request: SelectModelRequest):
    model = request.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name cannot be empty.")
    set_ollama_model(model)
    return {"model": model, "status": "ok"}
