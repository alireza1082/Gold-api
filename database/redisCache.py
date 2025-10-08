from datetime import datetime

import redis
from redis import RedisError

import config.config_api as conf
import database.consts as consts


def connect():
    try:
        # Connect with the port number and host
        client = redis.Redis(
            host=conf.redis_host,
            port=conf.redis_port,
            db=conf.redis_db,
            password=conf.redis_password)

        print("Connected to DB successfully")
        return client
    except RedisError as error:
        print("Could not connect to Redis with error: ", error)
        return None


def get_last_price(client):
    return client.get("price")


def is_update_required(client):
    last_update_time = client.get("timestamp")
    timestamp = int(round(datetime.now().timestamp()))

    if last_update_time is None:
        return True
    elif timestamp - consts.BASE_TIME > int(last_update_time):
        return True
    else:
        return False


def is_update_valid(client):
    last_update_time = client.get("timestamp")
    timestamp = int(round(datetime.now().timestamp()))

    if last_update_time is None:
        return False
    elif timestamp - consts.MAX_VALID_TIME < int(last_update_time):
        return True
    else:
        return False


def update_last_price(client, price):
    timestamp = int(round(datetime.now().timestamp()))
    print("Updating last price", price, timestamp)

    pip = client.pipeline()
    pip.set("timestamp", timestamp)
    pip.set("price", price)

    return pip.execute()


def increase_counter(client, req_type):
    counter = client.get(f"counter_{req_type}")

    pip = client.pipeline()

    if counter is None:
        pip.set(f"counter_{req_type}", "1")
    else:
        temp = int(counter) + 1
        pip.set(f"counter_{req_type}", temp)

    return pip.execute()


def get_counter(client):
    counter_gold = client.get("counter_gold")
    counter_usd = client.get("counter_usd")
    return {
        "counter_usd": str(counter_usd),
        "counter_gold": str(counter_gold),
    }


def get_last_price_usd(client):
    return client.get("price_usd")


def update_last_price_usd(client, price):
    timestamp = int(round(datetime.now().timestamp()))
    print("Updating last price", price, timestamp)

    pip = client.pipeline()
    pip.set("time_usd", timestamp)
    pip.set("price_usd", price)

    return pip.execute()


def is_update_required_usd(client):
    last_update_time = client.get("time_usd")
    timestamp = int(round(datetime.now().timestamp()))

    if last_update_time is None:
        return True
    elif timestamp - consts.BASE_TIME_USD > int(last_update_time):
        return True
    else:
        return False
