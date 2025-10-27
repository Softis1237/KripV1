# tests/test_llm_client.py

from src.core.llm_client import LLMClient

def test_deepseek_client():
    # Убедитесь, что переменная DEEPSEEK_API_KEY установлена
    client = LLMClient("deepseek-chat", "DEEPSEEK_API_KEY", provider="openrouter")
    response = client.call("Say 'Hello, world!' in one word.", max_tokens=10)
    print(f"DeepSeek response: {response}")
    assert response is not None

def test_qwen_client():
    # Убедитесь, что переменная QWEN_API_KEY установлена
    client = LLMClient("qwen-max", "QWEN_API_KEY", provider="alibaba")
    response = client.call("Say 'Hi' in one word.", max_tokens=10)
    print(f"Qwen response: {response}")
    assert response is not None

if __name__ == "__main__":
    # Эти тесты требуют реальных API-ключей
    # test_deepseek_client()
    # test_qwen_client()
    print("LLM Client tests defined. Run with valid API keys.")