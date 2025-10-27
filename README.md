# KripV1 - LLM Trading System

## Описание
Торговая система на основе LLM (Large Language Models) для автоматизированной торговли на криптовалютном рынке.

## Структура проекта
```
KripV1/
├── agents/        # Торговые агенты на основе LLM
├── data/         # Компоненты для работы с данными
├── core/         # Ядро системы
├── prompts/      # Системные промпты для LLM
├── logs/         # Логи работы системы
├── config/       # Конфигурационные файлы
└── tests/        # Тесты
```

## Установка
1. Клонировать репозиторий
```bash
git clone https://github.com/your-username/KripV1.git
cd KripV1
```

2. Создать виртуальное окружение и активировать его
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

3. Установить зависимости
```bash
pip install -r requirements.txt
```

## Настройка
1. Создать файл config/local.json на основе config/example.json
2. Заполнить необходимые API ключи и настройки

## Использование
```bash
python run.py
```

## Тестирование
```bash
python -m pytest tests/
```

## Лицензия
MIT License

## Автор
[Ваше имя]