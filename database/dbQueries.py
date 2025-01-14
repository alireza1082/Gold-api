from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

import database.consts as consts


def connect():
    try:
        time = datetime.now().timestamp()
        # Connect with the port number and host
        command_client = MongoClient("mongodb://localhost:27017/")
        client = MongoClient("localhost", 27017)
        print("Connected to DB successfully")
        print(time - datetime.now().timestamp())
        return client
    except PyMongoError as error:
        print("Could not connect to MongoDB with error: ", error)
        return None


def get_last_price(client):
    # Access database
    database = client.gold_db

    # Access collection of the database
    collection = database["gold_price"]

    return collection.find_one().get("price")


def is_update_required(client):
    collection = client.gold_db["gold_price"]

    last_update_time = collection.find_one().get("time")

    if last_update_time is None:
        return True
    elif datetime.now().timestamp() - consts.BASE_TIME > last_update_time:
        return True
    else:
        return False

def is_update_valid(client):
    collection = client.gold_db["gold_price"]

    last_update_time = collection.find_one().get("time")

    if last_update_time is None:
        return False
    elif datetime.now().timestamp() - consts.MAX_VALID_TIME < last_update_time:
        return True
    else:
        return False

def get_dict(price):
    mydict = {"name": "LastGoldPrice", "price": price, "time": datetime.now().timestamp()}
    return mydict


def update_last_price(client, price):
    collection = client.gold_db["gold_price"]
    collection.update_one(
        consts.BASE_DIC,
        {"$set": {"price": price, "time": datetime.now().timestamp()}},
    )
