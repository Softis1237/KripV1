# src/exchanges/base_exchange.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class BaseExchange(ABC):
    """
    Абстрактный базовый класс для клиента биржи.
    Определяет общий интерфейс, который должны реализовать все конкретные биржи (Hyperliquid, BingX и т.д.).
    """

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """
        Получает информацию о счёте: баланс, PnL и т.д.
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Получает список открытых позиций.
        """
        pass

    @abstractmethod
    def get_all_mids(self) -> Dict[str, float]:
        """
        Получает текущие mid цены для всех торгуемых активов.
        """
        pass

    @abstractmethod
    def place_order(self, coin: str, is_buy: bool, sz: float, limit_px: float, order_type: str = "limit", reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        Размещает ордер.
        """
        pass

    # --- ДОБАВИМ ЭТОТ АБСТРАКТНЫЙ МЕТОД ---
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Отменяет ордер.
        """
        pass
    # --- КОНЕЦ ДОБАВЛЕНИЯ ---

    @abstractmethod
    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
        """
        Получает свечи (OHLCV).
        """
        pass

    @abstractmethod
    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """
        Получает текущий funding rate для актива.
        """
        pass

    @abstractmethod
    def get_open_interest(self, symbol: str) -> Optional[float]:
        """
        Получает текущий open interest для актива.
        """
        pass
