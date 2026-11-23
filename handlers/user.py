from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import get_pool
from services import homework, parser

from config import WEBAPP_URL

router = Router()


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, db_user: dict):
    """Быстрый вызов расписания по команде /schedule."""
    if not db_user.get("group_name"):
        return await message.answer("Сначала выберите группу в главном меню (/start).")

    encoded_group = quote(db_user["group_name"])
    webapp_url = f"{WEBAPP_URL}/?group={encoded_group}"

    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Открыть Web App", web_app=WebAppInfo(url=webapp_url))
    kb.button(text="📝 Пары на завтра (текстом)", callback_data="schedule:tomorrow_text")
    kb.adjust(1)

    await message.answer(
        f"Расписание для группы <b>{db_user['group_name']}</b>:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "schedule:tomorrow_text")
async def tomorrow_text_fallback(cb: CallbackQuery, db_user: dict):
    """Текстовый запасной вариант расписания при слабом мобильном интернете."""
    group_name = db_user.get("group_name")
    if not group_name:
        return await cb.answer("Группа не назначена.", show_alert=True)

    tomorrow = (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(days=1)).date()

    # Подставьте здесь вызов вашего парсера/сервиса ДЗ для получения пар на tomorrow:
    lessons = await parser.get_schedule_for_date(group_name, tomorrow)
    homeworks = await homework.get_hw_for_date(group_name, tomorrow)
    schedule_text = (
        f"📆 <b>Расписание на {tomorrow.strftime('%d.%m.%Y')} ({group_name})</b>\n\n"
        f"<i>Подключите сюда вывод из services/parser.py и services/homework.py</i>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="menu:schedule")

    try:
        await cb.message.edit_text(schedule_text, reply_markup=kb.as_markup())
    except TelegramBadRequest:
        pass
    await cb.answer()


@router.message(Command("bind_teacher"))
async def bind_teacher_cmd(message: Message, db_user: dict):
    """Привязывает преподавателя к одной группе и предмету: /bind_teacher <user_id> <группа> <предмет>"""
    if db_user.get("role") not in ("admin", "owner"):
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4:
        return await message.answer(
            "Использование:\n<code>/bind_teacher ID_пользователя Группа Предмет</code>\n\n"
            "Пример:\n<code>/bind_teacher 123456789 МЭиТ26-8 Китайский</code>"
        )

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.answer("ID пользователя должен быть числом.")

    group_name = parts[2].strip()
    subject = parts[3].strip()

    pool = get_pool()
    async with pool.acquire() as conn:
        updated = await conn.fetchrow(
            """
            UPDATE users
            SET role = 'teacher',
                is_approved = TRUE,
                group_name = $2,
                teacher_subject = $3
            WHERE user_id = $1
            RETURNING user_id
            """,
            target_id,
            group_name,
            subject,
        )

    if not updated:
        return await message.answer("Пользователь с таким ID не найден в базе (он должен сначала нажать /start).")

    await message.answer(
        f"✅ Преподаватель <code>{target_id}</code> привязан:\n"
        f"• Группа: <b>{group_name}</b>\n"
        f"• Предмет: <b>{subject}</b>"
    )