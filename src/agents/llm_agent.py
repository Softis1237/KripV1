"""
LLM Trading Agent implementation.
Handles market data collection, LLM interaction, and trade execution.
"""

import time
import json
from typing import Dict, Optional
from pathlib import Path

from ..core.hyperliquid import HyperliquidClient
from ..core.llm_client import LLMClient
from ..data.market_fetcher import MarketFetcher
from ..data.account_state import AccountState

class LLMAgent:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.hyperliquid = HyperliquidClient(config)
        self.llm = LLMClient(config["model"], config["api_key"])
        self.market_fetcher = MarketFetcher()
        self.account_state = AccountState()
        self.invocation_count = 0
        self.start_time = time.time()
        
    def build_prompt(self, market_data: dict, account_data: dict) -> str:
        """Builds the system prompt with current market and account context."""
        pass
        
    def parse_decision(self, llm_response: str) -> Optional[Dict]:
        """Parses LLM response into actionable trading decisions."""
        pass
        
    def execute_decision(self, decision: Dict):
        """Executes trading decisions through Hyperliquid."""
        pass

    def log_cycle(self, market_data: dict, account_data: dict, 
                 llm_response: str, decision: Optional[Dict]):
        """Logs the full cycle context to JSON file."""
        pass
        
    def run_cycle(self):
        """Executes one full trading cycle."""
        # 1. Collect market data
        market_data = self.market_fetcher.get_all_assets()
        account_data = self.account_state.get()
        
        # 2. Build prompt
        prompt = self.build_prompt(market_data, account_data)
        
        # 3. Get LLM decision
        llm_response = self.llm.call(prompt)
        
        # 4. Parse decision
        decision = self.parse_decision(llm_response)
        
        # 5. Execute if needed
        if decision and decision.get("signal") != "HOLD":
            self.execute_decision(decision)
            
        # 6. Log everything
        self.log_cycle(market_data, account_data, llm_response, decision)
        
    def run(self):
        """Main agent loop."""
        while True:
            try:
                self.run_cycle()
                self.invocation_count += 1
                time.sleep(self.config["interval_sec"])
            except Exception as e:
                # Log error and continue
                self.log_cycle({}, {}, str(e), None)