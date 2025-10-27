# src/data/market_fetcher_broker_agnostic.py

import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange
from typing import Dict, List
import time
from src.exchanges.base_exchange import BaseExchange

class MarketFetcher:
    def __init__(self, exchange_client: BaseExchange, assets: List[str] = None):
        self.exchange = exchange_client
        self.assets = assets or ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"]

    def _get_candles_from_exchange(self, asset: str, interval: str, limit: int) -> pd.DataFrame:
        """
        Получает свечи через exchange_client.
        """
        raw_klines = self.exchange.get_klines(asset, interval, limit)
        if not raw_klines:
            print(f"No klines returned for {asset} ({interval}) from exchange.")
            return pd.DataFrame()

        df = pd.DataFrame(raw_klines, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        df = df.sort_values('t').reset_index(drop=True)
        for col in ['o', 'h', 'l', 'c', 'v']:
            df[col] = pd.to_numeric(df[col])
        return df

    def _calculate_indicators(self, df: pd.DataFrame, period_rsi: int = 14) -> pd.DataFrame:
        df = df.copy()
        df['ema20'] = EMAIndicator(close=df['c'], window=20).ema_indicator()
        df['rsi'] = RSIIndicator(close=df['c'], window=period_rsi).rsi()
        macd_indicator = MACD(close=df['c'])
        df['macd'] = macd_indicator.macd()
        df['atr'] = AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range()
        return df

    def _trim_to_10(self, series: List) -> List:
        return series[-10:] if len(series) >= 10 else series

    def get_asset_data(self, asset: str) -> Dict:
        """
        Собирает данные для одного актива через exchange_client.
        """
        df_3m = self._get_candles_from_exchange(asset, "3m", 20) # 20 для буфера
        if df_3m.empty:
            print(f"Warning: No 3m data for {asset}, returning empty dict")
            return {}
        df_4h = self._get_candles_from_exchange(asset, "4h", 20) # 20 для буфера
        if df_4h.empty:
            print(f"Warning: No 4h data for {asset}, returning empty dict")
            return {}

        df_3m = self._calculate_indicators(df_3m, period_rsi=7)
        df_3m = self._calculate_indicators(df_3m, period_rsi=14)
        df_4h = self._calculate_indicators(df_4h, period_rsi=14)

        current_price = float(df_3m['c'].iloc[-1])
        current_ema20 = float(df_3m['ema20'].iloc[-1])
        current_macd = float(df_3m['macd'].iloc[-1])
        current_rsi_7 = float(df_3m['rsi'].iloc[-1])
        df_3m_with_rsi14 = self._calculate_indicators(df_3m, period_rsi=14)
        current_rsi_14 = float(df_3m_with_rsi14['rsi'].iloc[-1])

        # Ряды
        mid_prices_3m = self._trim_to_10(df_3m['c'].tolist())
        ema20_3m = self._trim_to_10(df_3m['ema20'].tolist())
        macd_3m = self._trim_to_10(df_3m['macd'].fillna(0.0).tolist())
        rsi7_3m = self._trim_to_10(df_3m['rsi'].fillna(0.0).tolist())
        df_3m_with_rsi14 = self._calculate_indicators(df_3m, period_rsi=14)
        rsi14_3m = self._trim_to_10(df_3m_with_rsi14['rsi'].fillna(0.0).tolist())

        ema20_4h = float(df_4h['ema20'].iloc[-1])
        df_4h_with_ema50 = df_4h.copy()
        df_4h_with_ema50['ema50'] = EMAIndicator(close=df_4h_with_ema50['c'], window=50).ema_indicator()
        ema50_4h = float(df_4h_with_ema50['ema50'].iloc[-1])
        atr3_4h = float(AverageTrueRange(high=df_4h['h'], low=df_4h['l'], close=df_4h['c'], window=3).average_true_range().iloc[-1])
        atr14_4h = float(df_4h['atr'].iloc[-1])
        volume_current_4h = float(df_4h['v'].iloc[-1])
        volume_avg_4h = float(df_4h['v'].mean())

        df_4h_with_macd = self._calculate_indicators(df_4h, period_rsi=14)
        macd_4h_series = self._trim_to_10(df_4h_with_macd['macd'].fillna(0.0).tolist())
        rsi14_4h_series = self._trim_to_10(df_4h_with_macd['rsi'].fillna(0.0).tolist())

        # Данные с биржи
        funding_rate = self.exchange.get_funding_rate(asset) or 0.0
        open_interest_val = self.exchange.get_open_interest(asset) or 0.0

        return {
            "current_price": current_price,
            "current_ema20": current_ema20,
            "current_macd": current_macd,
            "current_rsi_7": current_rsi_7,
            "current_rsi_14": current_rsi_14,
            "open_interest": {"latest": open_interest_val, "average": open_interest_val * 0.99}, # Заглушка
            "funding_rate": funding_rate,
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
        result = {}
        for asset in self.assets:
            try:
                print(f"Fetching data for {asset}...")
                result[asset] = self.get_asset_data(asset)
                time.sleep(0.5)
            except Exception as e:
                print(f"Error fetching {asset}: {e}")
                result[asset] = {}
        return result
