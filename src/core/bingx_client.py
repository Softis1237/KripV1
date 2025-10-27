# src/core/bingx_client.py

import requests
import json
import time
import hmac
import hashlib
from typing import Dict, Any, Optional
import os

class BingXClient:
    def __init__(self, api_key_env: str, secret_key_env: str, is_testnet: bool = False):
        self.api_key = os.getenv(api_key_env)
        self.secret_key = os.getenv(secret_key_env)
        if not self.api_key or not self.secret_key:
            raise ValueError(f"API key or secret key not found in environment variables: {api_key_env}, {secret_key_env}")

        # Выбери URL в зависимости от testnet или нет
        base_url = "https://open-api.bingx.com" # Mainnet
        if is_testnet:
            base_url = "https://open-api-swap.bingx.com" # Testnet (если есть)
        self.base_url = base_url
        self.exchange_url = f"{self.base_url}/openApi/swap/v2/trade"
        self.account_url = f"{self.base_url}/openApi/swap/v2/trade"
        self.market_url = f"{self.base_url}/openApi/market"

    def _sign_request(self, params: Dict[str, Any], endpoint: str, method: str = "GET"):
        """
        Подписывает запрос к API BingX.
        """
        # Сортируем параметры по ключу
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        # Создаем подпись
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, data: str = None) -> Optional[Dict[str, Any]]:
        """
        Делает подписаный запрос к API BingX.
        """
        if params is None:
            params = {}
        if method in ["POST", "PUT", "DELETE"]:
            # Для POST запросов подпись добавляется в заголовок
            signature = self._sign_request({}, endpoint, method) # Подпись для body не всегда нужна, зависит от API
            headers = {
                "X-BX-APIKEY": self.api_key,
                "Content-Type": "application/json"
            }
            # Обычно подпись добавляется как параметр в URL или в body
            # Пример: params['timestamp'] = int(time.time() * 1000)
            # params['signature'] = signature
            url = f"{self.base_url}{endpoint}"
            try:
                response = requests.request(method, url, headers=headers, data=data)
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                return None
        else: # GET
            params['timestamp'] = int(time.time() * 1000)
            signature = self._sign_request(params, endpoint, method)
            params['signature'] = signature
            headers = {
                "X-BX-APIKEY": self.api_key
            }
            url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
            try:
                response = requests.request(method, url, headers=headers)
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                return None

        if response.status_code != 200:
            print(f"API request failed: {response.status_code} - {response.text}")
            return None

        try:
            return response.json()
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
            return None

    def get_account_info(self):
        """
        Получает информацию о счёте (баланс, позиции).
        Endpoint: GET /openApi/swap/v2/trade/account
        """
        endpoint = "/openApi/swap/v2/trade/account"
        params = {}
        return self._make_request("GET", endpoint, params)

    def get_position_info(self, symbol: str = None):
        """
        Получает информацию о позициях.
        Endpoint: GET /openApi/swap/v2/trade/position
        """
        endpoint = "/openApi/swap/v2/trade/position"
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._make_request("GET", endpoint, params)

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None, reduce_only: bool = False):
        """
        Размещает ордер.
        Endpoint: POST /openApi/swap/v2/trade/order
        side: BUY, SELL
        order_type: MARKET, LIMIT, STOP, TAKE_PROFIT
        """
        endpoint = "/openApi/swap/v2/trade/order"
        # Пример payload (может отличаться в зависимости от order_type)
        payload = {
            "symbol": symbol,
            "side": side.upper(), # "BUY" или "SELL"
            "type": order_type.upper(), # "LIMIT", "MARKET", "STOP", "TAKE_PROFIT"
            "quantity": quantity,
            "timestamp": int(time.time() * 1000)
        }
        if order_type.upper() in ["LIMIT", "STOP", "TAKE_PROFIT"]:
            if price is None:
                raise ValueError("Price is required for LIMIT, STOP, TAKE_PROFIT orders")
            payload["price"] = price
        if reduce_only:
            payload["reduceOnly"] = "true" # В API может быть строка "true"/"false"

        payload['signature'] = self._sign_request({}, endpoint, "POST") # Подпись для body

        data_str = json.dumps(payload, separators=(',', ':')) # Важно: без пробелов
        return self._make_request("POST", endpoint, data=data_str)

    def cancel_order(self, symbol: str, order_id: str):
        """
        Отменяет ордер.
        Endpoint: DELETE /openApi/swap/v2/trade/cancel
        """
        endpoint = "/openApi/swap/v2/trade/cancel"
        params = {
            "symbol": symbol,
            "orderId": order_id,
            "timestamp": int(time.time() * 1000)
        }
        # Подпись
        params['signature'] = self._sign_request(params, endpoint, "DELETE")
        return self._make_request("DELETE", endpoint, params)

    def get_klines(self, symbol: str, interval: str, limit: int = 500):
        """
        Получает свечи (OHLCV).
        Endpoint: GET /openApi/market/v1/kline
        interval: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M
        """
        endpoint = "/openApi/market/v1/kline"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        return self._make_request("GET", endpoint, params)

    # --- Добавь другие методы по необходимости: get_funding_rate, get_open_interest и т.д. ---
