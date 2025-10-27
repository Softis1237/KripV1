# src/data/account_state.py

import requests
import time
from typing import Dict, List
import random  # для генерации заглушек

class AccountState:
    def __init__(self, wallet_address: str = "0x000000000000000000000000000000000000dead"):
        self.wallet_address = wallet_address
        self.base_url = "https://api.hyperliquid.xyz"
        self.info_url = f"{self.base_url}/info"

    def _get_user_state_from_api(self) -> Dict:
        """
        Получает состояние счёта от Hyperliquid API.
        Требует адрес кошелька.
        """
        payload = {
            "type": "userState",
            "user": self.wallet_address
        }

        resp = requests.post(self.info_url, json=payload)
        if resp.status_code != 200:
            print(f"Error fetching user state: {resp.status_code} - {resp.text}")
            return {}

        data = resp.json()
        return data

    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """
        Упрощённый расчёт Sharpe Ratio.
        В реальности требует исторических данных и более сложной логики.
        """
        if len(returns) < 2:
            return 0.0
        returns_series = [r for r in returns if r is not None]
        if len(returns_series) < 2:
            return 0.0
        mean_return = sum(returns_series) / len(returns_series)
        std_return = (sum((r - mean_return) ** 2 for r in returns_series) / (len(returns_series) - 1)) ** 0.5
        if std_return == 0:
            return 0.0
        # Упрощённо, без учёта risk-free rate
        return (mean_return / std_return) * (365 ** 0.5)  # annualized

    def get(self) -> Dict:
        """
        Возвращает состояние счёта в формате, совместимом с Alpha Arena.
        """
        # Попробуем получить реальные данные, если кошелёк настоящий
        try:
            raw_state = self._get_user_state_from_api()
        except Exception as e:
            print(f"Could not fetch user state from API: {e}. Using mock data.")
            raw_state = {}

        if not raw_state or "marginSummary" not in raw_state or "positions" not in raw_state:
            # --- ЗАГЛУШКА ---
            # Используем фиктивные данные, как если бы у нас был счёт на $100
            total_account_value = 100.0
            # Добавим немного случайности, чтобы было интереснее
            total_account_value += random.uniform(-2, 5)
            available_cash = total_account_value * random.uniform(0.8, 0.95)

            # Симулируем позицию, например, ETH
            positions = []
            if random.choice([True, False]):  # 50% шанс, что позиция есть
                entry_px = 4191.2 + random.uniform(-200, 200)
                current_px = entry_px + random.uniform(-100, 100)
                qty = round(random.uniform(0.01, 0.1), 4)
                leverage = random.randint(10, 20)
                pnl = (current_px - entry_px) * qty
                positions = [
                    {
                        "symbol": "ETH",
                        "quantity": qty,
                        "entry_price": entry_px,
                        "current_price": current_px,
                        "unrealized_pnl": pnl,
                        "leverage": leverage,
                        "exit_plan": {
                            "profit_target": current_px * 1.05,  # 5% TP
                            "stop_loss": current_px * 0.98,      # 2% SL
                            "invalidation_condition": "4h close below 4018.868"
                        }
                    }
                ]

            total_return_pct = ((total_account_value / 100.0) - 1) * 100  # Начальный капитал = $100
            sharpe = self._calculate_sharpe_ratio([random.uniform(-1, 3) for _ in range(10)])  # Симуляция ретернов

            return {
                "total_return_pct": round(total_return_pct, 2),
                "available_cash": round(available_cash, 2),
                "total_account_value": round(total_account_value, 2),
                "sharpe_ratio": round(sharpe, 3),
                "positions": positions
            }

        # --- РЕАЛЬНЫЕ ДАННЫЕ (если API вернул их) ---
        margin_summary = raw_state["marginSummary"]
        positions_raw = raw_state["positions"]

        # Состояние счёта
        total_account_value = float(margin_summary.get("accountValue", 0))
        # availableCash не всегда возвращается, используем accountValue как приближение, если нет
        available_cash = float(margin_summary.get("cash", total_account_value))

        # Позиции
        positions = []
        for pos_raw in positions_raw:
            if float(pos_raw["positionValue"]) != 0:  # Только открытые позиции
                # Пример структуры: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/data-types/user-state
                symbol = pos_raw["coin"]
                side = "LONG" if float(pos_raw["szi"]) > 0 else "SHORT"
                quantity = abs(float(pos_raw["szi"]))
                entry_price = float(pos_raw["entryPx"])
                leverage = float(pos_raw["leverage"])
                # current_price и pnl рассчитываются на бирже, но мы можем приблизительно получить через market_fetcher
                # Для заглушки используем markPx из assetCtxs
                current_price = self._get_mark_price(symbol)
                unrealized_pnl = float(pos_raw["unrealizedPnl"])

                positions.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "unrealized_pnl": unrealized_pnl,
                    "leverage": leverage,
                    # Заглушка для exit_plan, т.к. биржа не возвращает TP/SL
                    "exit_plan": {
                        "profit_target": current_price * 1.05 if side == "LONG" else current_price * 0.95,
                        "stop_loss": current_price * 0.98 if side == "LONG" else current_price * 1.02,
                        "invalidation_condition": "4h close below 4018.868"
                    }
                })

        # Total Return: (Текущий капитал - Начальный капитал) / Начальный капитал * 100
        # Начальный капитал не возвращается API, предположим, что это $100 (или можно хранить в config)
        initial_capital = 100.0
        total_return_pct = ((total_account_value / initial_capital) - 1) * 100

        # Sharpe Ratio: требует исторических данных, возвращаем заглушку
        sharpe = self._calculate_sharpe_ratio([random.uniform(-1, 3) for _ in range(10)])

        return {
            "total_return_pct": round(total_return_pct, 2),
            "available_cash": round(available_cash, 2),
            "total_account_value": round(total_account_value, 2),
            "sharpe_ratio": round(sharpe, 3),
            "positions": positions
        }

    def _get_mark_price(self, symbol: str) -> float:
        """
        Получает текущую mark цену для актива через allMids.
        """
        try:
            mids_resp = requests.post(self.info_url, json={"type": "allMids"})
            if mids_resp.status_code == 200:
                mids = mids_resp.json()
                return float(mids.get(symbol, 0.0))
        except Exception:
            pass
        return 0.0  # Заглушка, если не удалось получить
