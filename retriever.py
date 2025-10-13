from werkzeug.exceptions import abort

import api.api_price as api
import api.api_retrieve_site as api_scraper
import database.redisCache as dB


def get_gold_price():
    redis = dB.connect()
    dB.increase_counter(redis, "gold")

    if dB.is_update_required(redis):
        print("DB update required!")
        price = get_gold_price_from_api()
        if price is not None:
            print("returned price: " + str(price))
            dB.update_last_price(redis, price)
            return price
        if (price is None) and dB.is_update_valid(redis):
            print("Api not responding and price is valid!!")
            return dB.get_last_price(redis)
        else:
            abort(404, description="Resource not found")
    else:
        print("update not required")
        return dB.get_last_price(redis)


def get_usd_price():
    redis = dB.connect()
    dB.increase_counter(redis, "usd")

    if dB.is_update_required_usd(redis):
        print("DB update required for usd!")
        price = api.get_usd_brs()
        if price is not None:
            print("returned price: " + str(price))
            dB.update_last_price_usd(redis, str(price))
            return price
        if price is None:
            print("Api brs not responding!!")
            return dB.get_last_price_usd(redis)
        else:
            abort(404, description="Resource not found")
    else:
        print("update not required")
        return dB.get_last_price_usd(redis)


def get_gold_price_from_api():
    tgju_site_price = api_scraper.get_tgju_price()
    if tgju_site_price is not None:
        tgju = tgju_site_price
    else:
        tgju = api.get_price_from_tgju()
    tala_site_price = api_scraper.get_tala_price()
    # bon_api_price = api.get_price_from_bonbast()
    if tgju > tala_site_price:
        return tgju
    if tala_site_price == "0":
        return None
    return tala_site_price


def get_counter():
    redis = dB.connect()
    return dB.get_counter(redis)
