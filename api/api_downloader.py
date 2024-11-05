import os
import sys

import requests
from clint.textui import progress


def get_price_from_tgju(pkg, path, string):
    url = "https://one-api.ir/price/"
    # one-api token
    token = '**************'
    parameters = {
        'token': token,
        'action': 'tgju'
    }
    response = requests.post(url, parameters)
    if response.status_code == 200:
        # check app is available on market
        if response.json()['status'] == 404:
            print("request failed with status 404")
            return
        else:
            print("request successfully.")
    else:
        print("failed on tgju api")
        return
    link = response.json()['result']['gold']['geram18']['p']
    print(link)


def get_price_from_bonbast(pkg, path, string):
    url = "https://one-api.ir/price/"
    # one-api token
    token = '***********'
    parameters = {
        'token': token,
        'action': 'bonbast'
    }
    response = requests.post(url, parameters)
    if response.status_code == 200:
        # check app is available on market
        if response.json()['status'] == 404:
            print("request failed with status 404")
            return
        else:
            print("request successfully.")
    else:
        print("failed on tgju api")
        return
    link = response.json()['result']['gol18']
    print(link)


if __name__ == '__main__':
    get_price_from_bonbast("com.BrainLadder.GhashangAbad", "/Downloads/", "")
