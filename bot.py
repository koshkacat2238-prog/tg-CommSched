import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import BotCommand, ErrorEvent, MenuButtonWebApp, WebAppInfo
from dotenv import load_dotenv

from config import BOT_TOKEN, REDIS_URL, WEBAPP_URL
from database import close_pool, get_pool, init_pool
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
        # Принудительно используем IPv4 и не переиспользуем keep-alive сокеты
        self._connector_init["family"] = socket.AF_INET
        self._connector_init["force_close"] = True


async def setup_bot_ui(bot: Bot):
    """Регистрирует меню команд и синюю кнопку Web App рядом с полем ввода."""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="schedule", description="Открыть расписание"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ]
    await bot.set_my_commands(commands)

    if WEBAPP_URL:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Расписание",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        )


async def evening_digest_worker(bot: Bot):
    """Фоновая задача: каждый день в 20:00 по МСК рассылает напоминание на завтра."""
    tz = ZoneInfo("Europe/Moscow")
    while True:
        now = datetime.now(tz)
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        await asyncio.sleep((target - now).total_seconds())

        try:
            tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
            pool = get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_id, group_name
                    FROM users
                    WHERE is_approved = TRUE
                      AND COALESCE(is_banned, FALSE) = FALSE
                      AND group_name IS NOT NULL
                    """
                )

            for row in rows:
                try:
                    text = (
                        f"📅 <b>Напоминание на завтра ({tomorrow.strftime('%d.%m')})</b>\n"
                        f"Группа: <b>{row['group_name']}</b>\n\n"
                        f"Актуальные пары и домашние задания уже доступны в расписании."
                    )
                    await bot.send_message(row["user_id"], text)
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logging.warning(f"Не удалось отправить сводку {row['user_id']}: {e}")
        except Exception as e:
            logging.error(f"Ошибка в фоновой задаче вечерней сводки: {e}")


async def main():
    await init_pool()

    cf_api_url = os.getenv("CF_API_URL", "").strip()
    if cf_api_url:
        session = IPv4Session(
            api=TelegramAPIServer.from_base(cf_api_url),
            timeout=15
        )
    else:
        session = IPv4Session(timeout=15)

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
        # Глушим временные сетевые сбои прокси, чтобы не засорять логи трейсбеками
        if isinstance(event.exception, (TelegramNetworkError, TelegramBadRequest)):
            logging.warning(f"Временная ошибка Telegram API: {event.exception}")
            return True
        logging.exception("Необработанная ошибка", exc_info=event.exception)
        return True

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(admin_handlers.router)
    dp.include_router(teacher_handlers.router)
    dp.include_router(common_handlers.router)
    dp.include_router(user_handlers.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await setup_bot_ui(bot)

    digest_task = asyncio.create_task(evening_digest_worker(bot))

    logging.info("Bot started")
    try:
        await dp.start_polling(bot, polling_timeout=8)
    finally:
        digest_task.cancel()
        await storage.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())