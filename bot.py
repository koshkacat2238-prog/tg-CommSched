import asyncio
import logging
import os
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import ErrorEvent
from dotenv import load_dotenv

from config import BOT_TOKEN, REDIS_URL
from database import close_pool, init_pool
from middlewares import AuthMiddleware

import handlers.admin as admin_handlers
import handlers.common as common_handlers
import handlers.teacher as teacher_handlers
import handlers.user as user_handlers

load_dotenv()
logging.basicConfig(level=logging.INFO)


class IPv4Session(AiohttpSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET
        # Не переиспользуем keep-alive сокеты, которые могут обрываться DPI/Cloudflare
        self._connector_init["force_close"] = True


async def main():
    await init_pool()

    cf_api_url = os.getenv("CF_API_URL", "").strip()
    if cf_api_url:
        session = IPv4Session(
            api=TelegramAPIServer.from_base(cf_api_url),
            timeout=30
        )
    else:
        session = IPv4Session(timeout=30)

    storage = RedisStorage.from_url(
        REDIS_URL,
        key_builder=DefaultKeyBuilder(with_bot_id=True)
    )
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session
    )
    dp = Dispatcher(storage=storage)

    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        if isinstance(event.exception, (TelegramNetworkError, TelegramBadRequest)):
            logging.warning(f"Telegram API transient error: {event.exception}")
            return True
        logging.exception("Unhandled error", exc_info=event.exception)
        return True

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(admin_handlers.router)
    dp.include_router(teacher_handlers.router)
    dp.include_router(common_handlers.router)
    dp.include_router(user_handlers.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started")
    try:
        await dp.start_polling(bot, polling_timeout=10)
    finally:
        await storage.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())