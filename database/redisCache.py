from datetime import datetime

import redis
from redis import RedisError

import database.consts as consts


def connect():
    try:
        # Connect with the port number and host
        client = redis.Redis(host='localhost', port=6379, db=0)
        print("Connected to DB successfully")
        return client
    except RedisError as error:
        print("Could not connect to MongoDB with error: ", error)
        return None


def get_last_price(client):
    return client.get("price")


def is_update_required(client):
    last_update_time = client.get("timestamp")

    if last_update_time is None:
        return True
    elif datetime.now().timestamp() - consts.BASE_TIME > last_update_time:
        return True
    else:
        return False


def is_update_valid(client):
    last_update_time = client.get("timestamp")

    if last_update_time is None:
        return False
    elif datetime.now().timestamp() - consts.MAX_VALID_TIME < last_update_time:
        return True
    else:
        return False

def update_last_price(client, price):
    pip = client.pipeline()
    pip.set("timestamp", datetime.now().timestamp())
    pip.set("price", price)
    return pip.execute()