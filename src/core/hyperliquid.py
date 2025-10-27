# src/core/hyperliquid.py

import requests
import json
import time
import hmac
import hashlib
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
from typing import Dict, Any, Optional
import os

class HyperliquidClient:
    def __init__(self, wallet_address: str, private_key_env: str):
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.private_key_hex = os.getenv(private_key_env)
        if not self.private_key_hex:
            raise ValueError(f"Private key not found in environment variable: {private_key_env}")
        if not self.private_key_hex.startswith("0x"):
            self.private_key_hex = "0x" + self.private_key_hex

        self.account = Account.from_key(self.private_key_hex)
        self.user_address = self.account.address

        self.base_url = "https://api.hyperliquid.xyz"
        self.exchange_url = f"{self.base_url}/exchange"
        self.info_url = f"{self.base_url}/info"

        # Для тестовой среды используй:
        # self.base_url = "https://api.hyperliquid-testnet.xyz"
        # self.exchange_url = f"{self.base_url}/exchange"
        # self.info_url = f"{self.base_url}/info"

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """
        Подписывает полезную нагрузку с использованием приватного ключа.
        Это упрощённый пример. Фактический процесс может отличаться.
        Пожалуйста, сверьтесь с официальной документацией Hyperliquid.
        """
        # В Hyperliquid v1 API подписывается JSON-строка полезной нагрузки
        payload_str = json.dumps(payload, separators=(',', ':')) # Важно: без пробелов
        # Используем encode_defunct для EIP-191 стиля подписи
        message = encode_defunct(text=payload_str)
        signed_message = self.account.sign_message(message)
        return signed_message.signature.hex()

    def _make_request(self, payload: Dict[str, Any], url: str) -> Optional[Dict[str, Any]]:
        """
        Делает запрос к API с подписью.
        """
        # Подписываем полезную нагрузку
        signature = self._sign_payload(payload)

        headers = {
            "Content-Type": "application/json"
        }

        # Добавляем подпись в полезную нагрузку согласно API
        payload_with_sig = {
            "signature": signature,
            "nonce": int(time.time() * 1000),
            "user": self.user_address
        }
        # Объединяем с оригинальным payload (для запросов типа "order")
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

    def place_order(self, coin: str, is_buy: bool, sz: float, limit_px: float, order_type: str = "limit", reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        Размещает ордер (лимитный или рыночный).

        :param coin: Например, "BTC", "ETH"
        :param is_buy: True для покупки, False для продажи
        :param sz: Количество (size)
        :param limit_px: Цена для лимитного ордера
        :param order_type: "limit" или "market"
        :param reduce_only: True, если ордер должен уменьшать позицию
        :return: Ответ API или None в случае ошибки
        """
        # Проверим, что coin допустим
        allowed_coins = {"BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"}
        if coin not in allowed_coins:
            print(f"Error: Coin {coin} not allowed.")
            return None

        # Определим тип ордера
        order_type_obj = {"limit": {"tif": "Gtc"}} # Gtc = Good Till Cancelled
        if order_type == "market":
            order_type_obj = {"market": {}}

        payload = {
            "type": "order",
            "req": {
                "asset": coin,
                "isBuy": is_buy,
                "sz": sz,
                "limitPx": limit_px,
                "orderType": order_type_obj,
                "reduceOnly": reduce_only,
                # "cloid": "my_id_123" # Необязательный клиентский ID
            }
        }

        print(f"[Hyperliquid] Placing {'BUY' if is_buy else 'SELL'} order for {sz} {coin} @ {limit_px} (Type: {order_type})")
        response = self._make_request(payload["req"], self.exchange_url)
        if response:
            print(f"[Hyperliquid] Order response: {response}")
        else:
            print(f"[Hyperliquid] Failed to place order.")
        return response

    def cancel_order(self, order_id: str, coin: str) -> Optional[Dict[str, Any]]:
        """
        Отменяет ордер по ID.

        :param order_id: ID ордера
        :param coin: Актив, к которому относится ордер
        :return: Ответ API или None
        """
        payload = {
            "type": "cancel",
            "req": {
                "asset": coin,
                "orderIds": [order_id]
            }
        }
        print(f"[Hyperliquid] Cancelling order {order_id} for {coin}")
        response = self._make_request(payload["req"], self.exchange_url)
        if response:
            print(f"[Hyperliquid] Cancel response: {response}")
        else:
            print(f"[Hyperliquid] Failed to cancel order.")
        return response

    def get_user_state(self) -> Optional[Dict[str, Any]]:
        """
        Получает состояние пользователя (баланс, позиции).
        """
        payload = {
            "type": "userState",
            "req": {
                "user": self.user_address
            }
        }
        response = self._make_request(payload["req"], self.info_url)
        if response:
            print(f"[Hyperliquid] User state fetched.")
        else:
            print(f"[Hyperliquid] Failed to fetch user state.")
        return response

    def get_all_mids(self) -> Optional[Dict[str, str]]:
        """
        Получает текущие mid цены для всех активов.
        """
        payload = {
            "type": "allMids"
        }
        # Для allMids подпись не нужна
        try:
            response = requests.post(self.info_url, json=payload)
            if response.status_code == 200:
                data = response.json()
                print(f"[Hyperliquid] Mid prices fetched.")
                return data
            else:
                print(f"[Hyperliquid] Failed to fetch mids: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"[Hyperliquid] Error fetching mids: {e}")
            return None

    # --- Утилиты для LLM Agent ---

    def execute_llm_decision(self, symbol: str, action: str, quantity: float, leverage: int = 10, stop_loss: Optional[float] = None, profit_target: Optional[float] = None):
        """
        Выполняет решение, принятое LLM.
        Пока что только основной ордер. TP/SL нужно реализовать отдельно через 'order' с reduceOnly=true.
        """
        # Получим текущую цену для лимитного ордера
        mids = self.get_all_mids()
        if not mids or symbol not in mids:
            print(f"Cannot execute decision: Cannot get current price for {symbol}")
            return

        current_price = float(mids[symbol])
        is_buy = (action.upper() == "BUY")

        # Рассчитаем цену ордера (например, на 0.1% выше/ниже для лимита)
        limit_px = current_price * 1.001 if is_buy else current_price * 0.999

        # 1. Основной ордер (вход)
        order_response = self.place_order(
            coin=symbol,
            is_buy=is_buy,
            sz=quantity,
            limit_px=limit_px,
            order_type="limit"
        )

        if not order_response or not order_response.get('status') == 'ok':
            print(f"Failed to place main order for {symbol}. Aborting TP/SL.")
            return

        # 2. Ордер на Take Profit (reduceOnly)
        if profit_target:
            self.place_order(
                coin=symbol,
                is_buy=not is_buy,  # Продажа если BUY, покупка если SELL
                sz=quantity,
                limit_px=profit_target,
                order_type="limit",
                reduce_only=True
            )

        # 3. Ордер на Stop Loss (reduceOnly)
        if stop_loss:
            self.place_order(
                coin=symbol,
                is_buy=not is_buy,
                sz=quantity,
                limit_px=stop_loss,
                order_type="limit",
                reduce_only=True
            )

        print(f"[Hyperliquid] Executed {action} for {quantity} {symbol} @ ~{current_price}. SL: {stop_loss}, TP: {profit_target}")

