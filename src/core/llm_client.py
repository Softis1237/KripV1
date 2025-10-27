"""
LLM client for interacting with language models.
"""

from typing import Dict, Optional
import json

class LLMClient:
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key
        self.base_params = {
            "temperature": 0.1,
            "max_tokens": 500,
            "response_format": {"type": "json_object"}
        }
        
    async def call(self, prompt: str) -> Dict:
        """Calls LLM API with the given prompt."""
        if self.model == "deepseek-chat":
            return await self._call_deepseek(prompt)
        elif self.model == "qwen-max":
            return await self._call_qwen(prompt)
        else:
            raise ValueError(f"Unsupported model: {self.model}")
            
    async def _call_deepseek(self, prompt: str) -> Dict:
        """Calls DeepSeek through OpenRouter."""
        pass
        
    async def _call_qwen(self, prompt: str) -> Dict:
        """Calls Qwen through Alibaba Cloud."""
        pass