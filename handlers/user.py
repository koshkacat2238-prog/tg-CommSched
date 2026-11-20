from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import WEBAPP_URL

router = Router()


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, db_user: dict):
    """Быстрый вызов кнопки расписания по команде /schedule."""
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
    # lessons = await parser.get_schedule_for_date(group_name, tomorrow)
    # homeworks = await homework.get_hw_for_date(group_name, tomorrow)
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