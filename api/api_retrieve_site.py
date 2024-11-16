# coding= utf-8

import requests
from bs4 import BeautifulSoup
from persiantools import digits


def get_tgju_price():
    server_name = "tgju"
    url = "https://www.tgju.org/profile/geram18"
    try:
        resp = requests.get(url.rstrip())
        # arrange file by html tags
        if resp.status_code == 404:
            print("server not responding")
            return 0
        soup = BeautifulSoup(resp.text, 'html.parser').find("span", {"data-col": "info.last_trade.PDrCotVal"})
        if soup is None:
            print("page not downloaded beautiful or structure changed")
            return 0
        version = soup.text
        new_version = ''.join((ch if ch in '0123456789' else '') for ch in version)
        print(new_version[:-1])
        if new_version is not None:
            return new_version[:-1]
        else:
            return 0
    except Exception as ex:
        print("an error occurred in checking " + server_name)
        print(ex)
        return 0


def get_tala_price():
    url = "https://www.tala.ir/price/18k"
    server_name = "tala"
    try:
        resp = requests.get(url)
        if resp.status_code == 404:
            print("server not responding or structure changed")
            return 0
        # arrange file by html tags
        soup = BeautifulSoup(resp.text, 'html.parser').find("h3", {"class": "bg-green-light"})
        # get version by text of before element
        version = soup.text
        version_en = digits.fa_to_en(version)
        # check version name if it has words and remove words
        new_version = ''.join((ch if ch in '0123456789' else '') for ch in version_en)
        # build array of versionName split by .
        print(new_version)
        return new_version
    except Exception as ex:
        print("an error occurred in checking " + server_name)
        print(ex)
        return 0
