"""
Main entry point for running LLM trading agents.
"""

import asyncio
import os
from typing import Dict
from pathlib import Path
import json

from agents.llm_agent import LLMAgent

def load_config() -> Dict:
    """Loads configuration from agents.json."""
    config_path = Path(__file__).parent / "config" / "agents.json"
    with open(config_path) as f:
        return json.load(f)

async def run_agent(name: str, config: Dict):
    """Runs a single agent in its own task."""
    agent = LLMAgent(name, config)
    await agent.run()

async def main():
    """Main entry point."""
    # Load configuration
    config = load_config()
    
    # Create tasks for each agent
    tasks = []
    for name, agent_config in config["agents"].items():
        # Get API key from environment
        api_key = os.getenv(agent_config["api_key_env"])
        if not api_key:
            print(f"Warning: No API key found for {name}")
            continue
            
        agent_config["api_key"] = api_key
        tasks.append(run_agent(name, agent_config))
    
    # Run all agents concurrently
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())