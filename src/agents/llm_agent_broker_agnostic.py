# src/agents/llm_agent_broker_agnostic.py

import time
import json
import re
from datetime import datetime
from typing import Dict, Optional, List, Any
from src.core.llm_client import LLMClient
from src.data.account_state_broker_agnostic import AccountState
from src.data.market_fetcher_broker_agnostic import MarketFetcher
from src.exchanges.order_manager import OrderManager
# --- ИМПОРТ PYDANTIC И НОВОЙ СХЕМЫ ---
from src.agents.llm_response_schema import ChainOfThought
from pydantic import ValidationError
# --- КОНЕЦ ИМПОРТА ---
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

        # --- СОЗДАДИМ OrderManager ---
        self.order_manager = OrderManager(self.exchange)
        # --- КОНЕЦ СОЗДАНИЯ ---

        self.start_time = time.time()
        self.invocation_count = 0

        with open("src/prompts/system_prompt.txt", "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    def _format_market_data_block(self, market_data: Dict[str, Any]) -> str:
        """
        Форматирует данные рынка в читаемый блок для промпта.
        """
        formatted = "=== MARKET DATA ===\n"
        for symbol, data in market_data.items():
            formatted += f"{symbol}:\n"
            formatted += f"  Price: {data.get('price', 'N/A')}\n"
            formatted += f"  Change 24h: {data.get('change_24h', 'N/A')}%\n"
            formatted += f"  Volume: {data.get('volume', 'N/A')}\n"
            formatted += "\n"
        return formatted

    def _format_account_data_block(self, account_data: Dict[str, Any]) -> str:
        """
        Форматирует данные аккаунта в читаемый блок для промпта.
        """
        formatted = "=== ACCOUNT STATE ===\n"
        formatted += f"Balance USD: {account_data.get('balance_usd', 'N/A')}\n"
        formatted += f"Equity: {account_data.get('equity', 'N/A')}\n"
        formatted += "Positions:\n"
        for pos in account_data.get('positions', []):
            formatted += f"  {pos.get('symbol', 'N/A')}: {pos.get('size', 0)} @ {pos.get('entry_price', 'N/A')}\n"
        formatted += "\n"
        return formatted

    def build_prompt(self, market_data: Dict[str, Any], account_data: Dict[str, Any]) -> str:
        """
        Строит полный промпт для LLM.
        """
        market_block = self._format_market_data_block(market_data)
        account_block = self._format_account_data_block(account_data)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        prompt = self.prompt_template.format(
            timestamp=timestamp,
            agent_name=self.name,
            market_data=market_block,
            account_data=account_block,
            config=json.dumps(self.config, indent=2)
        )
        return prompt

    def parse_llm_output(self, raw_output: str) -> Optional[Dict[str, Any]]:
        """
        Парсит вывод LLM в структуру, пригодную для исполнения.
        Использует pydantic для валидации CHAIN_OF_THOUGHT.
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

        cot_json_str = cot_match.group(1).strip()
        print(f"[{self.name}] Raw CoT JSON: {cot_json_str}") # Для отладки

        # --- ВАЛИДАЦИЯ С ПОМОЩЬЮ PYDANTIC ---
        try:
            cot_data = ChainOfThought.model_validate_json(cot_json_str) # Pydantic v2
            print(f"[{self.name}] CoT validated successfully: {cot_data.root}") # Pydantic v2
        except ValidationError as e:
            print(f"[{self.name}] Pydantic validation error for CHAIN_OF_THOUGHT: {e}")
            return None
        # --- КОНЕЦ ВАЛИДАЦИИ ---

        # Ищем блок TRADING_DECISIONS (как и раньше)
        dec_match = re.search(r'TRADING_DECISIONS\s*\n\s*(\w+)\s*\n\s*(\w+)\s*\n\s*(\d+)%\s*\n\s*(.*?)\s*\n\s*QUANTITY:\s*([0-9.-]+)', raw_output, re.DOTALL)
        if not dec_match:
            print(f"[{self.name}] Could not find TRADING_DECISIONS block in LLM output.")
            return None

        symbol = dec_match.group(1)
        action = dec_match.group(2) # BUY/SELL/HOLD
        confidence_pct = int(dec_match.group(3))
        justification = dec_match.group(4).strip()
        quantity = float(dec_match.group(5)) # Это quantity из парсинга, может быть не использовано

        # --- СОБИРАЕМ РЕЗУЛЬТАТ ---
        result = {
            "symbol": symbol,
            "action": action,
            "confidence": confidence_pct / 100.0,
            "justification": justification,
            "quantity": quantity, # Сохраняем на случай, если risk_usd не задан
            "raw_chain_of_thought": cot_data # Теперь это валидированный объект Pydantic
        }

        # --- ИЗВЛЕКАЕМ ДАННЫЕ ИЗ ВАЛИДИРОВАННОГО CoT ---
        if symbol in cot_data.root: # Pydantic v2
            cot_details = cot_data.root[symbol] # Pydantic v2
            result.update({
                "leverage": cot_details.leverage,
                "stop_loss": cot_details.stop_loss,
                "profit_target": cot_details.profit_target,
                "invalidation_condition": cot_details.invalidation_condition,
                "risk_usd": cot_details.risk_usd,
            })
        else:
            print(f"[{self.name}] Symbol {symbol} not found in validated CoT. Using defaults.")
            # Можно установить заглушки или вернуть None

        return result


    # --- НОВЫЙ МЕТОД ДЛЯ РАСЧЕТА QUANTITY ---
    def calculate_quantity_based_on_risk(self, symbol: str, entry_price: float, stop_loss_price: float, risk_usd: float) -> Optional[float]:
        """
        Рассчитывает количество (quantity) на основе фиксированного риска в USD,
        цены входа, цены стоп-лосса и текущей волатильности (ATR).

        Args:
            symbol: Символ монеты (например, 'BTC').
            entry_price: Цена входа.
            stop_loss_price: Цена стоп-лосса.
            risk_usd: Фиксированная сумма риска в USD (например, 10).

        Returns:
            Рассчитанное количество (float) или None, если данные недоступны.
        """
        # Получим ATR (например, 14-периодный 4h) через market_fetcher
        # NOTE: market_fetcher.get_all_assets() - это дорогой вызов. Лучше кешировать или получать данные напрямую у exchange.
        # Для простоты, получим ATR через exchange, если он реализован, или через market_fetcher.
        # Предположим, у market_fetcher есть способ получить ATR для конкретного актива.

        # Попробуем получить ATR через exchange_client, если метод реализован.
        # Если нет, используем market_fetcher.
        # NOTE: Это требует, чтобы market_fetcher или exchange_client предоставляли ATR.
        # BingXClient в его текущем виде не возвращает ATR напрямую из get_klines.
        # Его нужно рассчитать на основе свечей.
        # Лучше интегрировать это в MarketFetcher или создать вспомогательный метод в exchange_client.

        # --- ВАРИАНТ 1: Через MarketFetcher (требует доработки, чтобы возвращать ATR) ---
        # market_data = self.market_fetcher.get_all_assets()
        # atr = market_data[symbol]['atr14_4h'] # или аналогичное поле

        # --- ВАРИАНТ 2: Рассчитать ATR вручную через exchange_client ---
        # Получим 4h свечи
        klines_4h = self.exchange.get_klines(symbol, interval="4h", limit=20) # 20 для буфера
        if not klines_4h or len(klines_4h) < 15: # Нужно минимум 14 свечей для ATR(14)
            print(f"[{self.name}] Not enough klines to calculate ATR for {symbol}")
            return None

        # Рассчитаем ATR(14) вручную (среднее значение True Range за 14 периодов)
        # True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges = []
        for i in range(1, len(klines_4h)): # Начинаем с 1, т.к. нужна предыдущая свеча
            high = klines_4h[i]['h']
            low = klines_4h[i]['l']
            prev_close = klines_4h[i-1]['c']
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if len(true_ranges) < 14:
            print(f"[{self.name}] Not enough True Range values to calculate ATR(14) for {symbol}")
            return None

        atr = sum(true_ranges[-14:]) / 14 # Последние 14 значений
        print(f"[{self.name}] Calculated ATR(14) for {symbol}: {atr}")

        # --- РАСЧЁТ QUANTITY ---
        # Убедимся, что SL_Distance > 0, чтобы избежать деления на 0
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance == 0:
            print(f"[{self.name}] SL distance is zero for {symbol}. Cannot calculate quantity.")
            return None

        # Используем ATR как оценку волатильности. Можно использовать sl_distance напрямую.
        # Но ATR даёт более "плавающую" оценку.
        # Для простоты, используем sl_distance (так как SL - это наше конкретное правило выхода).
        # Quantity = Risk_USD / (SL_Distance * Contract_Value_in_USD)
        # Для USDT-перпетуалов Contract_Value = 1.
        calculated_quantity = risk_usd / sl_distance

        print(f"[{self.name}] Calculated quantity for {symbol}: {calculated_quantity} (Risk: ${risk_usd}, SL Dist: {sl_distance}, ATR: {atr})")

        return calculated_quantity


    # --- ОБНОВЛЕННЫЙ execute_decision ---
    def execute_decision(self, decision: Dict[str, Any]):
        """
        Исполняет решение через self.order_manager.
        """
        symbol = decision["symbol"]
        action = decision["action"]
        # qty = decision["quantity"] # БОЛЬШЕ НЕ ИСПОЛЬЗУЕМ ЭТО НАПРЯМУЮ
        sl = decision.get("stop_loss")
        tp = decision.get("profit_target")
        risk_usd = decision.get("risk_usd", 10.0) # Значение по умолчанию, можно настроить в config
        leverage = decision.get("leverage", 10)

        # Проверяем, нужно ли исполнять HOLD
        if action == "HOLD":
             print(f"[{self.name}] Decision is HOLD for {symbol}. No action taken.")
             return

        # Получим текущую цену через exchange
        all_mids = self.exchange.get_all_mids()
        if not all_mids or symbol not in all_mids:
            print(f"[{self.name}] Cannot execute decision: Cannot get current price for {symbol}")
            return

        current_price = all_mids[symbol]
        is_buy = (action.upper() == "BUY")

        # --- РАСЧЁТ QUANTITY НА ОСНОВЕ РИСКА ---
        calculated_qty = None
        if sl and risk_usd:
            calculated_qty = self.calculate_quantity_based_on_risk(
                symbol=symbol,
                entry_price=current_price, # Используем текущую цену как приближение к цене входа
                stop_loss_price=sl,
                risk_usd=risk_usd
            )
            if calculated_qty is None:
                print(f"[{self.name}] Failed to calculate quantity based on risk for {symbol}. Using default or skipping.")
                # Можно использовать decision["quantity"] как fallback, или пропустить
                return # Пример: пропускаем, если не можем рассчитать
        else:
            print(f"[{self.name}] SL or risk_usd not provided, cannot calculate risk-based quantity. Using parsed quantity.")
            calculated_qty = decision.get("quantity", 0.0) # Fallback

        # Проверим, что calculated_qty положительное
        if calculated_qty <= 0:
             print(f"[{self.name}] Calculated quantity is invalid: {calculated_qty}. Skipping execution.")
             return

        # Рассчитаем цену ордера (например, на 0.1% выше/ниже для лимита)
        limit_px = current_price * 1.001 if is_buy else current_price * 0.999

        # --- ВЫЗОВ OrderManager С РАСЧИТАННЫМ QUANTITY ---
        bracket_result = self.order_manager.place_bracket_order(
            symbol=symbol,
            side=action,
            quantity=calculated_qty, # <-- ИСПОЛЬЗУЕМ РАСЧИТАННОЕ КОЛИЧЕСТВО
            limit_px=limit_px,
            take_profit_px=tp,
            stop_loss_px=sl,
            order_type="limit",
            leverage=leverage # Передаём leverage, если используется
        )

        if bracket_result:
            print(f"[{self.name}] Bracket order executed for {calculated_qty} {symbol} @ ~{current_price}. SL: {sl}, TP: {tp}. IDs: {bracket_result}")
        else:
            print(f"[{self.name}] Failed to execute bracket order for {symbol}.")
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

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
                print(f"[{self.name}] Decision parsed: {decision['action']} {decision.get('quantity', 'N/A')} {decision['symbol']} (RiskUSD: {decision.get('risk_usd')})")
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