import asyncio
import html
import json
import logging
import os
import socket
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

import redis.asyncio as redis
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import BotCommand, ErrorEvent, MenuButtonWebApp, Message, WebAppInfo
from dotenv import load_dotenv

from config import BOT_TOKEN, REDIS_URL, WEBAPP_URL
from database import close_pool, get_pool, init_pool
from middlewares import AuthMiddleware
from services import homework as hw_service
from services.parser import fetch_schedule_from_ruz

import handlers.admin as admin_handlers
import handlers.common as common_handlers
import handlers.teacher as teacher_handlers
import handlers.user as user_handlers

load_dotenv()

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("logs/bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
    ],
)

STUDENT_DIGEST_ROLES = ("student", "headman", "admin", "owner")

WEEKDAYS_RU = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)


class IPv4Session(AiohttpSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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


def _filter_lessons_for_student(raw_lessons: list[dict], target_date_iso: str, user: dict) -> list[dict]:
    """Оставляет пары на нужную дату с учётом выбранных студентом преподавателей по языкам."""
    eng_t = (user.get("eng_teacher") or "").strip().lower()
    chin_t = (user.get("chin_teacher") or "").strip().lower()

    filtered = []
    for les in raw_lessons:
        if les.get("date") != target_date_iso:
            continue

        subj_lower = (les.get("subject") or "").lower()
        teacher_lower = (les.get("teacher") or "").lower()

        if ("иностранный" in subj_lower or "английский" in subj_lower) and eng_t:
            if eng_t not in teacher_lower:
                continue

        if "китайский" in subj_lower and chin_t:
            if chin_t not in teacher_lower:
                continue

        filtered.append(les)

    filtered.sort(key=lambda item: item.get("time_start") or "")
    return filtered


def _format_daily_schedule(
    group_name: str,
    target_date: date,
    lessons: list[dict],
    homeworks: list[dict],
) -> str:
    """Форматирует текст утреннего расписания на день вместе с ДЗ."""
    weekday_name = WEEKDAYS_RU[target_date.weekday()]
    date_iso = target_date.strftime("%Y-%m-%d")
    header = (
        f"📅 <b>Расписание на {target_date.strftime('%d.%m.%Y')} ({weekday_name})</b>\n"
        f"Группа: <b>{html.escape(group_name)}</b>"
    )

    if not lessons:
        return f"{header}\n\nСегодня занятий нет! 🎉"

    blocks = [header]
    for idx, les in enumerate(lessons, start=1):
        time_start = les.get("time_start") or ""
        time_end = les.get("time_end") or ""
        subject = les.get("subject") or "Без названия"
        les_type = les.get("type") or ""
        teacher = les.get("teacher") or "—"
        room = les.get("room") or "—"

        hw = next(
            (
                h for h in homeworks
                if h.get("lesson_date") == date_iso
                and h.get("subject") == subject
                and (h.get("teacher") or "") == (les.get("teacher") or "")
            ),
            None,
        )

        line = (
            f"{idx}. ⏰ <b>{html.escape(time_start)}–{html.escape(time_end)}</b> — "
            f"<b>{html.escape(subject)}</b>"
        )
        if les_type:
            line += f" <i>({html.escape(les_type)})</i>"
        line += f"\n    👨‍🏫 {html.escape(teacher)} | 📍 {html.escape(room)}"

        if hw:
            desc = html.escape(hw.get("description") or "")
            line += f"\n    📌 <b>ДЗ:</b> <i>{desc}</i>"

        blocks.append(line)

    return "\n\n".join(blocks)


async def _get_week_schedule_cached(
    redis_client: redis.Redis,
    group_name: str,
    target_date: date,
) -> list[dict]:
    """Загружает расписание на неделю из Redis-кэша или с сайта вуза (с резервным stale-кэшем)."""
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    start_str = monday.strftime("%Y.%m.%d")
    end_str = sunday.strftime("%Y.%m.%d")

    cache_key = f"sched:{group_name}:{start_str}:{end_str}"
    cached_raw = await redis_client.get(cache_key)
    if cached_raw:
        return json.loads(cached_raw)

    last_exc = None
    for attempt in range(2):
        try:
            raw_schedule = await fetch_schedule_from_ruz(group_name, start_str, end_str)
            await redis_client.setex(cache_key, 900, json.dumps(raw_schedule))
            await redis_client.setex(f"stale:{cache_key}", 86400, json.dumps(raw_schedule))
            return raw_schedule
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(3)

    logging.warning("Не удалось обновить расписание для %s с сайта вуза: %s", group_name, last_exc)
    stale_raw = await redis_client.get(f"stale:{cache_key}")
    if stale_raw:
        return json.loads(stale_raw)

    return []


async def send_daily_schedules(bot: Bot, only_user_id: int | None = None):
    """Рассылает актуальное расписание на текущий день всем пользователям кроме учителей."""
    tz = ZoneInfo("Europe/Moscow")
    today = datetime.now(tz).date()
    today_iso = today.strftime("%Y-%m-%d")

    pool = get_pool()
    async with pool.acquire() as conn:
        if only_user_id is not None:
            rows = await conn.fetch(
                """
                SELECT user_id, group_name, eng_teacher, chin_teacher
                FROM users
                WHERE user_id = $1
                  AND role = ANY($2::text[])
                  AND group_name IS NOT NULL
                  AND group_name <> ''
                """,
                only_user_id,
                list(STUDENT_DIGEST_ROLES),
            )
        else:
            rows = await conn.fetch(
                """
                SELECT user_id, group_name, eng_teacher, chin_teacher
                FROM users
                WHERE is_approved = TRUE
                  AND COALESCE(is_banned, FALSE) = FALSE
                  AND role = ANY($1::text[])
                  AND group_name IS NOT NULL
                  AND group_name <> ''
                """,
                list(STUDENT_DIGEST_ROLES),
            )

    if not rows:
        return

    users_by_group: dict[str, list[dict]] = {}
    for row in rows:
        u = dict(row)
        users_by_group.setdefault(u["group_name"], []).append(u)

    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        for group_name, group_users in users_by_group.items():
            try:
                raw_schedule = await _get_week_schedule_cached(redis_client, group_name, today)
                homeworks = await hw_service.list_homework(group_name, today_iso, today_iso)
            except Exception:
                logging.exception("Ошибка подготовки ночной рассылки для группы %s", group_name)
                continue

            for user in group_users:
                try:
                    personal_lessons = _filter_lessons_for_student(raw_schedule, today_iso, user)
                    text = _format_daily_schedule(group_name, today, personal_lessons, homeworks)
                    await bot.send_message(user["user_id"], text)
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logging.warning("Не удалось отправить расписание пользователю %s: %s", user["user_id"], exc)
    finally:
        await redis_client.aclose()


async def midnight_schedule_worker(bot: Bot):
    """Фоновая задача: ежедневно ровно в 00:00 (МСК) рассылает расписание на наступивший день."""
    tz = ZoneInfo("Europe/Moscow")
    while True:
        now = datetime.now(tz)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        sleep_seconds = (next_midnight - now).total_seconds()
        logging.info("Следующая рассылка расписания запланирована на %s (через %.0f сек.)", next_midnight, sleep_seconds)

        await asyncio.sleep(sleep_seconds)

        try:
            logging.info("Запуск ежедневной рассылки расписания в 00:00...")
            await send_daily_schedules(bot)
            logging.info("Ежедневная рассылка расписания завершена.")
        except Exception:
            logging.exception("Критическая ошибка в midnight_schedule_worker")


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
        if isinstance(event.exception, (TelegramNetworkError, TelegramBadRequest)):
            logging.warning("Временная ошибка Telegram API: %s", event.exception)
            return True
        logging.exception("Необработанная ошибка", exc_info=event.exception)
        return True

    @dp.message(Command("test_digest"))
    async def cmd_test_digest(message: Message, db_user: dict):
        """Тестовый запуск утренней рассылки лично для администратора."""
        if db_user.get("role") not in ("admin", "owner"):
            return
        await send_daily_schedules(bot, only_user_id=db_user["user_id"])

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.include_router(admin_handlers.router)
    dp.include_router(teacher_handlers.router)
    dp.include_router(common_handlers.router)
    dp.include_router(user_handlers.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await setup_bot_ui(bot)

    digest_task = asyncio.create_task(midnight_schedule_worker(bot))

    logging.info("Bot started")
    try:
        await dp.start_polling(bot, polling_timeout=8)
    finally:
        digest_task.cancel()
        await storage.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())