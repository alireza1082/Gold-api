"""Clients for the external price APIs."""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import config_api

logger = logging.getLogger(__name__)
ONE_API_URL = "https://one-api.ir/price/"


def _parse_api_price(raw_value: Any, trailing_digits: int) -> str | None:
    """Convert the providers' formatted rial strings into the existing price format."""
    if raw_value is None:
        return None
    digits = "".join(ch for ch in str(raw_value) if ch in "0123456789")
    if len(digits) <= trailing_digits:
        return None
    try:
        return str(int(digits[:-trailing_digits]) + 1)
    except ValueError:
        return None


def _one_api_request(action: str) -> dict[str, Any] | None:
    if not config_api.api_token:
        logger.error("ONE_API_TOKEN is not configured")
        return None
    try:
        response = requests.post(
            ONE_API_URL,
            params={"token": config_api.api_token, "action": action},
            timeout=config_api.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "One API %s request failed; error_type=%s",
            action,
            type(exc).__name__,
        )
        return None


def get_price_from_tgju() -> str | None:
    payload = _one_api_request("tgju")
    if not payload or str(payload.get("status")) != "200":
        logger.warning("One API returned an unsuccessful TGJU response")
        return None
    try:
        return _parse_api_price(payload["result"]["gold"]["geram18"]["p"], 4)
    except (KeyError, TypeError):
        logger.warning("Malformed TGJU response from One API")
        return None


def get_price_from_bonbast() -> str | None:
    payload = _one_api_request("bonbast")
    if not payload or str(payload.get("status")) != "200":
        logger.warning("One API returned an unsuccessful Bonbast response")
        return None
    try:
        return _parse_api_price(payload["result"]["gol18"], 3)
    except (KeyError, TypeError):
        logger.warning("Malformed Bonbast response from One API")
        return None
