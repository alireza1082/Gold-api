"""Runtime-configured promotional cards and their local image responses."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import abort, jsonify, request, send_file

from config import config_api

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60
MIN_CACHE_TTL_SECONDS = 60
MAX_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
IMAGE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_CAMPAIGNS = {"hokm": "hokm.json", "xo": "xo.json"}
_IMAGE_MIME_TYPES = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_CAMPAIGN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_IMAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")


class PromoConfigError(ValueError):
    """Raised when a campaign file is not safe to expose."""


@dataclass(frozen=True)
class PromoCampaign:
    enabled: bool = False
    campaign_id: str | None = None
    title: str | None = None
    url: str | None = None
    image_name: str | None = None
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    config_modified: float | None = None


@dataclass(frozen=True)
class PromoImage:
    path: Path
    mime_type: str
    revision: str
    modified: float


class PromoStore:
    """Read two fixed JSON files and serve only image files beneath one directory."""

    _ALLOWED_FIELDS = {"enabled", "id", "title", "url", "image", "cache_ttl_seconds"}

    def __init__(self, directory: Path | str):
        self.directory = Path(directory).resolve()
        self._lock = threading.RLock()
        self._config_cache: dict[
            str, tuple[tuple[int, int, int] | None, PromoCampaign]
        ] = {}
        self._warnings: set[tuple[object, ...]] = set()

    def _warn_once(self, key: tuple[object, ...], message: str, *args: object) -> None:
        with self._lock:
            if key in self._warnings:
                return
            self._warnings.add(key)
        logger.warning(message, *args)

    @staticmethod
    def _stat_signature(path: Path) -> tuple[tuple[int, int, int], float] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size, stat.st_ino), stat.st_mtime

    def get_campaign(self, slug: str) -> PromoCampaign:
        config_name = _CAMPAIGNS.get(slug)
        if config_name is None:
            raise ValueError("unknown promotional campaign")

        path = self.directory / config_name
        file_signature = self._stat_signature(path)
        signature = file_signature[0] if file_signature else None

        with self._lock:
            cached = self._config_cache.get(slug)
            if cached is not None and cached[0] == signature:
                return cached[1]

            if file_signature is None:
                self._warn_once(
                    (slug, "missing-config"),
                    "Promo config %s/%s is missing; campaign disabled",
                    self.directory,
                    config_name,
                )
                campaign = PromoCampaign()
            else:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    campaign = self._parse_campaign(data, file_signature[1])
                except (OSError, UnicodeError, json.JSONDecodeError, PromoConfigError) as exc:
                    self._warn_once(
                        (slug, signature, "invalid-config"),
                        "Invalid promo config %s; campaign disabled: %s",
                        path,
                        exc,
                    )
                    campaign = PromoCampaign(config_modified=file_signature[1])

            self._config_cache[slug] = (signature, campaign)
            return campaign

    @classmethod
    def _parse_campaign(cls, data: object, modified: float) -> PromoCampaign:
        if not isinstance(data, dict):
            raise PromoConfigError("expected a JSON object")
        unknown = set(data) - cls._ALLOWED_FIELDS
        if unknown:
            raise PromoConfigError(f"unknown field(s): {', '.join(sorted(map(str, unknown)))}")

        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            raise PromoConfigError("enabled must be a boolean")

        cache_ttl = data.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)
        if (
            isinstance(cache_ttl, bool)
            or not isinstance(cache_ttl, int)
            or not MIN_CACHE_TTL_SECONDS <= cache_ttl <= MAX_CACHE_TTL_SECONDS
        ):
            raise PromoConfigError(
                f"cache_ttl_seconds must be between {MIN_CACHE_TTL_SECONDS} "
                f"and {MAX_CACHE_TTL_SECONDS}"
            )

        image_name = data.get("image")
        if image_name is not None and not cls._valid_image_name(image_name):
            raise PromoConfigError("image must be a safe local image filename")

        if not enabled:
            return PromoCampaign(
                enabled=False,
                image_name=image_name,
                cache_ttl_seconds=cache_ttl,
                config_modified=modified,
            )

        campaign_id = data.get("id")
        if not isinstance(campaign_id, str) or not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise PromoConfigError("id must be a non-empty stable identifier")

        title = data.get("title")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title.strip()) > 60
            or any(ord(char) < 32 or ord(char) == 127 for char in title)
            or "<" in title
            or ">" in title
        ):
            raise PromoConfigError("title must be plain text between 1 and 60 characters")

        destination = data.get("url")
        if not cls._valid_https_url(destination):
            raise PromoConfigError("url must be a valid HTTPS destination")

        return PromoCampaign(
            enabled=True,
            campaign_id=campaign_id,
            title=title.strip(),
            url=destination,
            image_name=image_name,
            cache_ttl_seconds=cache_ttl,
            config_modified=modified,
        )

    @staticmethod
    def _valid_https_url(value: object) -> bool:
        if not isinstance(value, str) or not value or value != value.strip():
            return False
        if any(
            char.isspace() or char == "\\" or ord(char) < 32 or ord(char) == 127
            for char in value
        ):
            return False
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme.lower() == "https"
            and PromoStore._valid_hostname(parsed.hostname)
            and port != 0
            and not parsed.netloc.endswith(":")
            and parsed.username is None
            and parsed.password is None
        )

    @staticmethod
    def _valid_hostname(hostname: str | None) -> bool:
        if not hostname:
            return False
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            pass

        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        if len(ascii_hostname) > 253:
            return False
        if ascii_hostname.endswith(".."):
            return False
        normalized_hostname = (
            ascii_hostname[:-1] if ascii_hostname.endswith(".") else ascii_hostname
        )
        labels = normalized_hostname.split(".")
        return bool(labels) and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
        )

    @staticmethod
    def _valid_image_name(value: object) -> bool:
        if not isinstance(value, str) or not _IMAGE_NAME.fullmatch(value):
            return False
        if "/" in value or "\\" in value:
            return False
        return Path(value).suffix.lower() in _IMAGE_MIME_TYPES

    def get_image(self, slug: str) -> PromoImage | None:
        campaign = self.get_campaign(slug)
        if campaign.image_name is None:
            return None

        suffix = Path(campaign.image_name).suffix.lower()
        path = self.directory / campaign.image_name
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.directory)
            if not resolved.is_file():
                raise OSError("not a regular file")
            stat = resolved.stat()
            if stat.st_size <= 0 or stat.st_size > MAX_IMAGE_BYTES:
                raise OSError("image size is outside the allowed range")
            if not self._valid_image_bytes(resolved, suffix, stat.st_size):
                raise OSError("image content does not match its file type")
        except (OSError, ValueError) as exc:
            self._warn_once(
                (slug, campaign.config_modified, campaign.image_name, str(exc)),
                "Promo image %s for %s is unavailable: %s",
                campaign.image_name,
                slug,
                exc,
            )
            return None

        revision_source = f"{stat.st_mtime_ns}:{stat.st_size}:{stat.st_ino}".encode()
        revision = hashlib.blake2s(revision_source, digest_size=8).hexdigest()
        return PromoImage(
            path=resolved,
            mime_type=_IMAGE_MIME_TYPES[suffix],
            revision=revision,
            modified=stat.st_mtime,
        )

    @staticmethod
    def _valid_image_bytes(path: Path, suffix: str, size: int) -> bool:
        with path.open("rb") as image:
            header = image.read(12)
            if suffix == ".png":
                image.seek(-12, 2)
                return (
                    size >= 33
                    and header.startswith(b"\x89PNG\r\n\x1a\n")
                    and image.read(12) == b"\x00\x00\x00\x00IEND\xaeB`\x82"
                )
            if suffix in {".jpg", ".jpeg"}:
                image.seek(-2, 2)
                return header.startswith(b"\xff\xd8\xff") and image.read(2) == b"\xff\xd9"
            if suffix == ".webp":
                return (
                    size >= 16
                    and header[:4] == b"RIFF"
                    and header[8:12] == b"WEBP"
                    and int.from_bytes(header[4:8], "little") + 8 == size
                )
        return False

    def get_metadata(self, slug: str) -> tuple[dict[str, object], int, float | None]:
        campaign = self.get_campaign(slug)
        ttl = campaign.cache_ttl_seconds
        modified = campaign.config_modified

        if not campaign.enabled:
            return {"enabled": False, "cache_ttl_seconds": ttl}, ttl, modified

        image = self.get_image(slug)
        image_url = self._public_image_url(slug, image.revision) if image else None
        if image is not None:
            modified = max(modified or image.modified, image.modified)

        payload: dict[str, object] = {
            "enabled": True,
            "id": campaign.campaign_id,
            "title": campaign.title,
            "url": campaign.url,
            "image_url": image_url,
            "cache_ttl_seconds": ttl,
        }
        return payload, ttl, modified

    def _public_image_url(self, slug: str, revision: str) -> str | None:
        base = config_api.public_base_url
        try:
            parsed = urlsplit(base)
            port = parsed.port
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.scheme.lower() != "https"
            or not self._valid_hostname(parsed.hostname)
            or port == 0
            or parsed.netloc.endswith(":")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(
                char.isspace() or char == "\\" or ord(char) < 32 or ord(char) == 127
                for char in base
            )
        ):
            self._warn_once(
                ("public-base-url", base),
                "PUBLIC_BASE_URL must be a valid HTTPS origin; promo image URLs are disabled",
            )
            return None

        route = f"/{slug}-ad/image"
        return f"{base.rstrip('/')}{route}?v={revision}"


def _default_store_directory() -> Path:
    return Path(__file__).resolve().parent.parent / "promo"


promo_store = PromoStore(_default_store_directory())


def metadata_response(slug: str):
    payload, ttl, modified = promo_store.get_metadata(slug)
    response = jsonify(payload)
    etag = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    response.set_etag(etag)
    if modified is not None:
        response.last_modified = datetime.fromtimestamp(modified, timezone.utc)
    response.cache_control.public = True
    response.cache_control.max_age = ttl
    return response.make_conditional(request)


def image_response(slug: str):
    image = promo_store.get_image(slug)
    if image is None:
        abort(404)

    response = send_file(
        image.path,
        mimetype=image.mime_type,
        conditional=True,
        etag=image.revision,
        last_modified=datetime.fromtimestamp(image.modified, timezone.utc),
        max_age=IMAGE_MAX_AGE_SECONDS,
    )
    response.headers["Cache-Control"] = (
        f"public, max-age={IMAGE_MAX_AGE_SECONDS}, immutable"
    )
    return response
