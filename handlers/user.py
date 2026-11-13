from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db

router = Router()


@router.callback_query(F.data == "menu:schedule")
async def open_webapp(cb: CallbackQuery, db_user: dict):
    if not db_user["group_name"]:
        return await cb.answer("Группа не назначена. Обратитесь к администратору.", show_alert=True)

    # ВСТАВЬТЕ СЮДА ВАШ URL (пока тестируете локально - ссылку из ngrok)
    webapp_url = f"https://sixtieth-parsley-singular.ngrok-free.dev/?group={db_user['group_name']}"

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📅 Открыть расписание",
        web_app=WebAppInfo(url=webapp_url)
    )

    await cb.message.edit_text(
        "Нажмите кнопку ниже, чтобы открыть интерактивное расписание:",
        reply_markup=kb.as_markup()
    )

    async def get_groups_with_users() -> list[str]:
        """Возвращает список уникальных групп, у которых есть участники."""
        rows = await db().fetch(
            "SELECT DISTINCT group_name FROM users WHERE group_name IS NOT NULL AND group_name != '' ORDER BY group_name"
        )
        return [r['group_name'] for r in rows]

    async def list_users_by_group(group_name: str) -> list[dict]:
        """Возвращает список пользователей из конкретной группы."""
        if group_name == "None":  # Специальный маркер для тех, у кого нет группы
            rows = await db().fetch(
                "SELECT * FROM users WHERE group_name IS NULL OR group_name = '' ORDER BY created_at DESC")
        else:
            rows = await db().fetch("SELECT * FROM users WHERE group_name = $1 ORDER BY created_at DESC", group_name)
        return [dict(r) for r in rows]