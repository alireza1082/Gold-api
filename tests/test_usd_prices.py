import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from app import app
from api.api_retrieve_site import (
    _parse_usd_number,
    get_usd_from_alanchand,
    get_usd_from_tgju,
    parse_alanchand_usd_toman,
    parse_tgju_usd_toman,
)
import config.config_api as conf
import database.consts as consts
import database.redis_handler as cache
import retriever


class FakeRedisLock:
    def __init__(self, lock):
        self._lock = lock

    def acquire(self, blocking=True):
        return self._lock.acquire(blocking=False)

    def release(self):
        self._lock.release()


class FakeRedis:
    def __init__(self):
        self.values = {}
        self._values_lock = threading.Lock()
        self._refresh_lock = threading.Lock()

    def get(self, key):
        with self._values_lock:
            return self.values.get(key)

    def mset(self, values):
        with self._values_lock:
            self.values.update({key: str(value) for key, value in values.items()})

    def incr(self, key):
        with self._values_lock:
            self.values[key] = str(int(self.values.get(key, "0")) + 1)
            return int(self.values[key])

    def lock(self, *_args, **_kwargs):
        return FakeRedisLock(self._refresh_lock)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class USDParserTests(unittest.TestCase):
    def test_tgju_current_rial_is_converted_to_toman(self):
        html = """
        <span data-col="info.last_trade.PDrCotVal">۲,۶۷۳,۰۰۰</span>
        <table>
          <tr><td>نرخ روز گذشته</td><td>2,584,650</td></tr>
          <tr><td>نرخ بازگشایی بازار</td><td>2,652,750</td></tr>
        </table>
        """
        self.assertEqual(parse_tgju_usd_toman(html), Decimal("267300"))

    def test_tgju_uses_semantic_current_rate_row_as_fallback(self):
        html = """
        <table>
          <tr><td>نرخ روز گذشته</td><td>2,584,650</td></tr>
          <tr><td>نرخ فعلی</td><td>٢,٦٧٣,٠٠٠</td></tr>
          <tr><td>بالاترین قیمت روز</td><td>2,675,200</td></tr>
        </table>
        """
        self.assertEqual(parse_tgju_usd_toman(html), Decimal("267300"))

    def test_alanchand_reads_current_selling_price_in_toman(self):
        html = """
        <h2>قیمت فروش دلار آمریکا</h2>
        <div><span>۲۶۸,۵۰۰</span><span>٪۱.۸۲</span></div>
        <h3>قیمت خرید دلار آمریکا</h3>
        <div>۲۶۶,۰۰۰</div>
        <p>قیمت دیروز ۲۶۳,۹۰۰ تومان بود.</p>
        """
        self.assertEqual(parse_alanchand_usd_toman(html), Decimal("268500"))

    def test_number_normalizer_handles_persian_arabic_and_separators(self):
        self.assertEqual(_parse_usd_number("۲۶۸٬۵۰۰ تومان"), Decimal("268500"))
        self.assertEqual(_parse_usd_number("٢٦٨,٥٠٠ تومان"), Decimal("268500"))

    def test_parsers_reject_time_and_small_or_decimal_values(self):
        self.assertIsNone(_parse_usd_number("14:05"))
        self.assertIsNone(_parse_usd_number("100"))
        self.assertIsNone(_parse_usd_number("1.74"))

    def test_each_provider_makes_one_bounded_page_request(self):
        tgju_html = '<span data-col="info.last_trade.PDrCotVal">2,673,000</span>'
        alanchand_html = (
            "<h2>قیمت فروش دلار آمریکا</h2><p>۲۶۸,۵۰۰ تومان</p>"
            "<h3>قیمت خرید دلار آمریکا</h3>"
        )
        with patch(
            "api.api_retrieve_site.requests.get",
            side_effect=[FakeResponse(tgju_html), FakeResponse(alanchand_html)],
        ) as request:
            self.assertEqual(get_usd_from_tgju(), "267300")
            self.assertEqual(get_usd_from_alanchand(), "268500")

        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertEqual(call.kwargs["timeout"], conf.request_timeout)
            self.assertIn("User-Agent", call.kwargs["headers"])


class USDSelectionTests(unittest.TestCase):
    @patch("retriever.scraper.get_usd_from_alanchand", return_value="268500")
    @patch("retriever.scraper.get_usd_from_tgju", return_value="267300")
    def test_both_normalized_sources_select_max_without_ten_x_error(self, tgju, alanchand):
        # TGJU's 2,673,000 Rial is already converted to 267,300 Toman before comparison.
        self.assertEqual(retriever.get_usd_price_from_api(), "268500")
        tgju.assert_called_once_with()
        alanchand.assert_called_once_with()

    @patch("retriever.scraper.get_usd_from_alanchand", return_value="268500")
    @patch("retriever.scraper.get_usd_from_tgju", return_value="2673000")
    def test_unconverted_tgju_rial_candidate_is_rejected(self, _tgju, _alanchand):
        self.assertEqual(retriever.get_usd_price_from_api(), "268500")

    @patch("retriever.scraper.get_usd_from_alanchand", return_value=None)
    @patch("retriever.scraper.get_usd_from_tgju", return_value="267300")
    def test_alanchand_failure_falls_back_to_tgju(self, tgju, alanchand):
        self.assertEqual(retriever.get_usd_price_from_api(), "267300")
        tgju.assert_called_once_with()
        alanchand.assert_called_once_with()

    @patch("retriever.scraper.get_usd_from_alanchand", return_value="268500")
    @patch("retriever.scraper.get_usd_from_tgju", side_effect=TimeoutError("TGJU timeout"))
    def test_tgju_failure_falls_back_to_alanchand(self, tgju, alanchand):
        self.assertEqual(retriever.get_usd_price_from_api(), "268500")
        tgju.assert_called_once_with()
        alanchand.assert_called_once_with()

    @patch("retriever.scraper.get_usd_from_alanchand", return_value="100")
    @patch("retriever.scraper.get_usd_from_tgju", return_value=None)
    def test_invalid_and_missing_sources_produce_no_price(self, _tgju, _alanchand):
        self.assertIsNone(retriever.get_usd_price_from_api())


class USDCachingTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeRedis()

    def _mark_stale(self, age_seconds):
        self.client.values[consts.USD_TIMESTAMP_KEY] = str(int(time.time()) - age_seconds)

    def test_fresh_cache_skips_both_providers(self):
        cache.update_last_price_usd(self.client, "268500")
        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch("retriever.scraper.get_usd_from_tgju") as tgju, \
             patch("retriever.scraper.get_usd_from_alanchand") as alanchand:
            self.assertEqual(retriever.get_usd_price(), "268500")
        tgju.assert_not_called()
        alanchand.assert_not_called()

    def test_expired_cache_refreshes_both_once_then_reuses_fresh_result(self):
        cache.update_last_price_usd(self.client, "267000")
        self._mark_stale(1801)
        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch("retriever.scraper.get_usd_from_tgju", return_value="267300") as tgju, \
             patch("retriever.scraper.get_usd_from_alanchand", return_value="268500") as alanchand:
            self.assertEqual(retriever.get_usd_price(), "268500")
            self.assertEqual(retriever.get_usd_price(), "268500")
        tgju.assert_called_once_with()
        alanchand.assert_called_once_with()
        self.assertEqual(cache.get_last_price_usd(self.client), "268500")

    def test_both_provider_failures_return_stale_price_without_overwriting_it(self):
        cache.update_last_price_usd(self.client, "267300")
        old_timestamp = int(time.time()) - 1801
        self.client.values[consts.USD_TIMESTAMP_KEY] = str(old_timestamp)
        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch.object(conf, "max_stale_seconds", 10800), \
             patch("retriever.scraper.get_usd_from_tgju", return_value=None), \
             patch("retriever.scraper.get_usd_from_alanchand", return_value=None):
            self.assertEqual(retriever.get_usd_price(), "267300")
        self.assertEqual(cache.get_last_price_usd(self.client), "267300")
        self.assertEqual(self.client.get(consts.USD_TIMESTAMP_KEY), str(old_timestamp))

    def test_both_provider_failures_without_cache_preserve_unavailable_error(self):
        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch("retriever.scraper.get_usd_from_tgju", return_value=None), \
             patch("retriever.scraper.get_usd_from_alanchand", return_value=None):
            with self.assertRaises(retriever.PriceUnavailableError):
                retriever.get_usd_price()

    def test_unconverted_rial_in_stale_cache_is_never_returned(self):
        cache.update_last_price_usd(self.client, "2673000")
        self._mark_stale(1801)
        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch.object(conf, "max_stale_seconds", 10800), \
             patch("retriever.scraper.get_usd_from_tgju", return_value=None), \
             patch("retriever.scraper.get_usd_from_alanchand", return_value=None):
            with self.assertRaises(retriever.PriceUnavailableError):
                retriever.get_usd_price()

    def test_unconverted_rial_in_fresh_cache_is_refreshed_before_return(self):
        cache.update_last_price_usd(self.client, "2673000")
        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch("retriever.scraper.get_usd_from_tgju", return_value="267300"), \
             patch("retriever.scraper.get_usd_from_alanchand", return_value=None):
            self.assertEqual(retriever.get_usd_price(), "267300")
        self.assertEqual(cache.get_last_price_usd(self.client), "267300")

    def test_refresh_lock_prevents_parallel_provider_stampede(self):
        cache.update_last_price_usd(self.client, "267000")
        self._mark_stale(1801)
        barrier = threading.Barrier(8)
        request_counts = {"tgju": 0, "alanchand": 0}
        count_lock = threading.Lock()

        def refresh_tgju():
            with count_lock:
                request_counts["tgju"] += 1
            time.sleep(0.05)
            return "267300"

        def refresh_alanchand():
            with count_lock:
                request_counts["alanchand"] += 1
            time.sleep(0.05)
            return "268500"

        def request_price():
            barrier.wait()
            return retriever.get_usd_price()

        with patch.object(cache, "connect", return_value=self.client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch.object(conf, "max_stale_seconds", 10800), \
             patch("retriever.scraper.get_usd_from_tgju", side_effect=refresh_tgju), \
             patch("retriever.scraper.get_usd_from_alanchand", side_effect=refresh_alanchand):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda _index: request_price(), range(8)))

        self.assertEqual(request_counts, {"tgju": 1, "alanchand": 1})
        self.assertTrue(all(value in {"267000", "268500"} for value in results))


class USDEndpointTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("app.retriever.get_usd_price", return_value="268500")
    def test_usd_endpoint_still_returns_plain_text_price(self, _get_price):
        response = self.client.get("/usd")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "268500")

    def test_full_usd_route_returns_and_caches_normalized_toman(self):
        redis_client = FakeRedis()
        with patch.object(cache, "connect", return_value=redis_client), \
             patch.object(conf, "usd_cache_ttl", 1800), \
             patch("retriever.scraper.get_usd_from_tgju", return_value="267300"), \
             patch("retriever.scraper.get_usd_from_alanchand", return_value="268500"):
            response = self.client.get("/usd")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "268500")
        self.assertEqual(cache.get_last_price_usd(redis_client), "268500")


if __name__ == "__main__":
    unittest.main()
