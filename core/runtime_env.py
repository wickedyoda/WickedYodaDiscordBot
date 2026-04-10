import os
from pathlib import Path

PROTECTED_CONTAINER_ENV_KEYS = {
    "DATA_DIR",
    "LOG_DIR",
    "WEB_BIND_HOST",
    "WEB_PORT",
    "WEB_TLS_ENABLED",
    "WEB_TLS_PORT",
    "WEB_ENV_FILE",
}


def load_env_file(path: Path, *, override: bool, protected_keys: set[str] | None = None) -> None:
    if not path.exists() or not path.is_file():
        return
    protected = {str(key).strip() for key in (protected_keys or set()) if str(key).strip()}
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for raw_line in content:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key in protected and key in os.environ:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
