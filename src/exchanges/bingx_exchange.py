# src/exchanges/bingx_exchange.py

import requests
import json
import time
import hmac
import hashlib
from typing import Dict, Any, Optional, List
import os
from src.exchanges.base_exchange import BaseExchange

class BingXClient(BaseExchange):
    def __init__(self, api_key_env: str, secret_key_env: str, is_testnet: bool = False):
        self.api_key = os.getenv(api_key_env)
        self.secret_key = os.getenv(secret_key_env)
        if not self.api_key or not self.secret_key:
            raise ValueError(f"API key or secret key not found in environment variables: {api_key_env}, {secret_key_env}")

        base_url = "https://open-api.bingx.com" # Mainnet
        # BingX может не иметь отдельного URL для тестнета swap, проверь документацию
        # if is_testnet:
        #    base_url = "https://...testnet..."
        self.base_url = base_url
        self.exchange_url = f"{self.base_url}/openApi/swap/v2/trade"
        self.account_url = f"{self.base_url}/openApi/swap/v2/trade"
        self.market_url = f"{self.base_url}/openApi/market"

    def _sign_request(self, params: Dict[str, Any], endpoint: str, method: str = "GET"):
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, data: str = None) -> Optional[Dict[str, Any]]:
        if params is None:
            params = {}
        headers = {"X-BX-APIKEY": self.api_key}

        if method in ["POST", "PUT", "DELETE"]:
            # Подпись для POST часто добавляется в заголовок или в body, проверь документацию
            # Пока добавим timestamp и подпись в params как для GET
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._sign_request(params, endpoint, method)
            url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
            try:
                response = requests.request(method, url, headers=headers, data=data)
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                return None
        else: # GET
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._sign_request(params, endpoint, method)
            url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
            try:
                response = requests.request(method, url, headers=headers)
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                return None

        if response.status_code != 200:
            print(f"BingX API request failed: {response.status_code} - {response.text}")
            return None

        try:
            return response.json()
        except json.JSONDecodeError:
            print("Failed to decode JSON response from BingX")
            return None

    def get_account_info(self) -> Dict[str, Any]:
        endpoint = "/openApi/swap/v2/trade/account"
        params = {}
        response = self._make_request("GET", endpoint, params)
        if response and response.get('code') == 0: # Предполагаемый формат ответа
            # Пример: {"code": 0, "msg": "...", "data": {...}}
            data = response.get('data', {})
            # Преобразуем под общий формат
            # Найди в data поле с общей стоимостью счёта
            account_value = float(data.get('balance', 0.0)) # Замените 'balance' на реальное поле из API
            return {
                "accountValue": account_value,
                "raw_response": data
            }
        return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        endpoint = "/openApi/swap/v2/trade/position"
        params = {}
        response = self._make_request("GET", endpoint, params)
        if response and response.get('code') == 0:
            data = response.get('data', [])
            positions = []
            for pos in data:
                # Пример структуры из API BingX (проверь документацию!)
                # {"symbol": "BTC/USDT", "positionAmt": "0.001", "entryPrice": "40000", ...}
                positions.append({
                    "symbol": pos["symbol"].replace("/", ""), # Приводим к формату BTC (если нужно)
                    "side": "LONG" if float(pos["positionAmt"]) > 0 else "SHORT",
                    "quantity": abs(float(pos["positionAmt"])),
                    "entryPrice": float(pos["entryPrice"]),
                    # "leverage": float(pos.get("leverage", 1)), # Проверь, есть ли в ответе
                    "unrealizedPnl": float(pos.get("unrealizedProfit", 0.0)),
                    # "liquidationPrice": float(pos.get("liquidationPrice", 0.0)) # Проверь
                })
            return positions
        return []

    def get_all_mids(self) -> Dict[str, float]:
        # BingX не предоставляет allMids напрямую. Нужно запрашивать цены по отдельности или через WebSocket.
        # Заглушка: запросим цены для основных пар
        coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "XRPUSDT"]
        mids = {}
        for symbol in coins:
            ticker_resp = self._make_request("GET", f"/openApi/quote/v1/ticker/price", {"symbol": symbol})
            if ticker_resp and ticker_resp.get('code') == 0:
                price = float(ticker_resp['data']['price'])
                # Упрощённо считаем mid как текущую цену
                mids[symbol.replace("USDT", "")] = price
        return mids

    def place_order(self, symbol: str, side: str, quantity: float, limit_px: float, order_type: str = "limit", reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        endpoint = "/openApi/swap/v2/trade/order"
        # Проверь документацию BingX для точного формата
        params = {
            "symbol": f"{symbol}USDT", # BingX часто использует USDT пары
            "side": side.upper(), # "BUY" или "SELL"
            "type": order_type.upper(), # "LIMIT", "MARKET" и т.д.
            "quantity": quantity,
            "price": limit_px, # Требуется для LIMIT
            "timeInForce": "GTC", # Или другой TIF
        }
        if reduce_only:
             params["reduceOnly"] = "true"
        # Не забудь timestamp и подпись
        params['timestamp'] = int(time.time() * 1000)
        params['signature'] = self._sign_request(params, endpoint, "POST")
        url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
        headers = {"X-BX-APIKEY": self.api_key, "Content-Type": "application/json"}

        try:
            response = requests.post(url, headers=headers)
            if response.status_code == 200:
                 return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error placing order on BingX: {e}")
        return None

    def cancel_order(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        endpoint = "/openApi/swap/v2/trade/cancel"
        params = {
            "symbol": f"{symbol}USDT",
            "orderId": order_id,
        }
        # Подпись
        params['timestamp'] = int(time.time() * 1000)
        params['signature'] = self._sign_request(params, endpoint, "DELETE")
        return self._make_request("DELETE", endpoint, params)

    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        endpoint = "/openApi/market/v1/kline"
        params = {
            "symbol": f"{symbol}USDT", # BingX часто использует USDT пары
            "interval": interval,
            "limit": limit
        }
        # GET запрос не требует подписи в параметрах
        url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                raw_data = response.json()
                if raw_data.get('code') == 0:
                    # Пример: [{"openTime": 123, "open": "40000", ...}]
                    # Преобразуем к формату: [{"t": ..., "o": ..., "h": ..., "l": ..., "c": ..., "v": ...}]
                    klines = []
                    for k in raw_data.get('data', []):
                         kline = {
                             "t": int(k[0]),   # openTime
                             "o": float(k[1]), # open
                             "h": float(k[2]), # high
                             "l": float(k[3]), # low
                             "c": float(k[4]), # close
                             "v": float(k[5]), # volume
                         }
                         klines.append(kline)
                    return klines
        except Exception as e:
            print(f"Error fetching klines for {symbol} on BingX: {e}")
        return []

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        # Найди соответствующий эндпоинт в документации BingX
        # Пример: /openApi/quote/v1/fundingRate
        endpoint = "/openApi/quote/v1/fundingRate"
        params = {"symbol": f"{symbol}USDT"}
        response = self._make_request("GET", endpoint, params)
        if response and response.get('code') == 0:
            data = response.get('data', {})
            # Найди поле с funding rate, например 'fundingRate'
            rate_str = data.get('fundingRate')
            if rate_str:
                return float(rate_str)
        return None

    def get_open_interest(self, symbol: str) -> Optional[float]:
        # Найди соответствующий эндпоинт в документации BingX
        # BingX может не предоставлять open interest напрямую через API
        print(f"Open Interest for {symbol} on BingX: Not directly available via API or not implemented.")
        # Заглушка
        return None
