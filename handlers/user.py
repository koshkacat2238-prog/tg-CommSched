import html
import logging
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
    group_name = db_user.get("group_name")
    if not isinstance(group_name, str) or not group_name:
        await message.answer("Сначала выберите группу в главном меню (/start).")
        return

    encoded_group = quote(group_name)
    webapp_url = f"{WEBAPP_URL}/?group={encoded_group}"

    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Открыть Web App", web_app=WebAppInfo(url=webapp_url))
    kb.button(text="📝 Пары на завтра (текстом)", callback_data="schedule:tomorrow_text")
    kb.adjust(1)

    await message.answer(
        f"Расписание для группы <b>{html.escape(group_name)}</b>:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "schedule:tomorrow_text")
async def tomorrow_text_fallback(cb: CallbackQuery, db_user: dict):
    """Текстовый запасной вариант расписания на завтра при слабом интернете."""
    group_name = db_user.get("group_name")
    if not isinstance(group_name, str) or not group_name:
        await cb.answer("Группа не назначена.", show_alert=True)
        return

    tomorrow = (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(days=1)).date()
    date_dot = tomorrow.strftime("%Y.%m.%d")
    date_iso = tomorrow.strftime("%Y-%m-%d")

    try:
        raw_lessons = await parser.fetch_schedule_from_ruz(group_name, date_dot, date_dot)
        homeworks = await homework.list_homework(group_name, date_iso, date_iso)
    except Exception:
        logging.exception("Ошибка получения расписания на завтра для группы %s", group_name)
        await cb.answer("Сайт расписания временно недоступен.", show_alert=True)
        return

    eng_t = (db_user.get("eng_teacher") or "").lower()
    chin_t = (db_user.get("chin_teacher") or "").lower()
    teacher_subj = (db_user.get("teacher_subject") or "").lower()

    lessons = []
    for les in raw_lessons:
        if les.get("date") != date_iso:
            continue
        subj = (les.get("subject") or "").lower()
        teacher = (les.get("teacher") or "").lower()

        if teacher_subj and teacher_subj not in subj:
            continue
        if ("иностранный" in subj or "английский" in subj) and eng_t and eng_t not in teacher:
            continue
        if "китайский" in subj and chin_t and chin_t not in teacher:
            continue

        lessons.append(les)

    lines = [f"📆 <b>Расписание на {tomorrow.strftime('%d.%m.%Y')} ({html.escape(group_name)})</b>\n"]

    if not lessons:
        lines.append("На завтра занятий нет. 🎉")
    else:
        for les in lessons:
            time_str = f"{les.get('time_start', '')}–{les.get('time_end', '')}"
            subject = les.get("subject") or "Без названия"
            les_type = les.get("type") or ""
            teacher = les.get("teacher") or "—"
            room = les.get("room") or "—"

            hw = next(
                (
                    h for h in homeworks
                    if h.get("lesson_date") == date_iso
                    and h.get("subject") == les.get("subject")
                    and (h.get("teacher") or "") == (les.get("teacher") or "")
                ),
                None
            )

            block = (
                f"⏰ <b>{html.escape(time_str)}</b> — <b>{html.escape(subject)}</b> "
                f"({html.escape(les_type)})\n"
                f"👨‍🏫 {html.escape(teacher)} | 📍 {html.escape(room)}"
            )
            if hw:
                block += f"\n📌 <i>ДЗ: {html.escape(hw.get('description', ''))}</i>"
            lines.append(block)

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В главное меню", callback_data="menu:main")

    if isinstance(cb.message, Message):
        try:
            await cb.message.edit_text("\n\n".join(lines), reply_markup=kb.as_markup())
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
    return