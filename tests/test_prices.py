import unittest
from contextlib import nullcontext
from unittest.mock import patch

from app import app
from api.api_price import _parse_api_price
from api.api_retrieve_site import _parse_site_price
import database.redis_handler as cache
import retriever


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.incr_calls = []

    def incr(self, key):
        self.incr_calls.append(key)
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def get(self, key):
        return self.values.get(key)


class PriceParsingTests(unittest.TestCase):
    def test_provider_price_parsers_reject_empty_values(self):
        self.assertIsNone(_parse_api_price("abc", 4))
        self.assertIsNone(_parse_site_price("", 3))

    def test_provider_price_parsers_normalize_formatted_values(self):
        self.assertEqual(_parse_api_price("1,234,5678", 4), "1235")
        self.assertEqual(_parse_site_price("۱۲۳۴۵۶۷", 3), "1235")

    @patch("retriever.scraper.get_tala_price", return_value="200")
    @patch("retriever.scraper.get_tgju_price", return_value="100")
    def test_gold_price_uses_numeric_comparison(self, _tgju, _tala):
        self.assertEqual(retriever.get_gold_price_from_api(), "200")

    def test_gold_price_returns_valid_stale_cache_when_refresh_fails(self):
        with patch.object(retriever.cache, "connect", return_value=object()), \
             patch.object(retriever.cache, "increase_counter"), \
             patch.object(retriever.cache, "is_update_required", return_value=True), \
             patch.object(retriever.cache, "refresh_lock", return_value=nullcontext(True)), \
             patch.object(retriever.cache, "get_last_price", return_value="123"), \
             patch.object(retriever.cache, "is_update_valid", return_value=True), \
             patch.object(retriever, "get_gold_price_from_api", return_value=None):
            self.assertEqual(retriever.get_gold_price(), "123")


class CacheTests(unittest.TestCase):
    def test_counter_increment_is_atomic_operation(self):
        client = FakeRedis()
        self.assertTrue(cache.increase_counter(client, "gold"))
        self.assertTrue(cache.increase_counter(client, "gold"))
        self.assertTrue(cache.increase_counter(client, "xo"))
        self.assertEqual(client.incr_calls, ["counter_gold", "counter_gold", "counter_xo"])
        counters = cache.get_counter(client)
        self.assertEqual(counters["counter_gold"], "2")
        self.assertEqual(counters["counter_xo"], "1")
        self.assertEqual(counters["counter_hokm"], "0")

    def test_hokm_and_xo_counters_are_independent(self):
        client = FakeRedis()
        self.assertTrue(cache.increase_counter(client, "hokm"))
        self.assertTrue(cache.increase_counter(client, "xo"))
        self.assertTrue(cache.increase_counter(client, "xo"))
        counters = cache.get_counter(client)
        self.assertEqual(counters["counter_hokm"], "1")
        self.assertEqual(counters["counter_xo"], "2")

    def test_refresh_lock_does_not_release_after_acquire_error(self):
        class FailedRedis:
            def lock(self, *_args, **_kwargs):
                class FailedLock:
                    released = False

                    def acquire(self, **_kwargs):
                        raise cache.RedisError("Redis unavailable")

                    def release(self):
                        self.released = True

                self.failed_lock = FailedLock()
                return self.failed_lock

        client = FailedRedis()
        with cache.refresh_lock(client, "gold") as acquired:
            self.assertTrue(acquired)
        self.assertFalse(client.failed_lock.released)

    def test_refresh_lock_reports_when_another_worker_owns_lock(self):
        class LockedRedis:
            def lock(self, *_args, **_kwargs):
                class BusyLock:
                    def acquire(self, **_kwargs):
                        return False

                    def release(self):
                        raise AssertionError("busy lock must not be released")

                return BusyLock()

        with cache.refresh_lock(LockedRedis(), "gold") as acquired:
            self.assertFalse(acquired)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("app.cache.check_connection", return_value=True)
    def test_health_endpoint(self, _check):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    @patch("app.retriever.get_gold_price", side_effect=retriever.PriceUnavailableError())
    def test_unavailable_price_is_not_exposed_as_html_or_500(self, _get_price):
        response = self.client.get("/gold")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "price_unavailable")

    @patch("app.retriever.get_counter", return_value={"counter_gold": "0", "counter_xo": "1"})
    def test_counter_is_json(self, _get_counter):
        response = self.client.get("/counter")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["counter_gold"], "0")
        self.assertEqual(response.json["counter_xo"], "1")

    @patch("retriever.cache.increase_counter")
    @patch("retriever.cache.connect")
    def test_hokm_endpoint(self, _connect, _incr):
        response = self.client.get("/hokm")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.text, str)
        _incr.assert_called_with(_connect(), "hokm")

    @patch("retriever.cache.increase_counter")
    @patch("retriever.cache.connect")
    def test_xo_endpoint(self, _connect, _incr):
        response = self.client.get("/xo")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.text, str)
        _incr.assert_called_with(_connect(), "xo")


class ConfigReloadTests(unittest.TestCase):
    def test_dynamic_env_reload_without_restart(self):
        import os
        import tempfile
        import time
        from config import config_api

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
            f.write("HOKM_STRING=TEST_HOKM_1\nXO_STRING=TEST_XO_1\n")
            temp_path = f.name

        try:
            with patch.dict(os.environ, {"ENV_FILE_PATH": temp_path}):
                self.assertEqual(config_api.get_hokm_string(), "TEST_HOKM_1")
                self.assertEqual(config_api.get_xo_string(), "TEST_XO_1")

                # Update the file content without restarting
                time.sleep(0.01)
                with open(temp_path, "w") as f:
                    f.write("HOKM_STRING=TEST_HOKM_2\nXO_STRING=TEST_XO_2\n")

                # Next call should dynamically reload the new values
                self.assertEqual(config_api.get_hokm_string(), "TEST_HOKM_2")
                self.assertEqual(config_api.get_xo_string(), "TEST_XO_2")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
