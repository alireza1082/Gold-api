"""Legacy MongoDB helpers.

The current API uses Redis only. These helpers remain for compatibility with any
external callers, but use one client per explicit call and fail safely on empty data.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError

import database.consts as consts

logger = logging.getLogger(__name__)


def connect() -> MongoClient | None:
    """Create a MongoDB client using MONGO_URI, without attempting an unbounded call."""
    try:
        client = MongoClient(
            os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
        )
        client.admin.command("ping")
        return client
    except PyMongoError:
        logger.warning("Could not connect to MongoDB", exc_info=True)
        return None


def get_last_price(client: MongoClient | None) -> Any:
    if client is None:
        return None
    document = client.gold_db["gold_price"].find_one(consts.BASE_DIC)
    return document.get("price") if document else None


def is_update_required(client: MongoClient | None) -> bool:
    if client is None:
        return True
    document = client.gold_db["gold_price"].find_one(consts.BASE_DIC)
    last_update = document.get("time") if document else None
    return last_update is None or time.time() - consts.BASE_TIME > last_update


def is_update_valid(client: MongoClient | None) -> bool:
    if client is None:
        return False
    document = client.gold_db["gold_price"].find_one(consts.BASE_DIC)
    last_update = document.get("time") if document else None
    return last_update is not None and time.time() - consts.MAX_VALID_TIME < last_update


def get_dict(price: Any) -> dict[str, Any]:
    return {"name": "LastGoldPrice", "price": price, "time": time.time()}


def update_last_price(client: MongoClient | None, price: Any) -> bool:
    if client is None:
        return False
    try:
        result = client.gold_db["gold_price"].update_one(
            consts.BASE_DIC,
            {"$set": {"price": price, "time": time.time()}},
            upsert=True,
        )
        return result.acknowledged
    except PyMongoError:
        logger.warning("Could not update MongoDB gold price", exc_info=True)
        return False
