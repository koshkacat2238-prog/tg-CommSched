from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ROLES, TEACHER_ROLES

def main_menu(role: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Пользователи", callback_data="menu:users")
    kb.button(text="🚫 Баны", callback_data="menu:bans")
    kb.button(text="📜 Логи", callback_data="menu:logs")
    return kb.as_markup()

def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    return kb.as_markup()

def user_card(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Роль", callback_data=f"usr:role:{user_id}")
    if is_banned:
        kb.button(text="✅ Разбанить", callback_data=f"usr:unban:{user_id}")
    else:
        kb.button(text="🚫 Забанить", callback_data=f"usr:ban:{user_id}")
    kb.button(text="⬅️ Назад", callback_data="menu:users")
    kb.adjust(2, 1)
    return kb.as_markup()

def roles_keyboard(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in ("student", "teacher", "admin"): kb.button(text=r, callback_data=f"usr:setrole:{user_id}:{r}")
    kb.button(text="⬅️ Отмена", callback_data=f"usr:card:{user_id}")
    return kb.as_markup()

def ban_duration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="1 день", callback_data=f"usr:doBan:{user_id}:1")
    kb.button(text="Навсегда", callback_data=f"usr:doBan:{user_id}:0")
    return kb.as_markup()