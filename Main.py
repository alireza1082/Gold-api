from flask import Flask
from werkzeug.exceptions import abort

import api.api_price as api

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>An api returns Gold price.</p>"

@app.route("/gold")
def gold_price():
    tgju = api.get_price_from_tgju()
    bon = api.get_price_from_bonbast()
    if tgju > bon:
        return tgju
    if bon == 0:
        abort(404, description="Resource not found")
    return bon