from flask import Flask

import retriever

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "<p>An api returns Gold price.</p>"


@app.route("/gold")
def gold_price():
    return retriever.get_gold_price()


@app.route("/usd")
def usd_price():
    return retriever.get_usd_price()


@app.route("/counter")
def get_counter():
    return retriever.get_counter()
