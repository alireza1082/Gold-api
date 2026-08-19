"""Application constants for cache and price refresh behavior."""

BASE_DIC = {"name": "LastGoldPrice"}
BASE_TIME = 15 * 60
BASE_TIME_USD = 10 * 60
MAX_VALID_TIME = 3 * 60 * 60

PRICE_KEY = "price"
PRICE_TIMESTAMP_KEY = "timestamp"
USD_PRICE_KEY = "price_usd"
USD_TIMESTAMP_KEY = "time_usd"