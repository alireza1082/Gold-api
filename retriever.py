"""Business logic for cached gold and USD prices."""

from __future__ import annotations

import logging

import api.api_price as price_api
import api.api_retrieve_site as scraper
import database.redisCache as cache

logger = logging.getLogger(__name__)


class PriceUnavailableError(RuntimeError):
    """Raised when neither a fresh external price nor a usable cached price exists."""


def _valid_price(value: str | int | float | None) -> str | None:
    if value is None:
        return None
    try:
        numeric = float(value)
        return str(value) if numeric > 0 else None
    except (TypeError, ValueError):
        return None


def get_gold_price() -> str:
    client = cache.connect()
    cache.increase_counter(client, "gold")

    if not cache.is_update_required(client):
        last_price = _valid_price(cache.get_last_price(client))
        if last_price is not None:
            return last_price

    with cache.refresh_lock(client, "gold") as lock_acquired:
        if not lock_acquired:
            stale_price = _valid_price(cache.get_last_price(client))
            if stale_price is not None and cache.is_update_valid(client):
                return stale_price
            raise PriceUnavailableError("Gold price refresh is already in progress")

        # Another worker may have refreshed the value while this request waited.
        if not cache.is_update_required(client):
            last_price = _valid_price(cache.get_last_price(client))
            if last_price is not None:
                return last_price

        price = get_gold_price_from_api()
        if price is not None:
            cache.update_last_price(client, price)
            return price

        stale_price = _valid_price(cache.get_last_price(client))
        if stale_price is not None and cache.is_update_valid(client):
            logger.warning("Returning valid stale gold price because providers failed")
            return stale_price
        raise PriceUnavailableError("Gold price is currently unavailable")


def get_usd_price() -> str:
    client = cache.connect()
    cache.increase_counter(client, "usd")

    if not cache.is_update_required_usd(client):
        last_price = _valid_price(cache.get_last_price_usd(client))
        if last_price is not None:
            return last_price

    with cache.refresh_lock(client, "usd") as lock_acquired:
        if not lock_acquired:
            stale_price = _valid_price(cache.get_last_price_usd(client))
            if stale_price is not None and cache.is_update_valid_usd(client):
                return stale_price
            raise PriceUnavailableError("USD price refresh is already in progress")

        if not cache.is_update_required_usd(client):
            last_price = _valid_price(cache.get_last_price_usd(client))
            if last_price is not None:
                return last_price

        price = price_api.get_usd_brs()
        if price is not None:
            cache.update_last_price_usd(client, price)
            return price

        stale_price = _valid_price(cache.get_last_price_usd(client))
        if stale_price is not None and cache.is_update_valid_usd(client):
            logger.warning("Returning valid stale USD price because provider failed")
            return stale_price
        raise PriceUnavailableError("USD price is currently unavailable")


def get_gold_price_from_api() -> str | None:
    tgju = scraper.get_tgju_price()
    if tgju is None:
        tgju = price_api.get_price_from_tgju()
    tala = scraper.get_tala_price()

    candidates = [_valid_price(tgju), _valid_price(tala)]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        return None
    return max(candidates, key=float)


def get_hokm() -> str:
    client = cache.connect()
    cache.increase_counter(client, "hokm")
    return "Tapsell"


def get_counter() -> dict[str, str]:
    return cache.get_counter(cache.connect())
