"""Business logic for cached gold and USD prices."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import api.api_price as price_api
import api.api_retrieve_site as scraper
import config.config_api as conf
import database.redis_handler as cache

logger = logging.getLogger(__name__)
_USD_SOURCE_DIFFERENCE_WARNING_PCT = Decimal("20")


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
        last_price = _cached_usd_toman_price(cache.get_last_price_usd(client))
        if last_price is not None:
            return last_price

    with cache.refresh_lock(client, "usd") as lock_acquired:
        if not lock_acquired:
            stale_price = _cached_usd_toman_price(cache.get_last_price_usd(client))
            if stale_price is not None and cache.is_update_valid_usd(client):
                logger.warning("Returning stale USD price while another worker refreshes")
                return stale_price
            raise PriceUnavailableError("USD price refresh is already in progress")

        if not cache.is_update_required_usd(client):
            last_price = _cached_usd_toman_price(cache.get_last_price_usd(client))
            if last_price is not None:
                return last_price

        price = get_usd_price_from_api()
        if price is not None:
            cache.update_last_price_usd(client, price)
            return price

        stale_price = _cached_usd_toman_price(cache.get_last_price_usd(client))
        if stale_price is not None and cache.is_update_valid_usd(client):
            logger.warning("Returning valid stale USD price because all providers failed")
            return stale_price
        raise PriceUnavailableError("USD price is currently unavailable")


def _valid_usd_toman_price(value: str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if (
        not numeric.is_finite()
        or numeric < scraper.USD_TOMAN_MIN
        or numeric > scraper.USD_TOMAN_MAX
    ):
        return None
    return numeric


def _format_usd_toman_price(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _cached_usd_toman_price(value: str | int | float | None) -> str | None:
    """Validate cached values as Toman; never guess-convert a legacy cache value."""
    numeric = _valid_usd_toman_price(value)
    if numeric is None:
        if value is not None:
            logger.warning("Ignoring invalid cached USD price; value=%s", value)
        return None
    return _format_usd_toman_price(numeric)


def get_usd_price_from_api() -> str | None:
    """Fetch both independent USD sources and choose among Toman-normalized values."""
    providers = (
        ("TGJU", scraper.get_usd_from_tgju),
        ("Alanchand", scraper.get_usd_from_alanchand),
    )
    candidates: list[tuple[str, Decimal]] = []
    for name, provider in providers:
        try:
            raw_price = provider()
        except Exception as exc:
            logger.warning(
                "USD provider %s failed unexpectedly; error_type=%s",
                name,
                type(exc).__name__,
            )
            continue
        price = _valid_usd_toman_price(raw_price)
        if price is None:
            if raw_price is not None:
                logger.warning("USD provider %s validation error; value=%s toman", name, raw_price)
            continue
        logger.info("USD provider %s succeeded; normalized_toman=%s", name, price)
        candidates.append((name, price))

    if not candidates:
        logger.warning("USD refresh failed; no valid provider prices")
        return None

    if len(candidates) == 2:
        first, second = candidates[0][1], candidates[1][1]
        difference_pct = abs(first - second) / min(first, second) * Decimal("100")
        if difference_pct > _USD_SOURCE_DIFFERENCE_WARNING_PCT:
            logger.warning(
                "USD provider prices differ by %.2f%%; TGJU=%s Alanchand=%s toman",
                difference_pct,
                first,
                second,
            )

    # Both pages are normalized to Toman first; preserve the gold subsystem's max policy.
    selected_provider, selected_price = max(candidates, key=lambda item: item[1])
    logger.info(
        "USD refresh succeeded; selected=%s normalized_toman=%s providers=%s",
        selected_provider,
        selected_price,
        ",".join(name for name, _ in candidates),
    )
    return _format_usd_toman_price(selected_price)


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
    return conf.get_hokm_string()


def get_xo() -> str:
    client = cache.connect()
    cache.increase_counter(client, "xo")
    return conf.get_xo_string()


def get_counter() -> dict[str, str]:
    return cache.get_counter(cache.connect())
