# src/agents/llm_agent_broker_agnostic.py

import time
import json
import re
from datetime import datetime
from typing import Dict, Optional, List, Any
from src.core.llm_client import LLMClient
from src.data.account_state_broker_agnostic import AccountState
from src.data.market_fetcher_broker_agnostic import MarketFetcher
import os

class LLMAgent:
    def __init__(self, name: str, config: dict, exchange_client, llm_client):
        self.name = name
        self.config = config
        # Принимаем клиента биржи
        self.exchange = exchange_client
        # Создаём зависимости
        self.market_fetcher = MarketFetcher(self.exchange)
        self.account_state = AccountState(self.exchange, initial_capital=config.get("capital_usd", 100.0))
        self.llm_client = llm_client # Принимаем LLMClient

        self.start_time = time.time()
        self.invocation_count = 0

        with open("src/prompts/system_prompt.txt", "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    # ... (остальные методы _format_market_data_block, build_prompt, parse_llm_output остаются такими же) ...

    def execute_decision(self, decision: Dict[str, Any]):
        """
        Исполняет решение через self.exchange.
        """
        symbol = decision["symbol"]
        action = decision["action"]
        qty = decision["quantity"]
        leverage = decision.get("leverage", 10)
        sl = decision.get("stop_loss")
        tp = decision.get("profit_target")

        # Получим текущую цену через exchange
        all_mids = self.exchange.get_all_mids()
        if not all_mids or symbol not in all_mids:
            print(f"[{self.name}] Cannot execute decision: Cannot get current price for {symbol}")
            return

        current_price = all_mids[symbol]
        is_buy = (action.upper() == "BUY")
        # Рассчитаем цену ордера (например, на 0.1% выше/ниже для лимита)
        limit_px = current_price * 1.001 if is_buy else current_price * 0.999

        # 1. Основной ордер
        order_response = self.exchange.place_order(
            symbol=symbol,
            side=action,
            quantity=qty,
            limit_px=limit_px,
            order_type="limit"
        )

        if not order_response or not order_response.get('code') == 0: # Пример структуры ответа BingX, HL другой
            print(f"[{self.name}] Failed to place main order for {symbol}. Aborting TP/SL.")
            return

        # 2. TP и 3. SL - нужно смотреть, как BingX/Hyperliquid реализует reduce-only ордера.
        # BingX может использовать OCO (One-Cancels-Other) ордера.
        # Hyperliquid - отдельные ордера с reduceOnly=true.
        # Это требует доработки execute_decision под особенности каждой биржи.
        # Пока заглушка.
        if tp:
            print(f"[{self.name}] Would place Take Profit order for {symbol} at {tp} via exchange client.")
            # self.exchange.place_order(...)
        if sl:
            print(f"[{self.name}] Would place Stop Loss order for {symbol} at {sl} via exchange client.")
            # self.exchange.place_order(...)

        print(f"[{self.name}] Executed {action} for {qty} {symbol} @ ~{current_price}. SL: {sl}, TP: {tp}")


    def run_cycle(self):
        print(f"\n[{self.name}] Running cycle #{self.invocation_count}...")
        try:
            market_data = self.market_fetcher.get_all_assets()
            account_data = self.account_state.get()
            prompt = self.build_prompt(market_data, account_data)
            print(f"[{self.name}] Prompt built ({len(prompt)} chars). Calling LLM...")

            llm_response = self.llm_client.call(prompt)
            if not llm_response:
                print(f"[{self.name}] LLM returned no response.")
                return

            print(f"[{self.name}] LLM responded. Parsing output...")
            decision = self.parse_llm_output(llm_response)

            if decision:
                print(f"[{self.name}] Decision parsed: {decision['action']} {decision['quantity']} {decision['symbol']}")
                self.execute_decision(decision)
            else:
                print(f"[{self.name}] Could not parse LLM decision. Skipping execution.")

        except Exception as e:
            print(f"[{self.name}] Error in run_cycle: {e}")
        finally:
            self.invocation_count += 1

    def run(self):
        while True:
            self.run_cycle()
            interval = self.config.get("interval_sec", 600)
            print(f"[{self.name}] Waiting {interval} seconds for next cycle...")
            time.sleep(interval)
