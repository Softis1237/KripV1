# run_broker_agnostic.py

from src.agents.llm_agent_broker_agnostic import LLMAgent
from src.core.llm_client import LLMClient
from src.exchanges.hyperliquid_exchange import HyperliquidExchange
from src.exchanges.bingx_exchange import BingXClient
import json
import threading
import time

def load_config(path: str):
    with open(path, 'r') as f:
        return json.load(f)

def main():
    config = load_config('src/config/agents.json')
    agents = config.get("agents", {})

    agent_instances = []

    for name, cfg in agents.items():
        print(f"Initializing agent: {name}")
        # 1. Создаём клиента биржи
        broker = cfg.get("broker", "hyperliquid") # по умолчанию Hyperliquid
        if broker == "hyperliquid":
            exchange_client = HyperliquidExchange(
                wallet_address=cfg.get("wallet_address", "0x000000000000000000000000000000000000dead"),
                private_key_env=cfg.get("private_key_env", "HYPERLIQUID_SECRET"), # Укажи переменную в конфиге
                is_testnet=cfg.get("is_testnet", False)
            )
        elif broker == "bingx":
            exchange_client = BingXClient(
                api_key_env=cfg.get("api_key_env", "BINGX_API_KEY"), # Укажи переменные в конфиге
                secret_key_env=cfg.get("api_secret_env", "BINGX_SECRET_KEY"),
                is_testnet=cfg.get("is_testnet", False)
            )
        else:
            raise ValueError(f"Unsupported broker: {broker}")

        # 2. Создаём клиента LLM
        llm_client = LLMClient(
            model_name=cfg["model"],
            api_key_env=cfg["api_key_env"],
            provider=cfg.get("provider")
        )

        # 3. Создаём агента
        agent = LLMAgent(name, cfg, exchange_client, llm_client)
        agent_instances.append(agent)

    # 4. Запускаем агентов в потоках
    threads = []
    for agent in agent_instances:
        t = threading.Thread(target=agent.run)
        t.daemon = True
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down agents...")
        # Здесь можно добавить логику graceful shutdown, если нужно.

if __name__ == "__main__":
    main()
