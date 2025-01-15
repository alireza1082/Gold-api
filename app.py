from flask import Flask

import retriever

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "<p>An api returns Gold price.</p>"


@app.route("/gold")
def gold_price():
    return retriever.get_price()
