import requests

from config import config_api


def get_price_from_tgju():
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
    rond = int(new_version[:-4])
    print("price on tgju api is: ", str(rond + 1))
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
    rond = int(new_version[:-3])
    print("price on bon api is: ", str(rond + 1))
    return str(rond + 1)


def get_usd_brs():
    price = 0
    url = "https://BrsApi.ir/Api/Market/Gold_Currency_Pro.php"
    # one-api token
    brs_key = config_api.brs_api_token

    parameters = {
        'key': brs_key,
        'section': 'currency'
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/106.0.0.0",
        "Accept": "application/json, text/plain, */*"
    }

    response = requests.get(url, params=parameters, headers=headers)

    if response.status_code == 200:
        print("Successful brs request!")
    else:
        print(f"Error brs: {response.status_code}")
        return 0
    link = response.json()['currency']['free']

    for pr in link:
        if pr['symbol'] == 'USD':
            print(pr)
            price = pr['price']
    return str(int(price / 10))
