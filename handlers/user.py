from urllib.parse import quote
from aiogram import F, Router
from aiogram.types import CallbackQuery, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WEBAPP_URL

router = Router()


@router.callback_query(F.data == "menu:schedule")
async def open_webapp(cb: CallbackQuery, db_user: dict):
    if not db_user["group_name"]:
        return await cb.answer("Группа не назначена. Выберите группу в меню.", show_alert=True)

    encoded_group = quote(db_user["group_name"])
    webapp_url = f"{WEBAPP_URL}/?group={encoded_group}"

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📅 Открыть расписание",
        web_app=WebAppInfo(url=webapp_url)
    )
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1)

    await cb.message.edit_text(
        "Нажмите кнопку ниже, чтобы открыть интерактивное расписание:",
        reply_markup=kb.as_markup()
    )
    await cb.answer()