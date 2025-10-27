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

        # Убираем лишние пробелы из URL
        base_url = "https://open-api.bingx.com" # Mainnet
        self.base_url = base_url
        self.exchange_url = f"{self.base_url}/openApi/swap/v2/trade"
        self.account_url = f"{self.base_url}/openApi/swap/v2/trade"
        self.market_url = f"{self.base_url}/openApi/market"
        self.quote_url = f"{self.base_url}/openApi/quote/v1" # Для публичных данных

    def _sign_payload(self, payload_str: str) -> str:
        """Подписывает строку параметров."""
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, data: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Делает подписаный запрос к API BingX.
        Для GET: параметры в URL, подпись в параметрах.
        Для POST: параметры в теле (data), подпись в параметрах или в теле, в зависимости от эндпоинта.
        BingX документация: подпись часто идёт в параметрах строки запроса, даже для POST.
        """
        if params is None:
            params = {}
        if data is None:
            data_to_sign = params.copy()
        else:
            # Для POST, часто подпись формируется от объединённых параметров
            # Проверим документацию: подпись может быть в params даже для POST
            # Документация BingX: "The signature is generated based on the request parameters."
            # Обычно это означает, что подпись формируется от всех *подписываемых* параметров, включая тело.
            # Но в API BingX часто подпись идёт в параметрах строки запроса (query params).
            # Попробуем сначала добавить timestamp и сформировать подпись от params + data.
            # Правильный способ: все параметры, которые должны быть подписаны, объединяются в строку.
            # Для POST, часто это: все параметры в теле + timestamp, подпись формируется от этой строки.
            # Или: все параметры в query + timestamp, подпись формируется от query.
            # Проверим документацию. Часто для POST swap API подпись идёт в query.
            # Попробуем так: добавим timestamp к params, объединим с data, отсортируем, подпишем, добавим в query.
            # Это стандартный способ для многих API.
            all_params = params.copy()
            all_params.update(data)
            all_params['timestamp'] = int(time.time() * 1000)
            # Сортируем и создаем строку для подписи
            sorted_params_str = '&'.join(f"{k}={v}" for k, v in sorted(all_params.items()))
            signature = self._sign_payload(sorted_params_str)
            all_params['signature'] = signature

            headers = {"X-BX-APIKEY": self.api_key, "Content-Type": "application/x-www-form-urlencoded"}
            url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in all_params.items()]) }"
            try:
                response = requests.post(url, headers=headers)
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

        # --- GET REQUEST ---
        if method == "GET":
            params['timestamp'] = int(time.time() * 1000)
            # Сортируем и создаем строку для подписи
            sorted_params_str = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
            signature = self._sign_payload(sorted_params_str)
            params['signature'] = signature

            headers = {"X-BX-APIKEY": self.api_key}
            url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
            try:
                response = requests.get(url, headers=headers)
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

        # --- POST REQUEST (исправленный) ---
        # NOTE: Этот блок кода перемещён выше, так как логика для POST отличается.
        # Правильный способ для BingX Swap POST:
        # 1. Подготовить тело запроса (data)
        # 2. Добавить timestamp к телу (или к параметрам строки, документация не всегда ясна)
        # 3. Сформировать строку из ОТСОРТИРОВАННЫХ пар ключ=значение из ТЕЛА (и, возможно, query params)
        # 4. Подписать эту строку
        # 5. Отправить тело + подпись (часто подпись идёт в query params даже для POST!)
        # Это контринтуитивно, но так делают многие API.
        # Попробуем следующую логику:
        # - Для POST, добавляем timestamp к data
        # - Сортируем ВСЕ пары (из data) в строку
        # - Подписываем строку
        # - Отправляем data как application/x-www-form-urlencoded
        # - Подпись добавляем как параметр строки запроса.
        # Это соответствует примерам из документации BingX для swap.
        if method == "POST":
            # Подготовим данные для подписи
            data_to_sign = data.copy() if data else {}
            data_to_sign['timestamp'] = int(time.time() * 1000)
            # Сортируем и создаем строку для подписи
            sorted_data_str = '&'.join(f"{k}={v}" for k, v in sorted(data_to_sign.items()))
            signature = self._sign_payload(sorted_data_str)

            headers = {"X-BX-APIKEY": self.api_key, "Content-Type": "application/x-www-form-urlencoded"}
            # Подпись идёт в параметрах строки запроса даже для POST
            url = f"{self.base_url}{endpoint}?signature={signature}"
            # Тело - только данные
            body_str = '&'.join(f"{k}={v}" for k, v in sorted(data.items()))
            try:
                response = requests.post(url, headers=headers, data=body_str)
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

        # Для DELETE логика будет аналогична GET
        if method == "DELETE":
             params['timestamp'] = int(time.time() * 1000)
             sorted_params_str = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
             signature = self._sign_payload(sorted_params_str)
             params['signature'] = signature

             headers = {"X-BX-APIKEY": self.api_key}
             url = f"{self.base_url}{endpoint}?{ '&'.join([f'{k}={v}' for k, v in params.items()]) }"
             try:
                 response = requests.delete(url, headers=headers)
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

        return None


    def get_account_info(self) -> Dict[str, Any]:
        endpoint = "/openApi/swap/v2/trade/account"
        params = {}
        response = self._make_request("GET", endpoint, params=params)
        if response and response.get('code') == 0:
            data = response.get('data', {})
            # BingX использует 'updateTime' и 'totalWalletBalance' или 'totalMarginBalance' как 'accountValue'?
            # Проверим документацию. 'totalMarginBalance' вероятно ближе к 'accountValue' в HL.
            account_value = float(data.get('totalMarginBalance', data.get('totalWalletBalance', 0.0)))
            return {
                "accountValue": account_value,
                "raw_response": data
            }
        return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        endpoint = "/openApi/swap/v2/trade/position"
        params = {}
        response = self._make_request("GET", endpoint, params=params)
        if response and response.get('code') == 0:
            data = response.get('data', [])
            positions = []
            for pos in data:
                # BingX использует "BTC-USDT", приведём к "BTC"
                symbol_clean = pos["symbol"].replace("-USDT", "")
                positions.append({
                    "symbol": symbol_clean,
                    "side": "LONG" if float(pos["positionAmt"]) > 0 else "SHORT",
                    "quantity": abs(float(pos["positionAmt"])),
                    "entryPrice": float(pos["entryPrice"]),
                    "leverage": int(pos.get("leverage", 1)),
                    "unrealizedPnl": float(pos.get("unrealizedProfit", 0.0)),
                    "liquidationPrice": float(pos.get("liquidationPrice", 0.0))
                })
            return positions
        return []

    def get_all_mids(self) -> Dict[str, float]:
        # Используем quote endpoint
        coins = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "DOGE-USDT", "XRP-USDT"]
        mids = {}
        for symbol in coins:
            # Используем правильный эндпоинт и URL
            ticker_resp = self._make_request("GET", f"/quote/ticker/price", params={"symbol": symbol})
            if ticker_resp and ticker_resp.get('code') == 0:
                price = float(ticker_resp['data']['price'])
                mids[symbol.replace("-USDT", "")] = price
        return mids

    def place_order(self, symbol: str, side: str, quantity: float, limit_px: float, order_type: str = "LIMIT", reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        endpoint = "/openApi/swap/v2/trade/order"
        # Подготовим тело запроса
        data = {
            "symbol": f"{symbol}-USDT", # BingX использует дефис
            "side": side.upper(),
            "type": order_type.upper(), # LIMIT, MARKET
            "quantity": quantity,
            "price": limit_px,
            "timeInForce": "GTC", # Или другой TIF
        }
        if reduce_only:
            data["reduceOnly"] = "true"

        # _make_request сам добавит timestamp и подпись
        response = self._make_request("POST", endpoint, data=data)
        return response


    def cancel_order(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        endpoint = "/openApi/swap/v2/trade/cancel"
        params = {
            "symbol": f"{symbol}-USDT",
            "orderId": order_id,
        }
        # _make_request сам добавит timestamp и подпись
        return self._make_request("DELETE", endpoint, params=params)


    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        endpoint = "/openApi/market/v1/kline"
        params = {
            "symbol": f"{symbol}-USDT", # Используем дефис
            "interval": interval,
            "limit": limit
        }
        # GET запрос
        response = self._make_request("GET", endpoint, params=params)
        if response and response.get('code') == 0:
            raw_data = response.get('data', [])
            klines = []
            for k in raw_data:
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
        return []


    def get_funding_rate(self, symbol: str) -> Optional[float]:
        endpoint = "/quote/v1/fundingRate"
        params = {"symbol": f"{symbol}-USDT"}
        response = self._make_request("GET", endpoint, params=params)
        if response and response.get('code') == 0:
            data = response.get('data', {})
            # Ключ может быть 'fundingRate' или другим, проверь реальный ответ
            rate_str = data.get('fundingRate')
            if rate_str:
                return float(rate_str)
        return None


    def get_open_interest(self, symbol: str) -> Optional[float]:
        # BingX может не предоставлять это напрямую или через другой эндпоинт.
        # Оставим как есть или поищем эндпоинт.
        # На данный момент, оставим заглушку.
        print(f"Open Interest for {symbol} on BingX: Not directly available via standard API or not implemented.")
        return None
