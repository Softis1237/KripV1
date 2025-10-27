# tests/test_bingx_data.py

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.exchanges.bingx_exchange import BingXClient

# Убедись, что в .env у тебя заданы переменные
API_KEY_ENV = "BINGX_API_KEY"
SECRET_KEY_ENV = "BINGX_SECRET_KEY"

api_key = os.getenv(API_KEY_ENV)
secret_key = os.getenv(SECRET_KEY_ENV)

if not api_key or not secret_key:
    print(f"Ошибка: Не найдены переменные окружения {API_KEY_ENV} или {SECRET_KEY_ENV} в .env файле.")
    sys.exit(1)

# Создаём клиент
client = BingXClient(api_key_env=API_KEY_ENV, secret_key_env=SECRET_KEY_ENV)

# --- Тест с отображением ошибок ---
def safe_call(name, fn):
    try:
        res = fn()
        print(f"{name}: OK -> {str(res)[:200]}...") # Обрезаем длинный вывод
    except Exception as e:
        print(f"{name}: FAIL -> {e}")

print("Тестируем подключение к BingX...")

# Публичные вызовы (теперь используем _make_request)
safe_call("1) Ticker BTC", lambda: client._make_request("GET","/openApi/swap/v2/quote/price",{"symbol":"BTC-USDT"}))
safe_call("2) Klines 3m BTC", lambda: client._make_request("GET","/openApi/swap/v3/quote/klines",{"symbol":"BTC-USDT","interval":"3m","limit":5}))
safe_call("3) Funding BTC", lambda: client._make_request("GET","/openApi/swap/v2/quote/fundingRate",{"symbol":"BTC-USDT", "limit": 1}))

# Приватные вызовы (теперь используем _make_request)
safe_call("4) Account Info (Raw)", lambda: client._make_request("GET","/openApi/swap/v2/user/balance", signed=True))
safe_call("5) Positions (Raw)", lambda: client._make_request("GET","/openApi/swap/v2/user/positions", signed=True))

print("\n--- Тестирование завершено ---")

# --- Тест методов интерфейса BaseExchange ---
print("\n--- Тест методов интерфейса ---")
safe_call("get_all_mids", lambda: client.get_all_mids())
safe_call("get_klines (obj)", lambda: client.get_klines("BTC", "3m", 5))
safe_call("get_funding_rate (obj)", lambda: client.get_funding_rate("BTC"))
safe_call("get_account_info (obj)", lambda: client.get_account_info())
safe_call("get_positions (obj)", lambda: client.get_positions())
