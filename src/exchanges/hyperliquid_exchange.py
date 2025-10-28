# src/exchanges/hyperliquid_exchange.py

import requests
import json
import time
import hmac
import hashlib
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
from typing import Dict, Any, Optional, List
import os
from src.exchanges.base_exchange import BaseExchange

class HyperliquidExchange(BaseExchange):
    def __init__(self, wallet_address: str, private_key_env: str, is_testnet: bool = False):
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.private_key_hex = os.getenv(private_key_env)
        if not self.private_key_hex:
            raise ValueError(f"Private key not found in environment variable: {private_key_env}")
        if not self.private_key_hex.startswith("0x"):
            self.private_key_hex = "0x" + self.private_key_hex

        self.account = Account.from_key(self.private_key_hex)
        self.user_address = self.account.address

        # Выбираем URL в зависимости от testnet
        base_url = "https://api.hyperliquid.xyz"
        if is_testnet:
            base_url = "https://api.hyperliquid-testnet.xyz"
        self.base_url = base_url
        self.exchange_url = f"{self.base_url}/exchange"
        self.info_url = f"{self.base_url}/info"

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        payload_str = json.dumps(payload, separators=(',', ':'))
        message = encode_defunct(text=payload_str)
        signed_message = self.account.sign_message(message)
        return signed_message.signature.hex()

    def _make_request(self, payload: Dict[str, Any], url: str) -> Optional[Dict[str, Any]]:
        signature = self._sign_payload(payload)
        headers = {"Content-Type": "application/json"}

        payload_with_sig = {
            "signature": signature,
            "nonce": int(time.time() * 1000),
            "user": self.user_address
        }
        payload_with_sig.update(payload)

        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload_with_sig))
            if response.status_code != 200:
                print(f"API request failed: {response.status_code} - {response.text}")
                return None
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
            return None

    def _post_info(self, payload: Dict[str, Any]) -> Optional[Any]:
        """
        Performs an unsigned POST request to the /info endpoint.
        """
        try:
            response = requests.post(self.info_url, json=payload)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Info request failed: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Info request error: {e}")
            return None
        except json.JSONDecodeError:
            print("Failed to decode JSON response")
            return None

    def _get_asset_index(self, symbol: str) -> Optional[int]:
        """
        Retrieves the asset index for a given symbol from metaAndAssetCtxs.
        """
        payload = {"type": "metaAndAssetCtxs"}
        data = self._post_info(payload)
        if not data:
            return None
        universe = data[0]["universe"]
        for i, asset in enumerate(universe):
            if asset["name"] == symbol:
                return i
        return None

    def get_account_info(self) -> Dict[str, Any]:
        payload = {"type": "clearinghouseState", "user": self.user_address}
        response = self._post_info(payload)
        if response:
            # Обработка ответа, например, извлечение accountValue
            margin_summary = response.get("marginSummary", {})
            account_value = float(margin_summary.get("accountValue", response.get("accountValue", 0.0)))
            # ... другие поля ...
            return {
                "accountValue": account_value,
                "raw_response": response # Возвратим сырой ответ для дальнейшей обработки в account_state
            }
        return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        payload = {"type": "clearinghouseState", "user": self.user_address}
        response = self._post_info(payload)
        if response:
            positions_raw = response.get("assetPositions", [])
            # Преобразуем из формата HL в общий формат
            positions = []
            for pos in positions_raw:
                position_value = float(pos.get("positionValue", 0))
                if position_value != 0: # Только открытые
                    szi = float(pos.get("szi", 0))
                    side = "LONG" if szi > 0 else "SHORT"
                    quantity = abs(szi)
                    entry_price = float(pos["entryPx"])
                    leverage_obj = pos.get("leverage", {"value": 1})
                    leverage = float(leverage_obj.get("value", 1))
                    unrealized_pnl = float(pos["unrealizedPnl"])
                    liquidation_price = float(pos.get("liquidationPx", 0.0))
                    positions.append({
                        "symbol": pos["coin"],
                        "side": side,
                        "quantity": quantity,
                        "entryPrice": entry_price,
                        "leverage": leverage,
                        "unrealizedPnl": unrealized_pnl,
                        "liquidationPrice": liquidation_price
                    })
            return positions
        return []

    def get_all_mids(self) -> Dict[str, float]:
        payload = {"type": "allMids"}
        data = self._post_info(payload)
        if data:
            # Преобразуем строки в float
            return {k: float(v) for k, v in data.items()}
        return {}

    def place_order(self, symbol: str, side: str, quantity: float, limit_px: float, order_type: str = "limit", reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        asset_idx = self._get_asset_index(symbol)
        if asset_idx is None:
            print(f"[Hyperliquid] Unknown symbol: {symbol}")
            return None

        if order_type.lower() != "limit":
            print("Hyperliquid client only implements limit orders in this example.")
            # Для рыночных ордеров нужно другое поле
            order_type_obj = {"market": {}}
        else:
            order_type_obj = {"limit": {"tif": "Gtc"}}

        req = {
            "asset": asset_idx,
            "isBuy": side.upper() == "BUY",
            "sz": quantity,
            "limitPx": limit_px,
            "orderType": order_type_obj,
            "reduceOnly": reduce_only,
        }
        payload = {
            "type": "order",
            "req": req
        }
        print(f"[Hyperliquid] Placing {side.upper()} order for {quantity} {symbol} @ {limit_px}")
        return self._make_request(payload["req"], self.exchange_url)

    def cancel_order(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        # В Hyperliquid cancellation по ID ордера
        # Требуется ID конкретного ордера, который обычно приходит при создании
        # Этот метод требует доработки, если order_id - это ID из HL
        print(f"[Hyperliquid] Cancelling order {order_id} for {symbol} - Requires specific HL order ID.")
        # Заглушка - не реализовано полноценно без прямого ID
        return None

    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        # Hyperliquid использует /history для свечей
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": interval,
                "num": limit
            }
        }
        raw_data = self._post_info(payload) # Вместо прямого requests.post
        if raw_data and isinstance(raw_data, list):
            # Преобразуем поля в числа
            for item in raw_data:
                for key in ['t', 'o', 'h', 'l', 'c', 'v']:
                    if key in item:
                        item[key] = float(item[key])
            return raw_data
        return []

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        try:
            payload = {"type": "metaAndAssetCtxs"}
            data = self._post_info(payload) # Вместо прямого requests.post
            if not data:
                return None
            universe = data[0]["universe"]
            asset_ctxs = data[1]
            coin_idx = next((i for i, x in enumerate(universe) if x["name"] == symbol), None)
            if coin_idx is not None:
                funding_str = asset_ctxs[coin_idx]["funding"]
                return float(funding_str)
        except (IndexError, KeyError, ValueError, TypeError) as e:
            print(f"[Hyperliquid] Error fetching funding rate for {symbol}: {e}")
        return None

    def get_open_interest(self, symbol: str) -> Optional[float]:
        try:
            payload = {"type": "metaAndAssetCtxs"}
            data = self._post_info(payload) # Вместо прямого requests.post
            if not data:
                return None
            universe = data[0]["universe"]
            asset_ctxs = data[1]
            coin_idx = next((i for i, x in enumerate(universe) if x["name"] == symbol), None)
            if coin_idx is not None:
                oi = asset_ctxs[coin_idx]["openInterest"]
                return float(oi)
        except (IndexError, KeyError, ValueError, TypeError) as e:
            print(f"[Hyperliquid] Error fetching open interest for {symbol}: {e}")
        return None