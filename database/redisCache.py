"""Small Redis repository used by the request handlers.

Redis clients are safe to share between threads when using the standard redis-py
connection pool, so a single client is reused instead of being created per request.
Cache failures are deliberately non-fatal: callers can fetch a fresh external value.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

import redis
from redis import RedisError

import config.config_api as conf
import database.consts as consts

logger = logging.getLogger(__name__)
_client: redis.Redis | None = None


def connect() -> redis.Redis:
    """Return the process-wide Redis client.

    Redis-py opens connections lazily, which keeps application startup independent
    from Redis availability. Individual operations handle RedisError below.
    """
    global _client
    if _client is None:
        _client = redis.Redis(
            host=conf.redis_host,
            port=conf.redis_port,
            db=conf.redis_db,
            password=conf.redis_password,
            decode_responses=True,
            socket_connect_timeout=conf.request_timeout,
            socket_timeout=conf.request_timeout,
            health_check_interval=30,
        )
    return _client


@contextmanager
def refresh_lock(
    client: redis.Redis | None,
    name: str,
    timeout: int | None = None,
) -> Iterator[bool]:
    """Acquire a short Redis lock, yielding whether this caller owns it.

    A Redis outage must not prevent an external refresh, so lock failures yield
    ``True`` and let the caller proceed without coordination.
    """
    if client is None:
        yield True
        return

    lock = client.lock(
        f"lock:refresh:{name}",
        timeout=timeout or conf.refresh_lock_seconds,
        blocking_timeout=0,
    )
    acquired = False
    try:
        try:
            acquired = bool(lock.acquire(blocking=True))
        except RedisError:
            logger.warning("Redis refresh lock failed for %s", name, exc_info=True)
            acquired = True
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except RedisError:
                logger.warning("Redis refresh lock release failed for %s", name, exc_info=True)


def check_connection(client: redis.Redis | None) -> bool:
    """Check Redis readiness without leaking connection exceptions to Flask."""
    if client is None:
        return False
    try:
        return bool(client.ping())
    except RedisError as exc:
        logger.warning("Redis health check failed; error_type=%s", type(exc).__name__)
        return False


def _get(client: redis.Redis | None, key: str) -> str | None:
    if client is None:
        return None
    try:
        value = client.get(key)
        return str(value) if value is not None else None
    except (RedisError, ValueError) as exc:
        logger.warning(
            "Redis read failed for key %s; error_type=%s",
            key,
            type(exc).__name__,
        )
        return None


def get_last_price(client: redis.Redis | None) -> str | None:
    return _get(client, consts.PRICE_KEY)


def _timestamp(client: redis.Redis | None, key: str) -> int | None:
    value = _get(client, key)
    try:
        return int(value) if value is not None else None
    except ValueError:
        logger.warning("Invalid timestamp in Redis key %s", key)
        return None


def is_update_required(client: redis.Redis | None) -> bool:
    last_update = _timestamp(client, consts.PRICE_TIMESTAMP_KEY)
    return last_update is None or time.time() - conf.gold_cache_ttl > last_update


def is_update_valid(client: redis.Redis | None) -> bool:
    last_update = _timestamp(client, consts.PRICE_TIMESTAMP_KEY)
    return last_update is not None and time.time() - conf.max_stale_seconds < last_update


def update_last_price(client: redis.Redis | None, price: str | int | float) -> bool:
    if client is None:
        return False
    try:
        client.mset(
            {
                consts.PRICE_TIMESTAMP_KEY: int(time.time()),
                consts.PRICE_KEY: str(price),
            }
        )
        return True
    except RedisError as exc:
        logger.warning("Redis update failed for gold price; error_type=%s", type(exc).__name__)
        return False


def increase_counter(client: redis.Redis | None, req_type: str) -> bool:
    """Atomically increment a request counter, avoiding GET/SET lost updates."""
    if client is None or req_type not in {"gold", "usd", "hokm"}:
        return False
    try:
        client.incr(f"counter_{req_type}")
        return True
    except RedisError as exc:
        logger.warning(
            "Redis counter increment failed for %s; error_type=%s",
            req_type,
            type(exc).__name__,
        )
        return False


def get_counter(client: redis.Redis | None) -> dict[str, str]:
    keys = ("counter_usd", "counter_gold", "counter_hokm")
    values = [_get(client, key) or "0" for key in keys]
    return dict(zip(keys, values))


def get_last_price_usd(client: redis.Redis | None) -> str | None:
    return _get(client, consts.USD_PRICE_KEY)


def update_last_price_usd(client: redis.Redis | None, price: str | int | float) -> bool:
    if client is None:
        return False
    try:
        client.mset(
            {
                consts.USD_TIMESTAMP_KEY: int(time.time()),
                consts.USD_PRICE_KEY: str(price),
            }
        )
        return True
    except RedisError as exc:
        logger.warning("Redis update failed for USD price; error_type=%s", type(exc).__name__)
        return False


def is_update_required_usd(client: redis.Redis | None) -> bool:
    last_update = _timestamp(client, consts.USD_TIMESTAMP_KEY)
    return last_update is None or time.time() - conf.usd_cache_ttl > last_update


def is_update_valid_usd(client: redis.Redis | None) -> bool:
    last_update = _timestamp(client, consts.USD_TIMESTAMP_KEY)
    return last_update is not None and time.time() - conf.max_stale_seconds < last_update
