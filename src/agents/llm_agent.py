# src/agents/llm_agent.py

import time
import json
import re
from datetime import datetime
from typing import Dict, Optional, List, Any
from src.data.market_fetcher import MarketFetcher
from src.data.account_state import AccountState
from src.core.llm_client import LLMClient
from src.core.hyperliquid import HyperliquidClient  # Пока что заглушка
import os

class LLMAgent:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.market_fetcher = MarketFetcher()
        self.account_state = AccountState(wallet_address=config.get("wallet_address", "0x000000000000000000000000000000000000dead"))
        self.llm_client = LLMClient(
            model_name=config["model"],
            api_key_env=config["api_key_env"],
            provider=config.get("provider")
        )
        # Использовать HyperliquidClient только если есть реальный кошелёк и ключи
        wallet_addr = config.get("wallet_address")
        hl_secret = os.getenv("HYPERLIQUID_SECRET")
        if wallet_addr and len(wallet_addr) > 20 and hl_secret:
            self.hyperliquid = HyperliquidClient(wallet_addr, hl_secret)
        else:
            self.hyperliquid = None
            print(f"[{self.name}] Hyperliquid client not initialized (missing wallet or secret). Paper trading mode.")

        self.start_time = time.time()
        self.invocation_count = 0

        # Загрузим шаблон промпта
        with open("src/prompts/system_prompt.txt", "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    def _format_market_data_block(self, market_data: Dict[str, Dict]) -> str:
        """
        Преобразует словарь market_data в строку, как в nof1.ai
        """
        lines = []
        for asset, data in market_data.items():
            if not data or 'current_price' not in data:  # Если заглушка или ошибка
                lines.append(f"ALL {asset} DATA\nNo data available.\n")
                continue

            lines.append(f"ALL {asset} DATA")
            lines.append(f"current_price = {data['current_price']:.3f}, current_ema20 = {data['current_ema20']:.3f}, current_macd = {data['current_macd']:.3f}, current_rsi (7 period) = {data['current_rsi_7']:.3f}")
            lines.append("")
            lines.append(f"In addition, here is the latest {asset} open interest and funding rate for perps:")
            lines.append(f"Open Interest: Latest: {data['open_interest']['latest']:.2f} Average: {data['open_interest']['average']:.2f}")
            lines.append(f"Funding Rate: {data['funding_rate']:.6f}")
            lines.append("")
            lines.append("Intraday series (3‑minute intervals, oldest → latest):")
            lines.append(f"Mid prices: {data['mid_prices_3m']}")
            lines.append(f"EMA indicators (20‑period): {data['ema20_3m']}")
            lines.append(f"MACD indicators: {data['macd_3m']}")
            lines.append(f"RSI indicators (7‑Period): {data['rsi7_3m']}")
            lines.append(f"RSI indicators (14‑Period): {data['rsi14_3m']}")
            lines.append("")
            lines.append("Longer‑term context (4‑hour timeframe):")
            lines.append(f"20‑Period EMA: {data['ema20_4h']:.3f} vs. 50‑Period EMA: {data['ema50_4h']:.3f}")
            lines.append(f"3‑Period ATR: {data['atr3_4h']:.3f} vs. 14‑Period ATR: {data['atr14_4h']:.3f}")
            lines.append(f"Current Volume: {data['volume_current']:.3f} vs. Average Volume: {data['volume_avg']:.3f}")
            lines.append(f"MACD indicators: {data['macd_4h']}")
            lines.append(f"RSI indicators (14‑Period): {data['rsi14_4h']}")
            lines.append("") # Добавим пустую строку между активами
        return "\n".join(lines)

    def build_prompt(self, market_data: Dict[str, Dict], account_data: Dict) -> str:
        """
        Собирает полный промпт из шаблона и данных.
        """
        minutes_since_start = int((time.time() - self.start_time) / 60)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        market_block = self._format_market_data_block(market_data)

        # Формируем positions_json строку
        positions_json_str = json.dumps(account_data["positions"], separators=(',', ':'))

        filled_prompt = self.prompt_template.format(
            minutes_since_start=minutes_since_start,
            timestamp=timestamp,
            invocation_count=self.invocation_count,
            market_data_block=market_block,
            total_return_pct=account_data["total_return_pct"],
            available_cash=account_data["available_cash"],
            account_value=account_data["total_account_value"],
            positions_json=positions_json_str,
            sharpe=account_data["sharpe_ratio"]
        )
        return filled_prompt

    def parse_llm_output(self, raw_output: str) -> Optional[Dict[str, Any]]:
        """
        Парсит вывод LLM в структуру, пригодную для исполнения.
        Пример:
        ▶
        CHAIN_OF_THOUGHT
        { "ETH": { "signal": "HOLD", ... } }
        ▶
        TRADING_DECISIONS
        ETH
        HOLD
        88%
        Justification...
        QUANTITY: 22.66
        """
        # Ищем блок CHAIN_OF_THOUGHT
        cot_match = re.search(r'CHAIN_OF_THOUGHT\s*\n({.*?})\s*\n\s*▶', raw_output, re.DOTALL)
        if not cot_match:
            print(f"[{self.name}] Could not find CHAIN_OF_THOUGHT block in LLM output.")
            return None
        try:
            cot_json_str = cot_match.group(1).strip()
            cot_data = json.loads(cot_json_str)
        except json.JSONDecodeError:
            print(f"[{self.name}] Could not parse CHAIN_OF_THOUGHT JSON.")
            return None

        # Ищем блок TRADING_DECISIONS
        dec_match = re.search(r'TRADING_DECISIONS\s*\n\s*(\w+)\s*\n\s*(\w+)\s*\n\s*(\d+)%\s*\n\s*(.*?)\s*\n\s*QUANTITY:\s*([0-9.-]+)', raw_output, re.DOTALL)
        if not dec_match:
            print(f"[{self.name}] Could not find TRADING_DECISIONS block in LLM output.")
            return None

        symbol = dec_match.group(1)
        action = dec_match.group(2) # BUY/SELL/HOLD
        confidence_pct = int(dec_match.group(3))
        justification = dec_match.group(4).strip()
        quantity = float(dec_match.group(5))

        # Собираем результат
        result = {
            "symbol": symbol,
            "action": action,
            "confidence": confidence_pct / 100.0,
            "justification": justification,
            "quantity": quantity,
            "raw_chain_of_thought": cot_data
        }

        # Достаём данные из CoT, если они есть
        if symbol in cot_data:
            cot_details = cot_data[symbol]
            result.update({
                "leverage": cot_details.get("leverage", 10),
                "stop_loss": cot_details.get("stop_loss"),
                "profit_target": cot_details.get("profit_target"),
                "invalidation_condition": cot_details.get("invalidation_condition"),
                "risk_usd": cot_details.get("risk_usd"),
            })

        return result

    def execute_decision(self, decision: Dict[str, Any]):
        """
        Исполняет решение через Hyperliquid.
        """
        symbol = decision["symbol"]
        action = decision["action"]
        qty = decision["quantity"]
        leverage = decision.get("leverage", 10)
        sl = decision.get("stop_loss")
        tp = decision.get("profit_target")

        if not self.hyperliquid:
            print(f"[{self.name}] Paper trading mode. Would execute: {action} {qty} {symbol} at {leverage}x leverage.")
            if sl: print(f"  Stop Loss: {sl}")
            if tp: print(f"  Take Profit: {tp}")
            return

        # --- ЗАМЕНИТЬ ЭТУ ЗАГЛУШКУ НА ЭТОТ ВЫЗОВ ---
        self.hyperliquid.execute_llm_decision(
            symbol=symbol,
            action=action,
            quantity=qty,
            leverage=leverage,
            stop_loss=sl,
            profit_target=tp
        )
        # ---

    def run_cycle(self):
        """
        Один цикл: получить данные -> построить промпт -> вызвать LLM -> распарсить -> исполнить.
        """
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
        """
        Запуск в цикле с интервалом.
        """
        while True:
            self.run_cycle()
            interval = self.config.get("interval_sec", 600) # 10 минут по умолчанию
            print(f"[{self.name}] Waiting {interval} seconds for next cycle...")
            time.sleep(interval)
