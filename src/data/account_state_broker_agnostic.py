# src/data/account_state_broker_agnostic.py

import time
from typing import Dict, List
import random
from src.exchanges.base_exchange import BaseExchange

class AccountState:
    def __init__(self, exchange_client: BaseExchange, initial_capital: float = 100.0):
        self.exchange = exchange_client
        self.initial_capital = initial_capital

    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        if len(returns) < 2:
            return 0.0
        returns_series = [r for r in returns if r is not None]
        if len(returns_series) < 2:
            return 0.0
        mean_return = sum(returns_series) / len(returns_series)
        std_return = (sum((r - mean_return) ** 2 for r in returns_series) / (len(returns_series) - 1)) ** 0.5
        if std_return == 0:
            return 0.0
        return (mean_return / std_return) * (365 ** 0.5)

    def get(self) -> Dict:
        """
        Возвращает состояние счёта, используя exchange_client.
        """
        try:
            account_info = self.exchange.get_account_info()
            positions = self.exchange.get_positions()
            total_account_value = account_info.get("accountValue", self.initial_capital)
            # available_cash: может быть в account_info или нужно рассчитать
            # Пока заглушка
            available_cash = total_account_value * 0.9

            # Total Return
            total_return_pct = ((total_account_value / self.initial_capital) - 1) * 100

            # Sharpe: заглушка
            sharpe = self._calculate_sharpe_ratio([random.uniform(-1, 3) for _ in range(10)])

            return {
                "total_return_pct": round(total_return_pct, 2),
                "available_cash": round(available_cash, 2),
                "total_account_value": round(total_account_value, 2),
                "sharpe_ratio": round(sharpe, 3),
                "positions": positions
            }

        except Exception as e:
            print(f"Error fetching account state: {e}")
            # Возврат заглушки при ошибке
            return {
                "total_return_pct": 0.0,
                "available_cash": self.initial_capital,
                "total_account_value": self.initial_capital,
                "sharpe_ratio": 0.0,
                "positions": []
            }
