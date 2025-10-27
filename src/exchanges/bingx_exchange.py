# src/exchanges/bingx_exchange.py

import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode, quote
from typing import Dict, Any, Optional, List
import os
from src.exchanges.base_exchange import BaseExchange

# --- Вспомогательные функции ---
def _now_ms():
    return int(time.time() * 1000)

def _encode(params: dict) -> str:
    # Сортировка по ключу, фильтрация None значений, URL-кодирование
    filtered = {k: v for k, v in params.items() if v is not None}
    return urlencode(sorted(filtered.items()), quote_via=quote, safe='')

def _sign(secret: str, query_str: str) -> str:
    # HMAC-SHA256 в hex
    return hmac.new(secret.encode(), query_str.encode(), hashlib.sha256).hexdigest()

class BingXClient(BaseExchange):
    def __init__(self, api_key_env: str, secret_key_env: str, is_testnet: bool = False, recv_window: int = 5000):
        self.api_key = os.getenv(api_key_env)
        self.secret_key = os.getenv(secret_key_env)
        if not self.api_key or not self.secret_key:
            raise ValueError(f"API key or secret key not found in environment variable: {api_key_env}, {secret_key_env}")

        base_url = "https://open-api.bingx.com" # Mainnet
        self.base_url = base_url
        self.recv_window = recv_window

    def _make_request(self, method: str, path: str, params: Dict[str, Any] = None, signed: bool = False):
        params = params.copy() if params else {}

        headers = {}
        if signed:
            # Добавляем timestamp и recvWindow для приватных запросов
            params.update({"timestamp": _now_ms(), "recvWindow": self.recv_window})
            # Формируем строку для подписи
            query_str = _encode(params)
            signature = _sign(self.secret_key, query_str)
            # Добавляем подпись к параметрам (в query string для GET, в body для POST)
            params["signature"] = signature
            headers["X-BX-APIKEY"] = self.api_key

        url = self.base_url + path
        if method == "GET":
            # Для GET запросов параметры и подпись идут в URL
            full_url = f"{url}?{_encode(params)}"
            r = requests.get(full_url, headers=headers, timeout=15)
        else: # POST / DELETE (BingX использует POST для отмены)
            # Для POST запросов параметры (без подписи) идут в теле, подпись в query или теле (чаще в query)
            # BingX документация: подпись часто в query параметрах
            signature = params.pop("signature", None)
            query_part = f"?signature={signature}" if signature else ""
            full_url = f"{url}{query_part}"
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            r = requests.post(full_url, data=_encode(params), headers=headers, timeout=15)

        text = r.text
        try:
            data = r.json()
        except Exception:
            raise RuntimeError(f"HTTP {r.status_code}: {text}")

        code = data.get("code")
        if code not in (0, "0"):
            raise RuntimeError(f"BingX error code={code} msg={data.get('msg')} raw={text}")

        return data.get("data")


    # --- Реализация интерфейса BaseExchange ---
    def get_account_info(self) -> Dict[str, Any]:
        # GET /openApi/swap/v2/user/balance
        try:
            data = self._make_request("GET", "/openApi/swap/v2/user/balance", signed=True)
            print(f"[DEBUG] Raw balance data from API: {data}")
            # Структура: {"balance": {"equity": "105.0", "balance": "100.0", ...}}
            # Извлекаем вложенный словарь
            balance_info = data.get('balance', {})
            print(f"[DEBUG] Balance info dict: {balance_info}")

            # Теперь ищем equity и balance внутри balance_info
            equity_str = balance_info.get('equity')
            balance_str = balance_info.get('balance')

            account_value = 0.0
            if equity_str is not None:
                account_value = float(equity_str)
            elif balance_str is not None:
                account_value = float(balance_str)

            return {
                "accountValue": account_value,
                "raw_response": data
            }
        except RuntimeError as e:
            print(f"Error fetching account info: {e}")
            return {}
        except (ValueError, TypeError) as e: # Обработка ошибки float()
            print(f"Error parsing account value from  {e}. Raw  {data}")
            return {
                "accountValue": 0.0,
                "raw_response": data
            }

    def get_positions(self) -> List[Dict[str, Any]]:
        # GET /openApi/swap/v2/user/positions
        try:
            data = self._make_request("GET", "/openApi/swap/v2/user/positions", signed=True)
            # Пример структуры: [{"positionAmt": "0.1", "symbol": "BTC-USDT", "entryPrice": "40000", ...}, ...]
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
        except RuntimeError as e:
            print(f"Error fetching positions: {e}")
            return []

    def get_all_mids(self) -> Dict[str, float]:
        # GET /openApi/swap/v2/quote/price (публичный)
        coins = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"]
        mids = {}
        for coin in coins:
            symbol = f"{coin}-USDT"
            try:
                # Важно: новый эндпоинт
                data = self._make_request("GET", "/openApi/swap/v2/quote/price", params={"symbol": symbol}, signed=False)
                # Пример: {"symbol": "BTC-USDT", "price": "41000.50", ...}
                price = float(data["price"]) # Используем "price" вместо "lastPrice"
                mids[coin] = price
            except RuntimeError as e:
                print(f"Error fetching mid price for {symbol}: {e}")
        return mids

    def place_order(self, symbol: str, side: str, quantity: float, limit_px: float, order_type: str = "LIMIT", reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/order
        endpoint = "/openApi/swap/v2/trade/order"
        body_data = {
            "symbol": f"{symbol}-USDT", # Важно: формат пары
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
            "price": limit_px,
            "timeInForce": "GTC", # или другой
        }
        if reduce_only:
            body_data["reduceOnly"] = "true" # BingX использует строку "true"/"false"

        try:
            response_data = self._make_request("POST", endpoint, params=body_data, signed=True)
            print(f"Order placed successfully: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error placing order: {e}")
            return None

    def cancel_order(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/order (для отмены используется orderId в теле)
        # BingX использует один эндпоинт для place, cancel, query
        endpoint = "/openApi/swap/v2/trade/order"
        body_data = {
            "symbol": f"{symbol}-USDT",
            "orderId": order_id,
            # Для отмены не нужно указывать другие поля типа side, type
        }
        try:
            # BingX может использовать POST для отмены тоже!
            # Попробуем POST, как в документации к /trade/order
            response_data = self._make_request("POST", endpoint, params=body_data, signed=True)
            print(f"Order {order_id} cancelled successfully: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error cancelling order {order_id}: {e}")
            return None

    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        # GET /openApi/swap/v3/quote/klines (публичный) - ВАЖНО: v3
        endpoint = "/openApi/swap/v3/quote/klines" # ИСПРАВЛЕНО: v3
        params = {
            "symbol": f"{symbol}-USDT", # Важно: формат пары
            "interval": interval,
            "limit": limit
        }
        try:
            raw_klines = self._make_request("GET", endpoint, params=params, signed=False)
            # Пример raw_klines: [{"open": "16725.0", "close": "16725.5", ...}, ...]
            # Преобразуем к стандартному формату: [{"t": ..., "o": ..., "h": ..., "l": ..., "c": ..., "v": ...}]
            klines = []
            for k in raw_klines:
                kline = {
                    "t": int(k["time"]),   # openTime
                    "o": float(k["open"]), # open
                    "h": float(k["high"]), # high
                    "l": float(k["low"]),  # low
                    "c": float(k["close"]),# close
                    "v": float(k["volume"]),# volume
                }
                klines.append(kline)
            return klines
        except RuntimeError as e:
            print(f"Error fetching klines for {symbol}: {e}")
            return []

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        # GET /openApi/swap/v2/quote/fundingRate (публичный)
        endpoint = "/openApi/swap/v2/quote/fundingRate"
        params = {"symbol": f"{symbol}-USDT", "limit": 1} # Важно: формат пары, limit
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            # Пример: [{"fundingRate": "0.00012345", "fundingTime": "1672531200000", ...}]
            if data and isinstance(data, list) and len(data) > 0:
                 rate_str = data[0].get("fundingRate")
                 if rate_str:
                     return float(rate_str)
        except RuntimeError as e:
            print(f"Error fetching funding rate for {symbol}: {e}")
        return None

    def get_open_interest(self, symbol: str) -> Optional[float]:
        # GET /openApi/swap/v2/quote/openInterest (публичный)
        endpoint = "/openApi/swap/v2/quote/openInterest"
        params = {"symbol": f"{symbol}-USDT"}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            # Пример: {"symbol": "BTC-USDT", "openInterest": "12345.67", "time": 1234567890}
            oi_str = data.get("openInterest")
            if oi_str:
                return float(oi_str)
        except RuntimeError as e:
            print(f"Error fetching open interest for {symbol}: {e}")
        return None

    # --- Новые методы на основе списка эндпоинтов ---
    def get_contracts(self) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v2/quote/contracts
        endpoint = "/openApi/swap/v2/quote/contracts"
        try:
            data = self._make_request("GET", endpoint, signed=False)
            return data # Список контрактов
        except RuntimeError as e:
            print(f"Error fetching contracts: {e}")
            return None

    def get_depth(self, symbol: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        # GET /openApi/swap/v2/quote/depth
        endpoint = "/openApi/swap/v2/quote/depth"
        params = {"symbol": f"{symbol}-USDT", "limit": limit}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            return data # {"bids": [...], "asks": [...]}
        except RuntimeError as e:
            print(f"Error fetching depth for {symbol}: {e}")
            return None

    def get_trades(self, symbol: str, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v2/quote/trades
        endpoint = "/openApi/swap/v2/quote/trades"
        params = {"symbol": f"{symbol}-USDT", "limit": limit}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            return data # Список последних сделок
        except RuntimeError as e:
            print(f"Error fetching trades for {symbol}: {e}")
            return None

    def get_premium_index(self, symbol: str) -> Optional[Dict[str, Any]]:
        # GET /openApi/swap/v2/quote/premiumIndex
        endpoint = "/openApi/swap/v2/quote/premiumIndex"
        params = {"symbol": f"{symbol}-USDT"}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            return data # {"symbol": "BTC-USDT", "markPrice": "41000.50", "lastFundingRate": "0.0001", ...}
        except RuntimeError as e:
            print(f"Error fetching premium index for {symbol}: {e}")
            return None

    def get_ticker_24h(self, symbol: str) -> Optional[Dict[str, Any]]:
        # GET /openApi/swap/v2/quote/ticker
        endpoint = "/openApi/swap/v2/quote/ticker"
        params = {"symbol": f"{symbol}-USDT"}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            return data # {"symbol": "BTC-USDT", "priceChange": "100", "priceChangePercent": "0.5", ...}
        except RuntimeError as e:
            print(f"Error fetching 24h ticker for {symbol}: {e}")
            return None

    def get_book_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        # GET /openApi/swap/v2/quote/bookTicker
        endpoint = "/openApi/swap/v2/quote/bookTicker"
        params = {"symbol": f"{symbol}-USDT"}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=False)
            return data # {"symbol": "BTC-USDT", "bidPrice": "40999.5", "askPrice": "41000.5", ...}
        except RuntimeError as e:
            print(f"Error fetching book ticker for {symbol}: {e}")
            return None

    def get_mark_price_klines(self, symbol: str, interval: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v1/market/markPriceKlines
        endpoint = "/openApi/swap/v1/market/markPriceKlines"
        params = {"symbol": f"{symbol}-USDT", "interval": interval, "limit": limit}
        try:
            raw_klines = self._make_request("GET", endpoint, params=params, signed=False)
            # Аналогично get_klines, но для mark-price
            klines = []
            for k in raw_klines:
                kline = {
                    "t": int(k["time"]),   # openTime
                    "o": float(k["open"]), # open
                    "h": float(k["high"]), # high
                    "l": float(k["low"]),  # low
                    "c": float(k["close"]),# close
                    "v": float(k["volume"]),# volume (если есть)
                }
                klines.append(kline)
            return klines
        except RuntimeError as e:
            print(f"Error fetching mark price klines for {symbol}: {e}")
            return None

    def get_income(self, symbol: str = None, income_type: str = None, start_time: int = None, end_time: int = None, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v2/user/income
        endpoint = "/openApi/swap/v2/user/income"
        params = {
            "symbol": f"{symbol}-USDT" if symbol else None,
            "incomeType": income_type, # REALIZED_PNL, FUNDING_FEE, COMMISSION, etc.
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        try:
            data = self._make_request("GET", endpoint, params=params, signed=True)
            return data # Список записей доходов
        except RuntimeError as e:
            print(f"Error fetching income: {e}")
            return None

    def get_commission_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        # GET /openApi/swap/v2/user/commissionRate
        endpoint = "/openApi/swap/v2/user/commissionRate"
        params = {"symbol": f"{symbol}-USDT"}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=True)
            return data # {"symbol": "BTC-USDT", "maker": "0.0002", "taker": "0.0004"}
        except RuntimeError as e:
            print(f"Error fetching commission rate for {symbol}: {e}")
            return None

    def get_open_orders(self, symbol: str = None) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v2/trade/openOrders
        endpoint = "/openApi/swap/v2/trade/openOrders"
        params = {"symbol": f"{symbol}-USDT" if symbol else None}
        try:
            data = self._make_request("GET", endpoint, params=params, signed=True)
            return data # Список открытых ордеров
        except RuntimeError as e:
            print(f"Error fetching open orders: {e}")
            return None

    def cancel_all_open_orders(self, symbol: str) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/allOpenOrders
        endpoint = "/openApi/swap/v2/trade/allOpenOrders"
        params = {"symbol": f"{symbol}-USDT"}
        try:
            response_data = self._make_request("POST", endpoint, params=params, signed=True)
            print(f"All open orders for {symbol} cancelled successfully: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error cancelling all open orders for {symbol}: {e}")
            return None

    def close_all_positions(self, symbol: str = None) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/closeAllPositions
        endpoint = "/openApi/swap/v2/trade/closeAllPositions"
        params = {"symbol": f"{symbol}-USDT" if symbol else None}
        try:
            response_data = self._make_request("POST", endpoint, params=params, signed=True)
            print(f"All positions closed successfully: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error closing all positions: {e}")
            return None

    def get_all_orders(self, symbol: str, start_time: int = None, end_time: int = None, limit: int = 500) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v2/trade/allOrders
        endpoint = "/openApi/swap/v2/trade/allOrders"
        params = {
            "symbol": f"{symbol}-USDT",
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        try:
            data = self._make_request("GET", endpoint, params=params, signed=True)
            return data # История ордеров
        except RuntimeError as e:
            print(f"Error fetching all orders for {symbol}: {e}")
            return None

    def get_all_fills(self, symbol: str, start_time: int = None, end_time: int = None, limit: int = 500) -> Optional[List[Dict[str, Any]]]:
        # GET /openApi/swap/v2/trade/allFillOrders
        endpoint = "/openApi/swap/v2/trade/allFillOrders"
        params = {
            "symbol": f"{symbol}-USDT",
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        try:
            data = self._make_request("GET", endpoint, params=params, signed=True)
            return data # История сделок (fills)
        except RuntimeError as e:
            print(f"Error fetching all fills for {symbol}: {e}")
            return None

    def test_order(self, symbol: str, side: str, quantity: float, limit_px: float, order_type: str = "LIMIT") -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/order/test
        endpoint = "/openApi/swap/v2/trade/order/test"
        body_data = {
            "symbol": f"{symbol}-USDT",
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
            "price": limit_px,
            "timeInForce": "GTC",
        }
        try:
            response_data = self._make_request("POST", endpoint, params=body_data, signed=True)
            print(f"Test order successful: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Test order failed: {e}")
            return None

    def set_leverage(self, symbol: str, leverage: int) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/leverage
        endpoint = "/openApi/swap/v2/trade/leverage"
        params = {
            "symbol": f"{symbol}-USDT",
            "leverage": leverage
        }
        try:
            response_data = self._make_request("POST", endpoint, params=params, signed=True)
            print(f"Leverage for {symbol} set to {leverage}: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error setting leverage for {symbol}: {e}")
            return None

    def set_margin_type(self, symbol: str, margin_type: str) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v2/trade/marginType
        # margin_type: "ISOLATED" или "CROSSED"
        endpoint = "/openApi/swap/v2/trade/marginType"
        params = {
            "symbol": f"{symbol}-USDT",
            "marginType": margin_type.upper()
        }
        try:
            response_data = self._make_request("POST", endpoint, params=params, signed=True)
            print(f"Margin type for {symbol} set to {margin_type}: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error setting margin type for {symbol}: {e}")
            return None

    def set_position_mode(self, dual_side_position: bool) -> Optional[Dict[str, Any]]:
        # POST /openApi/swap/v1/positionSide/dual
        # dual_side_position: True для Hedge Mode, False для One-way Mode
        endpoint = "/openApi/swap/v1/positionSide/dual"
        params = {
            "dualSidePosition": "true" if dual_side_position else "false"
        }
        try:
            response_data = self._make_request("POST", endpoint, params=params, signed=True)
            print(f"Position mode set: {response_data}")
            return response_data
        except RuntimeError as e:
            print(f"Error setting position mode: {e}")
            return None
