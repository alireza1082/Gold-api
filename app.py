"""Flask application entrypoint."""

from __future__ import annotations

import logging

from flask import Flask, jsonify

import database.redisCache as cache
import retriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = Flask(__name__)
app.config.from_mapping(JSON_SORT_KEYS=False)


@app.errorhandler(retriever.PriceUnavailableError)
def handle_price_unavailable(error: retriever.PriceUnavailableError):
    app.logger.error("Price request failed: %s", error)
    return jsonify(error="price_unavailable", message="Price is temporarily unavailable"), 503


@app.errorhandler(404)
def handle_not_found(error):
    return jsonify(error="not_found", message="Resource not found"), 404


@app.errorhandler(405)
def handle_method_not_allowed(error):
    return jsonify(error="method_not_allowed", message="Method not allowed"), 405


@app.errorhandler(500)
def handle_internal_error(error):
    app.logger.exception("Unhandled application error")
    return jsonify(error="internal_error", message="Internal server error"), 500


@app.route("/", methods=["GET"])
def hello_world():
    return "<p>An api returns Gold price.</p>"


@app.route("/health", methods=["GET"])
def health():
    """Readiness endpoint: the process is healthy only when Redis is reachable."""
    if cache.check_connection(cache.connect()):
        return jsonify(status="ok", redis="ok")
    return jsonify(status="degraded", redis="unavailable"), 503


@app.route("/gold", methods=["GET"])
def gold_price():
    return retriever.get_gold_price()


@app.route("/usd", methods=["GET"])
def usd_price():
    return retriever.get_usd_price()


@app.route("/hokm", methods=["GET"])
def hokm_state():
    return retriever.get_hokm()


@app.route("/counter", methods=["GET"])
def get_counter():
    return jsonify(retriever.get_counter())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
