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
        # 1. Создаём клиента LLM
        llm_client = LLMClient(
            model_name=cfg["model"],
            api_key_env=cfg["llm_api_key_env"],
            provider=cfg.get("provider")
        )

        # 2. Создаём клиента биржи
        broker = cfg.get("broker", "hyperliquid") # по умолчанию Hyperliquid
        exchange_client = None
        if broker == "hyperliquid":
            exchange_client = HyperliquidExchange(
                wallet_address=cfg.get("exchange_wallet_address", "0x000000000000000000000000000000000000dead"),
                private_key_env=cfg.get("exchange_private_key_env", "HYPERLIQUID_SECRET"), 
                is_testnet=cfg.get("is_testnet", False)
            )
        elif broker == "bingx":
            exchange_client = BingXClient(
                api_key_env=cfg.get("exchange_api_key_env", "BINGX_API_KEY"), 
                secret_key_env=cfg.get("exchange_api_secret_env", "BINGX_SECRET_KEY"), 
                is_testnet=cfg.get("is_testnet", False)
            )
        else:
            raise ValueError(f"Unsupported broker: {broker}")

        if exchange_client is None:
            print(f"Failed to create exchange client for agent {name}")
            continue

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
