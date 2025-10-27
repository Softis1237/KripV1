# src/core/llm_client.py

import requests
import json
from typing import Dict, Optional
import os
import time

class LLMClient:
    def __init__(self, model_name: str, api_key_env: str, provider: str = None):
        """
        Инициализирует клиента для вызова LLM.

        :param model_name: Название модели, например 'deepseek-chat', 'qwen-max'
        :param api_key_env: Название переменной окружения, где хранится API-ключ
        :param provider: 'openrouter', 'alibaba', 'fireworks', 'custom' и т.д.
        """
        self.model_name = model_name
        self.api_key = os.getenv(api_key_env)
        if not self.api_key:
            raise ValueError(f"API key not found in environment variable: {api_key_env}")

        # Определим endpoint и headers автоматически по провайдеру или названию модели
        if provider:
            self.provider = provider
        elif "deepseek" in model_name.lower():
            self.provider = "openrouter"
        elif "qwen" in model_name.lower():
            self.provider = "alibaba"
        else:
            self.provider = "openrouter"  # по умолчанию

        if self.provider == "openrouter":
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        elif self.provider == "alibaba":
            # Пример для Alibaba Cloud DashScope
            # Документация: https://help.aliyun.com/zh/dashscope/developer-reference/api-details
            self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable" # если нужен асинхронный вызов
            }
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def call(self, prompt: str, max_tokens: int = 512, temperature: float = 0.1) -> Optional[str]:
        """
        Вызывает LLM с заданным промптом.

        :return: Ответ модели (или None в случае ошибки)
        """
        if self.provider == "openrouter":
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                # "response_format": {"type": "json_object"} # Опционально, если хочешь JSON
            }
        elif self.provider == "alibaba":
            # Для Qwen через Alibaba Cloud DashScope
            # Документация: https://help.aliyun.com/zh/dashscope/developer-reference/llm-v1-detail
            payload = {
                "model": self.model_name,
                "input": {
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                "parameters": {
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            }
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        try:
            start_time = time.time()
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=60)
            latency = time.time() - start_time

            if response.status_code != 200:
                print(f"LLM call failed: {response.status_code} - {response.text}")
                return None

            resp_json = response.json()

            # Парсинг ответа в зависимости от провайдера
            if self.provider == "openrouter":
                content = resp_json['choices'][0]['message']['content']
            elif self.provider == "alibaba":
                # Пример пути к результату для Alibaba DashScope
                content = resp_json['output']['text']
            else:
                content = None

            print(f"[LLM] Call took {latency:.2f}s")
            return content

        except requests.exceptions.RequestException as e:
            print(f"Request error during LLM call: {e}")
            return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing LLM response: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error during LLM call: {e}")
            return None
