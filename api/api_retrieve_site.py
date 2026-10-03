"""Fallback scrapers for public price pages."""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from persiantools import digits

from config import config_api

logger = logging.getLogger(__name__)

TGJU_USD_URL = "https://www.tgju.org/profile/price_dollar_rl"
ALANCHAND_USD_URL = "https://alanchand.com/currencies-price/usd"
USD_TOMAN_MIN = Decimal("10000")
# This broad upper bound also rejects the sample TGJU Rial value if accidentally
# passed through as though it were Toman; increase it if the market outgrows it.
USD_TOMAN_MAX = Decimal("2500000")
_USD_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}
_USD_PRICE_TOKEN = re.compile(
    r"(?<![0-9:])(?:[0-9]{1,3}(?:[,٬، ][0-9]{3})+|[0-9]{4,})(?![0-9:])"
)
_USD_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


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


def _parse_usd_number(raw_value: Any) -> Decimal | None:
    """Read a grouped integer price from a provider-specific DOM value."""
    if raw_value is None:
        return None
    normalized = str(raw_value).translate(_USD_TRANSLATION)
    normalized = normalized.replace("\u00a0", " ").replace("\u202f", " ")
    match = _USD_PRICE_TOKEN.search(normalized)
    if match is None:
        return None
    digits_only = re.sub(r"[,٬، ]", "", match.group(0))
    try:
        return Decimal(digits_only)
    except InvalidOperation:
        return None


def _valid_usd_toman(value: Decimal | None, provider: str) -> str | None:
    if (
        value is None
        or not value.is_finite()
        or not USD_TOMAN_MIN <= value <= USD_TOMAN_MAX
    ):
        logger.warning("USD provider %s validation error; value=%s toman", provider, value)
        return None
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def parse_tgju_usd_toman(html: str) -> Decimal | None:
    """Parse TGJU's current USD rate and convert its displayed Rial to Toman."""
    soup = BeautifulSoup(html, "html.parser")

    # TGJU's profile page marks the latest traded/current rate with this data column.
    current_rate = soup.select_one('span[data-col="info.last_trade.PDrCotVal"]')
    rial_price = _parse_usd_number(current_rate.get_text(" ", strip=True)) if current_rate else None

    # Keep a semantic fallback for table markup where the current-rate row is present.
    if rial_price is None:
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True).strip(" :：")
            if label == "نرخ فعلی":
                rial_price = _parse_usd_number(cells[1].get_text(" ", strip=True))
                if rial_price is not None:
                    break

    if rial_price is None:
        return None

    # The TGJU price_dollar_rl page reports Rial; the existing /usd contract is Toman.
    return rial_price / Decimal("10")


def parse_alanchand_usd_toman(html: str) -> Decimal | None:
    """Parse the current USD selling price; Alanchand already reports Toman."""
    soup = BeautifulSoup(html, "html.parser")
    heading_tags = {"h1", "h2", "h3", "h4", "h5"}
    heading = next(
        (
            tag
            for tag in soup.find_all(sorted(heading_tags))
            if tag.get_text(" ", strip=True).strip(" :：") == "قیمت فروش دلار آمریکا"
        ),
        None,
    )
    if heading is None:
        return None

    # Read the first price immediately following this heading, stopping at the next
    # heading so buy prices and historical sections cannot be mistaken for today's sell.
    for node in heading.next_elements:
        if isinstance(node, Tag) and node.name in heading_tags:
            break
        if isinstance(node, NavigableString):
            price = _parse_usd_number(node)
            if price is not None:
                return price
    return None


def _request_usd_page(url: str, provider: str) -> str | None:
    try:
        response = requests.get(
            url,
            headers=_USD_REQUEST_HEADERS,
            timeout=config_api.request_timeout,
        )
        response.raise_for_status()
        return response.text
    except requests.Timeout as exc:
        logger.warning("USD provider %s timeout; error_type=%s", provider, type(exc).__name__)
    except requests.HTTPError as exc:
        logger.warning("USD provider %s HTTP error; error_type=%s", provider, type(exc).__name__)
    except requests.RequestException as exc:
        logger.warning("USD provider %s request error; error_type=%s", provider, type(exc).__name__)
    return None


def get_usd_from_tgju() -> str | None:
    html = _request_usd_page(TGJU_USD_URL, "TGJU")
    if html is None:
        return None
    price = parse_tgju_usd_toman(html)
    if price is None:
        logger.warning("USD provider TGJU parse error; current rate was not found")
        return None
    return _valid_usd_toman(price, "TGJU")


def get_usd_from_alanchand() -> str | None:
    html = _request_usd_page(ALANCHAND_USD_URL, "Alanchand")
    if html is None:
        return None
    price = parse_alanchand_usd_toman(html)
    if price is None:
        logger.warning("USD provider Alanchand parse error; current selling price was not found")
        return None
    return _valid_usd_toman(price, "Alanchand")
