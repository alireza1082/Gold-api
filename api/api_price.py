import requests

from config import config_api


def get_price_from_tgju():
    return "0"
    url = "https://one-api.ir/price/"
    # one-api token
    token = config_api.api_token
    parameters = {
        'token': token,
        'action': 'tgju'
    }
    response = requests.post(url, parameters)
    if response.status_code == 200:
        # check app is available on market
        if response.json()['status'] == 404:
            print("tgju request failed with status 404")
            return "0"
        elif response.json()['status'] == 500:
            print("tgju request failed with status 500")
            return "0"
        elif response.json()['status'] == 200:
            print("request successfully on tgju.")
    else:
        print("failed on tgju api")
        return "0"
    print(response.json()['status'])
    link = response.json()['result']['gold']['geram18']['p']
    new_version = ''.join((ch if ch in '0123456789' else '') for ch in link)
    print(new_version[:-1])
    rond = int(new_version[:-4])
    return str(rond + 1)


def get_price_from_bonbast():
    url = "https://one-api.ir/price/"
    # one-api token
    token = config_api.api_token
    parameters = {
        'token': token,
        'action': 'bonbast'
    }
    response = requests.post(url, parameters)
    if response.status_code == 200:
        # check price retrieved successfully
        if response.json()['status'] == 404:
            print("request failed with status 404")
            return "0"
        elif response.json()['status'] == 500:
            print("request failed with status 500")
            return "0"
        elif response.json()['status'] == 200:
            print("request successfully on Bonbast.")
    else:
        print("failed on Bonbast api")
        return "0"
    link = response.json()['result']['gol18']
    new_version = ''.join((ch if ch in '0123456789' else '') for ch in link)
    print(new_version)
    rond = int(new_version[:-3])
    return str(rond + 1)
