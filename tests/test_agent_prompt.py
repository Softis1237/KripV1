# tests/test_agent_prompt.py

import pytest
from src.agents.llm_agent import LLMAgent
from src.data.market_fetcher import MarketFetcher
from src.data.account_state import AccountState
import json

def test_market_fetcher_returns_data():
    fetcher = MarketFetcher()
    data = fetcher.get_all_assets()
    assert "BTC" in data
    assert "current_price" in data["BTC"]
    assert isinstance(data["BTC"]["current_price"], float)
    print(f"✅ BTC Price: {data['BTC']['current_price']}")


def test_account_state_returns_data():
    account = AccountState()
    data = account.get()
    assert "total_account_value" in data
    assert "positions" in data
    assert isinstance(data["total_account_value"], float)
    print(f"✅ Account Value: {data['total_account_value']}")


def test_prompt_building():
    agent = LLMAgent("test_agent", {"wallet_address": "0x000000000000000000000000000000000000dead"})
    market_data = agent.market_fetcher.get_all_assets()
    account_data = agent.account_state.get()

    prompt = agent.build_prompt(market_data, account_data)

    # Проверим, что промпт содержит ключевые слова
    assert "It has been" in prompt
    assert "CURRENT MARKET STATE FOR ALL COINS" in prompt
    assert "HERE IS YOUR ACCOUNT INFORMATION & PERFORMANCE" in prompt
    assert "Trade ONLY BTC, ETH, SOL, XRP, DOGE, and BNB" in prompt
    assert "Respond in this EXACT format:" in prompt
    # Проверим, что позиции сериализованы как JSON
    assert json.dumps(account_data["positions"], separators=(',', ':')) in prompt

    print(f"✅ Prompt built successfully. Length: {len(prompt)} chars")
    # print(f"Prompt preview:\n{prompt[:500]}...") # <-- Для отладки


def test_agent_run_cycle():
    agent = LLMAgent("test_agent", {"wallet_address": "0x000000000000000000000000000000000000dead"})
    prompt = agent.run_cycle()
    assert len(prompt) > 1000  # Промпт должен быть длинным
    print("✅ Agent run_cycle completed.")


if __name__ == "__main__":
    test_market_fetcher_returns_data()
    test_account_state_returns_data()
    test_prompt_building()
    test_agent_run_cycle()
    print("\n🎉 All tests passed!")
