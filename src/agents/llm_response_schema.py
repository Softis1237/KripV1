# src/agents/llm_response_schema.py

from pydantic import BaseModel, Field
from typing import Dict, Optional, Literal
from decimal import Decimal # Для более точного представления цен/количеств

# --- Внутренние модели ---

class CoTEntry(BaseModel):
    """
    Модель для одного элемента в CHAIN_OF_THOUGHT.
    """
    quantity: float = Field(..., description="Размер позиции/ордера")
    stop_loss: Optional[float] = Field(None, description="Цена стоп-лосс")
    signal: Literal["HOLD", "BUY", "SELL"] = Field(..., description="Сигнал: HOLD, BUY, SELL")
    profit_target: Optional[float] = Field(None, description="Цена тейк-профит")
    invalidation_condition: Optional[str] = Field(None, description="Условие для отмены/выхода")
    justification: str = Field(..., description="Обоснование решения")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность (0.0 - 1.0)")
    leverage: int = Field(..., ge=1, le=100, description="Используемое плечо") # Пример ограничения
    risk_usd: Optional[float] = Field(None, description="Риск в USD")
    coin: str = Field(..., description="Название монеты (например, 'BTC')")


class ChainOfThought(BaseModel):
    """
    Модель для всего блока CHAIN_OF_THOUGHT.
    Предполагается, что он представляет собой словарь { "COIN": CoTEntry, ... }
    """
    __root__: Dict[str, CoTEntry] # Pydantic v1 стиль, для v2 используем модель с корневым полем
    # В Pydantic v2 можно использовать:
    root: Dict[str, CoTEntry]

    def __init__(self, **data):
        # Для совместимости с v1/v2, можно принять словарь напрямую
        super().__init__(root=data)

    def __getitem__(self, item):
        return self.root[item]

    def get(self, item, default=None):
        return self.root.get(item, default)

    def items(self):
        return self.root.items()

    def keys(self):
        return self.root.keys()

    # Pydantic v2:
    # model_config = ConfigDict(extra='forbid') # Запретить лишние поля


# --- Основная модель для всего ответа (упрощённо) ---
class LLMTradingResponse(BaseModel):
    """
    Модель для основного ответа LLM, включая CoT и основное торговое решение.
    """
    chain_of_thought: ChainOfThought = Field(..., alias='CHAIN_OF_THOUGHT')
    # TRADING_DECISIONS - это текстовый блок, который мы парсим отдельно.
    # Для строгой валидации TRADING_DECISIONS нужно будет создать отдельный парсер,
    # но основные данные из CoT будут валидированы.
    # Здесь мы можем добавить поля, извлечённые из TRADING_DECISIONS, если они критичны.
    trading_symbol: str = Field(..., description="Символ для торговли (например, 'BTC')")
    trading_action: Literal["HOLD", "BUY", "SELL"] = Field(..., description="Действие")
    trading_confidence_pct: int = Field(..., ge=0, le=100, description="Уверенность в процентах")
    trading_quantity: float = Field(..., description="Количество")
    trading_justification: str = Field(..., description="Обоснование из TRADING_DECISIONS")

    # Pydantic v2:
    # model_config = ConfigDict(extra='forbid')
