"""
Market data fetcher for collecting price and indicator data from Hyperliquid.
"""

import asyncio
from typing import Dict, List
import pandas as pd
import ta
from datetime import datetime, timedelta

class MarketFetcher:
    def __init__(self):
        self.allowed_assets = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"]
        
    async def fetch_candles(self, symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
        """Fetches OHLCV candles from Hyperliquid."""
        pass
        
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculates technical indicators from OHLCV data."""
        pass
        
    def get_current_data(self, symbol: str) -> Dict:
        """Gets current price, funding rate, and open interest."""
        pass
        
    def get_time_series(self, symbol: str) -> Dict:
        """Gets 3m and 4h time series (last 10 points)."""
        pass
        
    def get_all_assets(self) -> Dict:
        """Collects data for all allowed assets."""
        results = {}
        for symbol in self.allowed_assets:
            try:
                current = self.get_current_data(symbol)
                series = self.get_time_series(symbol)
                results[symbol] = {**current, **series}
            except Exception as e:
                # Log error and continue with other assets
                print(f"Error fetching {symbol}: {str(e)}")
                continue
        return results