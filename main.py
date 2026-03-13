from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import load_config
from database import Database
from handlers.callbacks import router as callbacks_router
from handlers.commands import router as commands_router
from services import ProcessManager


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    if not config.bot_token:
        raise RuntimeError("Переменная BOT_TOKEN не задана")

    db = Database(config.db_path)
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    bot.db = db
    bot.config = config
    bot.process_manager = ProcessManager(bot, db, config)

    dp = Dispatcher()
    dp.include_router(callbacks_router)
    dp.include_router(commands_router)

    await bot.process_manager.restore_from_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
