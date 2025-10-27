import asyncio
import os
import sys
# Добавим src в путь, чтобы можно было импортировать модули
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# --- Добавь ЭТИ строки ---
from dotenv import load_dotenv
# Загружаем переменные из .env файла в текущей директории (KripV1/)
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

print("Тестируем подключение к BingX...")

# --- 1. Проверим публичные данные: цены ---
print("\n1. Получаем цены для BTC, ETH...")
try:
    prices = client.get_all_mids()
    print(f"   Полученные цены: {prices}")
except Exception as e:
    print(f"   Ошибка при получении цен: {e}")

# --- 2. Проверим публичные данные: свечи ---
print("\n2. Получаем 3-минутные свечи для BTC...")
try:
    klines = client.get_klines(symbol="BTC", interval="3m", limit=5)
    print(f"   Полученные свечи: {klines}")
except Exception as e:
    print(f"   Ошибка при получении свечей: {e}")

# --- 3. Проверим публичные данные: фандинг ---
print("\n3. Получаем funding rate для BTC...")
try:
    funding_rate = client.get_funding_rate("BTC")
    print(f"   Funding rate: {funding_rate}")
except Exception as e:
    print(f"   Ошибка при получении funding rate: {e}")

# --- 4. Проверим приватные данные: аккаунт (только если ключи верны) ---
print("\n4. Получаем информацию о счёте...")
try:
    account_info = client.get_account_info()
    print(f"   Информация о счёте: {account_info}")
except Exception as e:
    print(f"   Ошибка при получении информации о счёте: {e}")

# --- 5. Проверим приватные данные: позиции (только если ключи верны) ---
print("\n5. Получаем открытые позиции...")
try:
    positions = client.get_positions()
    print(f"   Открытые позиции: {positions}")
except Exception as e:
    print(f"   Ошибка при получении позиций: {e}")

print("\n--- Тестирование завершено ---")
