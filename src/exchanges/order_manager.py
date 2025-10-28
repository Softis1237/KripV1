# src/exchanges/order_manager.py

from typing import Dict, Any, Optional, List
import time
import logging

# Настройка логирования для OrderManager
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Простой обработчик для вывода в консоль (можно настроить на файл)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class OrderManager:
    def __init__(self, exchange_client):
        self.exchange = exchange_client
        # Словарь для отслеживания связанных ордеров: {position_id: {'main': id, 'tp': id, 'sl': id}}
        # Для упрощения, используем symbol и время как идентификатор "позиции"
        # В реальности можно использовать реальный position_id, если биржа его предоставляет после входа
        self.active_brackets = {}

    def _get_position_key(self, symbol: str) -> str:
        """Генерирует уникальный ключ для отслеживания позиции по символу и времени."""
        # Упрощённый ключ. В реальности может быть связан с конкретным order_id открытия.
        return f"{symbol}_{int(time.time())}"

    def place_bracket_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        limit_px: float,
        take_profit_px: Optional[float] = None,
        stop_loss_px: Optional[float] = None,
        order_type: str = "limit",
        leverage: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Выставляет основной ордер и связанные TP/SL как отдельные reduceOnly ордера.
        """
        position_key = self._get_position_key(symbol)
        logger.info(f"[OrderManager] Placing bracket order for {position_key}")

        # 1. Выставляем основной ордер (вход)
        main_order_response = self.exchange.place_order(
            coin=symbol,
            is_buy=(side.upper() == "BUY"),
            sz=quantity,
            limit_px=limit_px,
            order_type=order_type,
            # leverage не всегда передаётся в place_order, зависит от биржи
        )

        if not main_order_response:
            logger.error(f"[OrderManager] Failed to place main order for {position_key}. Aborting TP/SL.")
            return None

        logger.info(f"[OrderManager] Main order placed successfully for {position_key}: {main_order_response}")

        bracket_ids = {
            'main': main_order_response.get('orderId') or main_order_response.get('id'), # Зависит от биржи
            'tp': None,
            'sl': None
        }

        # 2. Выставляем Take Profit (reduceOnly)
        if take_profit_px:
            tp_order_response = self.exchange.place_order(
                coin=symbol,
                is_buy=(side.upper() != "BUY"),  # Продажа если BUY, покупка если SELL
                sz=quantity,
                limit_px=take_profit_px,
                order_type=order_type,
                reduce_only=True
            )
            if tp_order_response:
                bracket_ids['tp'] = tp_order_response.get('orderId') or tp_order_response.get('id')
                logger.info(f"[OrderManager] TP order placed for {position_key}: {bracket_ids['tp']}")
            else:
                logger.error(f"[OrderManager] Failed to place TP order for {position_key}.")

        # 3. Выставляем Stop Loss (reduceOnly)
        if stop_loss_px:
            sl_order_response = self.exchange.place_order(
                coin=symbol,
                is_buy=(side.upper() != "BUY"),
                sz=quantity,
                limit_px=stop_loss_px,
                order_type=order_type,
                reduce_only=True
            )
            if sl_order_response:
                bracket_ids['sl'] = sl_order_response.get('orderId') or sl_order_response.get('id')
                logger.info(f"[OrderManager] SL order placed for {position_key}: {bracket_ids['sl']}")
            else:
                logger.error(f"[OrderManager] Failed to place SL order for {position_key}.")

        # Сохраняем идентификаторы для возможного управления позже
        self.active_brackets[position_key] = bracket_ids
        logger.info(f"[OrderManager] Bracket order complete for {position_key}: {bracket_ids}")

        return bracket_ids

    def cancel_bracket_order(self, position_key: str):
        """
        Отменяет все ордера в брекете (main, tp, sl) по ключу позиции.
        """
        if position_key not in self.active_brackets:
            logger.warning(f"[OrderManager] Bracket for {position_key} not found.")
            return

        bracket_ids = self.active_brackets[position_key]
        logger.info(f"[OrderManager] Cancelling bracket order for {position_key}: {bracket_ids}")

        # Отменяем все ордера в брекете
        for order_type, order_id in bracket_ids.items():
            if order_id:
                # Используем метод отмены из exchange_client
                # NOTE: cancel_order сигнатура может отличаться у разных бирж (symbol + orderId, или просто orderId)
                # Для упрощения, предположим, что exchange_client.handle_cancel_order(order_id, symbol) -> response
                # Или exchange_client.cancel_order(orderId=order_id, symbol=symbol)
                # Нужно смотреть конкретную реализацию в BingXClient и HyperliquidClient
                # Пока используем общий интерфейс, который может потребовать адаптации
                # Пример: self.exchange.cancel_order(order_id, symbol) # где order_id и symbol
                # Потому что нам нужен symbol для бирж, как BingX
                # Нужно получить symbol из position_key или хранить отдельно
                # Для этого примера, предположим, что symbol можно извлечь из position_key
                symbol = position_key.split('_')[0]
                try:
                    cancel_response = self.exchange.cancel_order(order_id, symbol)
                    if cancel_response:
                         logger.info(f"[OrderManager] {order_type.upper()} order {order_id} cancelled successfully.")
                    else:
                         logger.warning(f"[OrderManager] Failed to cancel {order_type.upper()} order {order_id}.")
                except Exception as e:
                     logger.error(f"[OrderManager] Error cancelling {order_type.upper()} order {order_id}: {e}")

        # Удаляем из отслеживания
        del self.active_brackets[position_key]
        logger.info(f"[OrderManager] Bracket order cancelled and removed from tracking: {position_key}")

    def get_active_brackets(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает словарь активных брекет-ордеров.
        """
        return self.active_brackets.copy()

    # --- Возможные будущие методы ---
    # def modify_bracket_order(self, position_key: str, new_tp_px: Optional[float] = None, new_sl_px: Optional[float] = None):
    #     # Модификация TP/SL
    #     pass
    # def close_position(self, position_key: str):
    #     # Закрытие позиции и отмена оставшихся SL/TP
    #     pass
