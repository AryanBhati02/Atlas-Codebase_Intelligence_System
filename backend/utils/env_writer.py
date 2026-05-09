
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

def _ensure_env_exists() -> None:
    if not _ENV_PATH.exists():
        _ENV_PATH.write_text("# Codebase Intelligence Tool — Environment Variables\n", encoding="utf-8")

def read_env() -> dict[str, str]:
    _ensure_env_exists()
    result: dict[str, str] = {}
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            result[key] = value
    return result

def get_key(key: str) -> Optional[str]:
    return read_env().get(key)

def backup_env() -> Optional[Path]:
    _ensure_env_exists()
    if not _ENV_PATH.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = _ENV_PATH.parent / f".env.backup_{timestamp}"
    shutil.copy2(str(_ENV_PATH), str(backup_path))
    return backup_path

def write_key(key: str, value: str) -> None:
    _ensure_env_exists()
    backup_env()

    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    key_found = False
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.partition("=")[0].strip()
            if existing_key == key:
                new_lines.append(f"{key}={value}")
                key_found = True
                continue
        new_lines.append(line)

    if not key_found:
        new_lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def remove_key(key: str) -> None:
    _ensure_env_exists()
    backup_env()

    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.partition("=")[0].strip()
            if existing_key == key:
                continue
        new_lines.append(line)

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def mask_key(value: str) -> str:
    if not value or len(value) <= 6:
        return "****"
    return "****" + value[-6:]

def get_env_path() -> Path:
    return _ENV_PATH
