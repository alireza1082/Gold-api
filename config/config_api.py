"""Runtime configuration loaded from environment variables."""

import os


def _get_int(name: str, default: int, minimum: int = 0) -> int:
    value = os.getenv(name)
    try:
        parsed = int(value) if value is not None else default
        return parsed if parsed >= minimum else default
    except ValueError:
        return default


def _get_float(name: str, default: float, minimum: float = 0.1) -> float:
    value = os.getenv(name)
    try:
        parsed = float(value) if value is not None else default
        return parsed if parsed >= minimum else default
    except ValueError:
        return default


api_token = os.getenv("ONE_API_TOKEN", "").strip()
brs_api_token = os.getenv("BRS_API_TOKEN", "").strip()

# localhost keeps local development convenient; Compose overrides this with "redis".
redis_host = os.getenv("REDIS_HOST", "localhost").strip() or "localhost"
redis_port = _get_int("REDIS_PORT", 6379, minimum=1)
redis_db = _get_int("REDIS_DB", 0)
redis_password = os.getenv("REDIS_PASSWORD") or None
request_timeout = _get_float("REQUEST_TIMEOUT_SECONDS", 10.0)

# Defaults preserve the original refresh behavior while allowing production tuning.
gold_cache_ttl = _get_int("GOLD_CACHE_TTL_SECONDS", 15 * 60, minimum=1)
usd_cache_ttl = _get_int("USD_CACHE_TTL_SECONDS", 10 * 60, minimum=1)
max_stale_seconds = _get_int("MAX_STALE_SECONDS", 3 * 60 * 60, minimum=1)
refresh_lock_seconds = _get_int("REFRESH_LOCK_SECONDS", 30, minimum=1)

import logging
from pathlib import Path
import threading

logger = logging.getLogger(__name__)

_env_cache_lock = threading.Lock()
_cached_env_vars: dict[str, str] = {}
_cached_stat: tuple[int, int] | None = None


def _parse_env_file(filepath: Path | str) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if not key:
                    continue
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                else:
                    if " #" in val:
                        val = val.split(" #", 1)[0].strip()
                    elif "\t#" in val:
                        val = val.split("\t#", 1)[0].strip()
                env_vars[key] = val
    except Exception as exc:
        logger.warning("Could not read env file %s: %s", filepath, exc)
    return env_vars


def _resolve_env_path() -> Path | None:
    override = os.getenv("ENV_FILE_PATH")
    if override:
        p = Path(override)
        return p if p.is_file() else None

    # Primary path: root of repo relative to config/
    base_env = Path(__file__).resolve().parent.parent / ".env"
    if base_env.is_file():
        return base_env

    app_env = Path("/app/.env")
    if app_env.is_file():
        return app_env

    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env

    return None


def _reload_env_if_needed() -> None:
    global _cached_stat, _cached_env_vars
    env_path = _resolve_env_path()
    if env_path is None:
        if _cached_stat is not None:
            with _env_cache_lock:
                _cached_stat = None
                _cached_env_vars = {}
        return

    try:
        st = env_path.stat()
        current_stat = (st.st_mtime_ns, st.st_size)
    except OSError:
        current_stat = None

    if current_stat != _cached_stat:
        with _env_cache_lock:
            if current_stat != _cached_stat:
                if current_stat is None:
                    _cached_stat = None
                    _cached_env_vars = {}
                else:
                    _cached_env_vars = _parse_env_file(env_path)
                    _cached_stat = current_stat


def get_dynamic_env(key: str, default: str = "") -> str:
    """Retrieve an environment variable, dynamically reloading from .env when modified."""
    _reload_env_if_needed()
    with _env_cache_lock:
        if key in _cached_env_vars:
            return _cached_env_vars[key]
    return os.getenv(key, default)


def get_hokm_string() -> str:
    return get_dynamic_env("HOKM_STRING", "Tapsell")


def get_xo_string() -> str:
    return get_dynamic_env("XO_STRING", "XO")


def __getattr__(name: str) -> str:
    if name in {"HOKM_STRING", "hokm_string"}:
        return get_hokm_string()
    if name in {"XO_STRING", "xo_string"}:
        return get_xo_string()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

