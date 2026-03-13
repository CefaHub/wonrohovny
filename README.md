# K-pop Telegram Bot (aiogram 3.x)

Групповой Telegram-бот для флудилок с профилями, отношениями, беременностью, экономикой, банками, магазинами и работой.

## Структура

- `main.py` — точка входа
- `config.py` — конфиг и пути
- `database.py` — SQLite и инициализация таблиц
- `models.py` — датаклассы
- `services.py` — фоновые процессы беременности/секса
- `utils.py` — парсинг и помощники
- `keyboards.py` — inline-клавиатуры
- `handlers/commands.py` — текстовые команды
- `handlers/callbacks.py` — callback-обработчики
- `requirements.txt` — зависимости

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# заполнить BOT_TOKEN
python main.py
```

## Важно

- База данных создаётся автоматически.
- По умолчанию путь к БД — `data/bot.db` локально и `/app/data/bot.db` на Bothost.
- Все таймеры сделаны через `asyncio.create_task()` + `asyncio.sleep()`.
- После перезапуска процесса активные таймеры в текущем MVP не восстанавливаются автоматически из БД. Для продакшена стоит добавить recovery scheduler на startup.
