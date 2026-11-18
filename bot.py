from aiogram.client.default import DefaultBotProperties
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder

from config import BOT_TOKEN, REDIS_URL
from database import init_pool, close_pool
from middlewares import AuthMiddleware

# Импорт роутеров (ваша часть + часть стажёра)
import handlers.admin as admin_handlers
import handlers.common as common_handlers
import handlers.user as user_handlers
import handlers.teacher as teacher_handlers

logging.basicConfig(level=logging.INFO)

session = AiohttpSession(
    api=TelegramAPIServer.from_base('https://bot-proxy.koshkacat2238.workers.dev')
)

async def main():
    await init_pool()
    storage = RedisStorage.from_url(REDIS_URL, key_builder=DefaultKeyBuilder(with_bot_id=True))
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")  # <--- ДОБАВИТЬ ЭТО
    )
    me = await bot.get_me()
    print(f"Успех! Бот @{me.username} подключен через прокси.")
    dp = Dispatcher(storage=storage)

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Порядок важен: /cancel должен ловиться первым
    dp.include_router(admin_handlers.router)
    dp.include_router(teacher_handlers.router)
    dp.include_router(common_handlers.router)
    dp.include_router(user_handlers.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await storage.close()
        await close_pool()

if __name__ == "__main__":
    asyncio.run(main())