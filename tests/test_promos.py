import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
import api.api_promo as promo_api
from api.api_promo import DEFAULT_CACHE_TTL_SECONDS, PromoStore
import config.config_api as conf


PROJECT_PROMO_DIR = Path(__file__).resolve().parent.parent / "promo"


class PromoApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        for image_name in ("hokm.webp", "xo.webp"):
            shutil.copyfile(PROJECT_PROMO_DIR / image_name, self.root / image_name)

        self.store_patch = patch.object(promo_api, "promo_store", PromoStore(self.root))
        self.store_patch.start()
        self.base_url_patch = patch.object(
            conf, "public_base_url", "https://gold.example:8443"
        )
        self.base_url_patch.start()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self):
        self.base_url_patch.stop()
        self.store_patch.stop()
        self.temp_dir.cleanup()

    def write_campaign(self, slug, **values):
        path = self.root / f"{slug}.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return path

    def enabled_campaign(self, slug, **overrides):
        values = {
            "enabled": True,
            "id": f"{slug}-campaign",
            "title": f"{slug.title()} Offer",
            "url": "https://example.com/offer",
            "image": f"{slug}.webp",
            "cache_ttl_seconds": 21600,
        }
        values.update(overrides)
        return self.write_campaign(slug, **values)

    def test_hokm_and_xo_metadata_are_independent_and_point_to_this_api(self):
        self.enabled_campaign("hokm", id="phoenix-coin", title="Phoenix Coin")
        self.enabled_campaign("xo", id="xo-prize", title="XO Prize", url="https://prize.example")

        hokm = self.client.get("/hokm-ad")
        xo = self.client.get("/xo-ad")
        self.assertEqual(hokm.status_code, 200)
        self.assertEqual(xo.status_code, 200)
        self.assertEqual(hokm.json["id"], "phoenix-coin")
        self.assertEqual(hokm.json["title"], "Phoenix Coin")
        self.assertEqual(hokm.json["url"], "https://example.com/offer")
        self.assertTrue(
            hokm.json["image_url"].startswith("https://gold.example:8443/hokm-ad/image?v=")
        )
        self.assertEqual(hokm.json["cache_ttl_seconds"], 21600)
        self.assertEqual(xo.json["id"], "xo-prize")
        self.assertEqual(xo.json["url"], "https://prize.example")
        self.assertTrue(
            xo.json["image_url"].startswith("https://gold.example:8443/xo-ad/image?v=")
        )

        # Changing Hokm's file must not affect XO's independent config.
        self.enabled_campaign("hokm", title="Updated Phoenix Offer")
        self.assertEqual(self.client.get("/hokm-ad").json["title"], "Updated Phoenix Offer")
        self.assertEqual(self.client.get("/xo-ad").json["title"], "XO Prize")

    def test_missing_and_disabled_campaigns_return_http_200(self):
        response = self.client.get("/hokm-ad")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {"enabled": False, "cache_ttl_seconds": DEFAULT_CACHE_TTL_SECONDS},
        )

        self.write_campaign(
            "xo", enabled=False, image="xo.webp", cache_ttl_seconds=7200
        )
        response = self.client.get("/xo-ad")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"enabled": False, "cache_ttl_seconds": 7200})

    def test_default_production_assets_are_served_by_the_api(self):
        with patch.object(promo_api, "promo_store", PromoStore(PROJECT_PROMO_DIR)):
            for slug in ("hokm", "xo"):
                metadata = self.client.get(f"/{slug}-ad")
                image = self.client.get(f"/{slug}-ad/image")
                self.assertEqual(metadata.status_code, 200)
                self.assertFalse(metadata.json["enabled"])
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.mimetype, "image/webp")
                self.assertTrue(image.data.startswith(b"RIFF"))
                self.assertEqual(image.data[8:12], b"WEBP")

    def test_image_response_has_binary_mime_etag_last_modified_and_long_cache(self):
        self.write_campaign("hokm", enabled=False, image="hokm.webp")
        response = self.client.get("/hokm-ad/image?v=ignored-by-route")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/webp")
        self.assertTrue(response.data.startswith(b"RIFF"))
        self.assertIn("immutable", response.headers["Cache-Control"])
        self.assertIn("max-age=31536000", response.headers["Cache-Control"])
        self.assertIn("ETag", response.headers)
        self.assertIn("Last-Modified", response.headers)

        unchanged = self.client.get(
            "/hokm-ad/image", headers={"If-None-Match": response.headers["ETag"]}
        )
        self.assertEqual(unchanged.status_code, 304)

    def test_metadata_cache_headers_and_etag(self):
        self.enabled_campaign("hokm", cache_ttl_seconds=3600)
        response = self.client.get("/hokm-ad")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cache_control.max_age, 3600)
        self.assertTrue(response.cache_control.public)
        self.assertIn("ETag", response.headers)
        self.assertIn("Last-Modified", response.headers)

        unchanged = self.client.get(
            "/hokm-ad", headers={"If-None-Match": response.headers["ETag"]}
        )
        self.assertEqual(unchanged.status_code, 304)

    def test_config_reload_updates_title_and_image_revision(self):
        config_path = self.enabled_campaign("hokm", title="First Offer")
        first = self.client.get("/hokm-ad").json

        config_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "id": "hokm-campaign",
                    "title": "A Different Offer After Reload",
                    "url": "https://example.com/offer",
                    "image": "hokm.webp",
                }
            ),
            encoding="utf-8",
        )
        second = self.client.get("/hokm-ad").json
        self.assertEqual(second["title"], "A Different Offer After Reload")
        self.assertEqual(first["image_url"], second["image_url"])

        image_path = self.root / "hokm.webp"
        image_path.write_bytes((PROJECT_PROMO_DIR / "xo.webp").read_bytes())
        third = self.client.get("/hokm-ad").json
        self.assertNotEqual(second["image_url"], third["image_url"])

    def test_enabled_campaign_without_image_is_text_only(self):
        self.enabled_campaign("hokm", image=None)
        metadata = self.client.get("/hokm-ad")
        self.assertEqual(metadata.status_code, 200)
        self.assertTrue(metadata.json["enabled"])
        self.assertIsNone(metadata.json["image_url"])
        self.assertEqual(self.client.get("/hokm-ad/image").status_code, 404)

    def test_missing_configured_image_does_not_return_broken_url(self):
        self.enabled_campaign("hokm", image="missing.webp")
        metadata = self.client.get("/hokm-ad")
        self.assertTrue(metadata.json["enabled"])
        self.assertIsNone(metadata.json["image_url"])
        self.assertEqual(self.client.get("/hokm-ad/image").status_code, 404)

        (self.root / "bad.webp").write_bytes(b"not a WebP image")
        self.enabled_campaign("hokm", image="bad.webp")
        metadata = self.client.get("/hokm-ad")
        self.assertIsNone(metadata.json["image_url"])
        self.assertEqual(self.client.get("/hokm-ad/image").status_code, 404)

    def test_invalid_public_base_url_does_not_emit_external_or_internal_image_url(self):
        self.enabled_campaign("hokm")
        with patch.object(conf, "public_base_url", "http://gold:8000"):
            metadata = self.client.get("/hokm-ad")
        self.assertTrue(metadata.json["enabled"])
        self.assertIsNone(metadata.json["image_url"])

    def test_invalid_destination_urls_fail_closed(self):
        invalid_urls = (
            "http://example.com",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "data:text/plain,bad",
            "https://",
            "https://bad host/path",
            "https://bad_host.example",
            "https://example..com",
            "https://example.com..",
            "https://example.com:0",
            "https://example.com:",
            r"https://example.com\@evil.example",
            "https://%",
            "https://user:pass@example.com",
        )
        for index, destination in enumerate(invalid_urls):
            with self.subTest(destination=destination):
                root = self.root / f"url-{index}"
                root.mkdir()
                (root / "hokm.json").write_text(
                    json.dumps(
                        {
                            "enabled": True,
                            "id": "safe-id",
                            "title": "Safe title",
                            "url": destination,
                        }
                    ),
                    encoding="utf-8",
                )
                with patch.object(promo_api, "promo_store", PromoStore(root)):
                    response = self.client.get("/hokm-ad")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json["enabled"])

    def test_path_traversal_and_bad_titles_are_rejected(self):
        self.enabled_campaign("hokm", image="../../etc/passwd")
        metadata = self.client.get("/hokm-ad")
        self.assertEqual(metadata.status_code, 200)
        self.assertFalse(metadata.json["enabled"])
        self.assertEqual(self.client.get("/hokm-ad/image").status_code, 404)

        root = self.root / "html-title"
        root.mkdir()
        (root / "hokm.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "id": "safe-id",
                    "title": "<script>alert(1)</script>",
                    "url": "https://example.com",
                }
            ),
            encoding="utf-8",
        )
        with patch.object(promo_api, "promo_store", PromoStore(root)):
            response = self.client.get("/hokm-ad")
        self.assertFalse(response.json["enabled"])

    def test_invalid_cache_ttl_fails_closed(self):
        self.enabled_campaign("hokm", cache_ttl_seconds=0)
        response = self.client.get("/hokm-ad")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["enabled"])
        self.assertEqual(response.json["cache_ttl_seconds"], DEFAULT_CACHE_TTL_SECONDS)

    def test_routes_do_not_access_redis(self):
        self.write_campaign("xo", enabled=False, image="xo.webp")
        with patch("app.cache.connect", side_effect=AssertionError("promo must not use Redis")):
            self.assertEqual(self.client.get("/hokm-ad").status_code, 200)
            self.assertEqual(self.client.get("/xo-ad/image").status_code, 200)


if __name__ == "__main__":
    unittest.main()
