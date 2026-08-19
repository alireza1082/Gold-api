"""Fallback scrapers for public price pages."""

from __future__ import annotations

import logging
from typing import Any

import requests
from bs4 import BeautifulSoup
from persiantools import digits

from config import config_api

logger = logging.getLogger(__name__)


def _parse_site_price(raw_value: Any, trailing_digits: int) -> str | None:
    if raw_value is None:
        return None
    normalized = digits.fa_to_en(str(raw_value))
    numeric = "".join(ch for ch in normalized if ch in "0123456789")
    if len(numeric) <= trailing_digits:
        return None
    try:
        return str(int(numeric[:-trailing_digits]) + 1)
    except ValueError:
        return None


def get_tgju_price() -> str | None:
    try:
        response = requests.get(
            "https://www.tgju.org/profile/geram18",
            timeout=config_api.request_timeout,
        )
        response.raise_for_status()
        element = BeautifulSoup(response.text, "html.parser").find(
            "span", {"data-col": "info.last_trade.PDrCotVal"}
        )
        price = _parse_site_price(element.get_text() if element else None, 4)
        if price is None:
            logger.warning("TGJU page did not contain a valid price")
        return price
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("TGJU scrape failed; error_type=%s", type(exc).__name__)
        return None


def get_tala_price() -> str | None:
    try:
        response = requests.get(
            "https://www.tala.ir/price/18k",
            timeout=config_api.request_timeout,
        )
        response.raise_for_status()
        element = BeautifulSoup(response.text, "html.parser").find(
            "h3", {"class": "bg-green-light"}
        )
        price = _parse_site_price(element.get_text() if element else None, 3)
        if price is None:
            logger.warning("Tala page did not contain a valid price")
        return price
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("Tala scrape failed; error_type=%s", type(exc).__name__)
        return None
