
import aiohttp
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from typing import Dict, List
import time
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketFetcher:
    def __init__(self, assets: List[str] | None = None):
        """Initialize MarketFetcher with a list of assets to track"""
        self.assets = assets if assets is not None else ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"]
        self.api_base_url = "https://api.binance.com/api/v3"
        self.session = None
        self.logger = logger
        
    async def __aenter__(self):
        """Create aiohttp session when entering context"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_value, traceback):
        """Close aiohttp session when exiting context"""
        if self.session:
            await self.session.close()
            
    async def _init_session(self):
        """Initialize aiohttp session if not exists"""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def _get_current_price(self, symbol: str) -> float:
        """Get current price for an asset"""
        try:
            await self._init_session()
            self.logger.info(f"Fetching data for {symbol}...")
            url = f"{self.api_base_url}/info/markets"
            response = await self.session.get(url)
            data = await response.json()
            
            for ticker in data:
                if ticker['name'] == symbol:
                    return float(ticker['markPrice'])
                    
            self.logger.error(f"Symbol {symbol} not found in response")
            raise ValueError(f"Symbol {symbol} not found in response")
            
        except Exception as e:
            self.logger.error(f"Error fetching data for {symbol}: {e}")
            raise

    async def get_all_assets(self) -> Dict:
        """Gets current data for all allowed assets."""
        results = {}
        for symbol in self.assets:
            try:
                current_price = await self._get_current_price(symbol)
                results[symbol] = {
                    'current_price': current_price
                }
            except Exception as e:
                self.logger.error(f"Error fetching {symbol}: {str(e)}")
                continue
        return results
