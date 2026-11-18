from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ROLES, AVAILABLE_GROUPS


def main_menu(role: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Расписание", callback_data="menu:schedule")
    kb.button(text="📁 Выбрать группу", callback_data="menu:choose_group")

    if role in ADMIN_ROLES:
        kb.button(text="👥 Пользователи", callback_data="menu:users")
        kb.button(text="🚫 Баны", callback_data="menu:bans")
        kb.button(text="📜 Логи", callback_data="menu:logs")
        kb.button(text="⏳ Заявки", callback_data="menu:pending")
    kb.button(text="🐞 Сообщить об ошибке", callback_data="menu:report")

    if role in ADMIN_ROLES:
        kb.adjust(2, 2, 2, 1)
    else:
        kb.adjust(2, 1)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    return kb.as_markup()


def user_card(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Роль", callback_data=f"usr:role:{user_id}")
    kb.button(text="📁 Группа", callback_data=f"usr:group:{user_id}")
    if is_banned:
        kb.button(text="✅ Разбанить", callback_data=f"usr:unban:{user_id}")
    else:
        kb.button(text="🚫 Забанить", callback_data=f"usr:ban:{user_id}")
    kb.button(text="⬅️ К списку", callback_data="menu:users")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def roles_keyboard(user_id: int, actor_role: str = "admin") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    available_roles = ("student", "teacher", "admin") if actor_role == "owner" else ("student", "teacher")
    for r in available_roles:
        kb.button(text=r, callback_data=f"usr:setrole:{user_id}:{r}")
    kb.button(text="⬅️ Отмена", callback_data=f"usr:card:{user_id}")
    kb.adjust(len(available_roles), 1)
    return kb.as_markup()


def ban_duration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ 1 день", callback_data=f"usr:doBan:{user_id}:1")
    kb.button(text="📅 7 дней", callback_data=f"usr:doBan:{user_id}:7")
    kb.button(text="🔒 Навсегда", callback_data=f"usr:doBan:{user_id}:0")
    kb.button(text="⬅️ Отмена", callback_data=f"usr:card:{user_id}")
    kb.adjust(3, 1)
    return kb.as_markup()


def persistent_menu() -> ReplyKeyboardMarkup:
    kb = [[KeyboardButton(text="🏠 Главное меню")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)


def select_group_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in AVAILABLE_GROUPS:
        kb.button(text=f"📁 {g}", callback_data=f"usr:my_grp:{g}")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()