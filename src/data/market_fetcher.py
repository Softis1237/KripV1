# src/data/market_fetcher.py

import requests
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange
from typing import Dict, List
import time

class MarketFetcher:
    def __init__(self, assets: List[str] = None):
        self.assets = assets or ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"]
        self.base_url = "https://api.hyperliquid.xyz"
        self.info_url = f"{self.base_url}/info"

    def _get_candles_hl(self, asset: str, interval: str, n_candles: int) -> pd.DataFrame:
        """
        Получает свечи через Hyperliquid info API (candleSnapshot).
        interval: '1m', '3m', '1h', '4h'
        """
        # Определим startTime и endTime примерно
        now_ms = int(time.time() * 1000)
        # Примерно: n_candles * interval в миллисекундах
        interval_to_ms = {
            "1m": 60 * 1000,
            "3m": 3 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000
        }
        if interval not in interval_to_ms:
            raise ValueError(f"Unsupported interval: {interval}")

        total_ms = n_candles * interval_to_ms[interval]
        start_time = now_ms - total_ms

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": asset,
                "interval": interval,
                "startTime": start_time,
                "endTime": now_ms
            }
        }

        resp = requests.post(self.info_url, json=payload)
        if resp.status_code != 200:
            print(f"Error fetching candles for {asset} ({interval}): {resp.status_code} - {resp.text}")
            return pd.DataFrame(columns=['t', 'o', 'h', 'l', 'c', 'v'])

        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            print(f"Warning: No candle data returned for {asset} ({interval})")
            return pd.DataFrame(columns=['t', 'o', 'h', 'l', 'c', 'v'])

        df = pd.DataFrame(data, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        df = df.sort_values('t').reset_index(drop=True)
        for col in ['o', 'h', 'l', 'c', 'v']:
            df[col] = pd.to_numeric(df[col])
        return df

    def _calculate_indicators(self, df: pd.DataFrame, period_rsi: int = 14) -> pd.DataFrame:
        """Добавляет EMA20, MACD, RSI, ATR"""
        df = df.copy()
        df['ema20'] = EMAIndicator(close=df['c'], window=20).ema_indicator()
        df['rsi'] = RSIIndicator(close=df['c'], window=period_rsi).rsi()

        macd_indicator = MACD(close=df['c'])
        df['macd'] = macd_indicator.macd()
        df['atr'] = AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range()

        return df

    def _get_funding_and_oi(self, asset: str) -> Dict:
        """Получает funding rate и open interest через Hyperliquid API (исправлено)"""
        # --- ИСПРАВЛЕНО: metaAndAssetCtxs возвращает [meta, [ctx0, ctx1, ...]] ---
        resp = requests.post(self.info_url, json={"type": "metaAndAssetCtxs"})
        if resp.status_code != 200:
            print(f"Error fetching metaAndAssetCtxs for {asset}: {resp.text}")
            # Возвращаем заглушки, чтобы не ломать цикл
            return {
                "open_interest": {"latest": 0.0, "average": 0.0},
                "funding_rate": 0.0
            }

        data = resp.json()
        universe = data[0]["universe"]
        asset_ctxs = data[1]

        # Найдём индекс актива
        coin_idx = next((i for i, x in enumerate(universe) if x["name"] == asset), None)
        if coin_idx is None:
            raise ValueError(f"Asset {asset} not found in Hyperliquid universe")

        # Получим контекст нужного актива
        ctx = asset_ctxs[coin_idx]

        funding_rate = float(ctx["funding"])
        open_interest = float(ctx["openInterest"])

        return {
            "open_interest": {"latest": open_interest, "average": open_interest * 0.99},  # Заглушка для среднего
            "funding_rate": funding_rate
        }


    def _trim_to_10(self, series: List) -> List:
        """Оставляет последние 10 значений, но в порядке oldest → newest"""
        return series[-10:] if len(series) >= 10 else series

    def get_asset_data(self, asset: str) -> Dict:
        """Собирает полный блок данных по одному активу, как у nof1.ai"""
        # 1. Получаем 30 минут (для 3m) и 40 часов (для 4h) данных
        df_3m = self._get_candles_hl(asset, "3m", 20)  # 20 для буфера
        if df_3m.empty:
            print(f"Warning: No 3m data for {asset}, returning empty dict")
            # --- ИСПРАВЛЕНО: возвращаем заглушку с ключами ---
            return {
                "current_price": 0.0,
                "current_ema20": 0.0,
                "current_macd": 0.0,
                "current_rsi_7": 0.0,
                "current_rsi_14": 0.0,
                "open_interest": {"latest": 0.0, "average": 0.0},
                "funding_rate": 0.0,
                "mid_prices_3m": [],
                "ema20_3m": [],
                "macd_3m": [],
                "rsi7_3m": [],
                "rsi14_3m": [],
                "ema20_4h": 0.0,
                "ema50_4h": 0.0,
                "atr3_4h": 0.0,
                "atr14_4h": 0.0,
                "volume_current": 0.0,
                "volume_avg": 0.0,
                "macd_4h": [],
                "rsi14_4h": []
            }
        df_4h = self._get_candles_hl(asset, "4h", 20)  # 20 для буфера
        if df_4h.empty:
            print(f"Warning: No 4h data for {asset}, returning empty dict")
            # --- ИСПРАВЛЕНО: возвращаем заглушку с ключами ---
            return {
                "current_price": 0.0,
                "current_ema20": 0.0,
                "current_macd": 0.0,
                "current_rsi_7": 0.0,
                "current_rsi_14": 0.0,
                "open_interest": {"latest": 0.0, "average": 0.0},
                "funding_rate": 0.0,
                "mid_prices_3m": [],
                "ema20_3m": [],
                "macd_3m": [],
                "rsi7_3m": [],
                "rsi14_3m": [],
                "ema20_4h": 0.0,
                "ema50_4h": 0.0,
                "atr3_4h": 0.0,
                "atr14_4h": 0.0,
                "volume_current": 0.0,
                "volume_avg": 0.0,
                "macd_4h": [],
                "rsi14_4h": []
            }

        # 2. Считаем индикаторы
        df_3m = self._calculate_indicators(df_3m, period_rsi=7)
        df_3m = self._calculate_indicators(df_3m, period_rsi=14)
        df_4h = self._calculate_indicators(df_4h, period_rsi=14)

        # 3. Текущие значения (последние)
        current_price = float(df_3m['c'].iloc[-1])
        current_ema20 = float(df_3m['ema20'].iloc[-1])
        current_macd = float(df_3m['macd'].iloc[-1])
        current_rsi_7 = float(df_3m['rsi'].iloc[-1])  # Это RSI7
        df_3m_with_rsi14 = self._calculate_indicators(df_3m, period_rsi=14)
        current_rsi_14 = float(df_3m_with_rsi14['rsi'].iloc[-1])

        # 4. Ряды (последние 10, oldest → newest)
        mid_prices_3m = self._trim_to_10(df_3m['c'].tolist())
        ema20_3m = self._trim_to_10(df_3m['ema20'].tolist())
        macd_3m = self._trim_to_10(df_3m['macd'].fillna(0.0).tolist())
        rsi7_3m = self._trim_to_10(df_3m['rsi'].fillna(0.0).tolist())
        df_3m_with_rsi14 = self._calculate_indicators(df_3m, period_rsi=14)
        rsi14_3m = self._trim_to_10(df_3m_with_rsi14['rsi'].fillna(0.0).tolist())

        # 4h данные
        ema20_4h = float(df_4h['ema20'].iloc[-1])
        df_4h_with_ema50 = df_4h.copy()
        df_4h_with_ema50['ema50'] = EMAIndicator(close=df_4h_with_ema50['c'], window=50).ema_indicator()
        ema50_4h = float(df_4h_with_ema50['ema50'].iloc[-1])
        atr3_4h = float(AverageTrueRange(high=df_4h['h'], low=df_4h['l'], close=df_4h['c'], window=3).average_true_range().iloc[-1])
        atr14_4h = float(df_4h['atr'].iloc[-1])  # уже рассчитан как ATR14
        volume_current_4h = float(df_4h['v'].iloc[-1])
        volume_avg_4h = float(df_4h['v'].mean())

        df_4h_with_macd = self._calculate_indicators(df_4h, period_rsi=14)
        macd_4h_series = self._trim_to_10(df_4h_with_macd['macd'].fillna(0.0).tolist())
        rsi14_4h_series = self._trim_to_10(df_4h_with_macd['rsi'].fillna(0.0).tolist())

        # 5. Метаданные
        meta = self._get_funding_and_oi(asset)

        return {
            "current_price": current_price,
            "current_ema20": current_ema20,
            "current_macd": current_macd,
            "current_rsi_7": current_rsi_7,
            "current_rsi_14": current_rsi_14,
            "open_interest": meta["open_interest"],
            "funding_rate": meta["funding_rate"],
            "mid_prices_3m": [float(x) for x in mid_prices_3m],
            "ema20_3m": [float(x) for x in ema20_3m],
            "macd_3m": [float(x) for x in macd_3m],
            "rsi7_3m": [float(x) for x in rsi7_3m],
            "rsi14_3m": [float(x) for x in rsi14_3m],
            "ema20_4h": ema20_4h,
            "ema50_4h": ema50_4h,
            "atr3_4h": atr3_4h,
            "atr14_4h": atr14_4h,
            "volume_current": volume_current_4h,
            "volume_avg": volume_avg_4h,
            "macd_4h": [float(x) for x in macd_4h_series],
            "rsi14_4h": [float(x) for x in rsi14_4h_series]
        }

    def get_all_assets(self) -> Dict[str, Dict]:
        """Возвращает данные по всем активам"""
        result = {}
        for asset in self.assets:
            try:
                print(f"Fetching data for {asset}...")
                result[asset] = self.get_asset_data(asset)
                time.sleep(0.5)  # избегаем рейт-лимитов
            except Exception as e:
                print(f"Error fetching {asset}: {e}")
                # --- ИСПРАВЛЕНО: возвращаем заглушку с ключами ---
                result[asset] = {
                    "current_price": 0.0,
                    "current_ema20": 0.0,
                    "current_macd": 0.0,
                    "current_rsi_7": 0.0,
                    "current_rsi_14": 0.0,
                    "open_interest": {"latest": 0.0, "average": 0.0},
                    "funding_rate": 0.0,
                    "mid_prices_3m": [],
                    "ema20_3m": [],
                    "macd_3m": [],
                    "rsi7_3m": [],
                    "rsi14_3m": [],
                    "ema20_4h": 0.0,
                    "ema50_4h": 0.0,
                    "atr3_4h": 0.0,
                    "atr14_4h": 0.0,
                    "volume_current": 0.0,
                    "volume_avg": 0.0,
                    "macd_4h": [],
                    "rsi14_4h": []
                }
        return result
