# tests/test_llm_agent_full.py

from src.agents.llm_agent import LLMAgent

def test_agent_cycle_with_mock_llm():
    # Тест, где LLM возвращает фиксированный ответ
    # Пока сложно протестировать без реального API, но можно проверить парсер
    agent = LLMAgent("test_agent", {
        "model": "test-model",
        "api_key_env": "DUMMY_KEY",
        "provider": "custom"
    })

    # Пример ответа LLM как с nof1.ai
    mock_response = """
It has been 7259 minutes since you started trading. The current time is 2025-10-27 14:10:19.368166 and you've been invoked 4514 times.

▶
CHAIN_OF_THOUGHT
{ "ETH": { "signal": "HOLD", "justification": "Price is testing support but long-term bullish.", "confidence": 0.88, "leverage": 25, "stop_loss": 4120.0, "profit_target": 4280.0, "invalidation_condition": "4h close below 4018.868", "risk_usd": 1560.0 } }

▶
TRADING_DECISIONS
ETH
HOLD
88%
Price is testing the intraday support near 4140 but remains above the critical 4h 20 EMA (4032.49). The long-term trend is still bullish (4h EMAs stacked positively, RSI > 68), and recent intraday weakness appears corrective. Funding is neutral, OI is stable. The invalidation condition (4h close below 4018.868) has not triggered, so the position remains valid.

QUANTITY: 22.66
    """

    decision = agent.parse_llm_output(mock_response)
    assert decision is not None
    assert decision["symbol"] == "ETH"
    assert decision["action"] == "HOLD"
    assert decision["confidence"] == 0.88
    assert decision["quantity"] == 22.66
    assert decision["raw_chain_of_thought"]["ETH"]["leverage"] == 25
    print("✅ LLM output parsing test passed.")


if __name__ == "__main__":
    test_agent_cycle_with_mock_llm()
    print("\n🎉 Agent parsing test passed!")
