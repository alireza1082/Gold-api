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
