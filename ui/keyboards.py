from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ROLES, TEACHER_ROLES


def main_menu(role: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Расписание", callback_data="menu:schedule")

    if role in ADMIN_ROLES:
        kb.button(text="👥 Пользователи", callback_data="menu:users")
        kb.button(text="🚫 Баны", callback_data="menu:bans")
        kb.button(text="📜 Логи", callback_data="menu:logs")

    kb.adjust(2, 1, 1, 2)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    return kb.as_markup()


def user_card(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Роль", callback_data=f"usr:role:{user_id}")
    kb.button(text="📁 Группа", callback_data=f"usr:group:{user_id}")  # <--- КНОПКА ГРУППЫ ЗДЕСЬ
    if is_banned:
        kb.button(text="✅ Разбанить", callback_data=f"usr:unban:{user_id}")
    else:
        kb.button(text="🚫 Забанить", callback_data=f"usr:ban:{user_id}")
    kb.button(text="⬅️ К списку", callback_data="menu:users")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def roles_keyboard(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in ("student", "teacher", "admin"):
        kb.button(text=r, callback_data=f"usr:setrole:{user_id}:{r}")
    kb.button(text="⬅️ Отмена", callback_data=f"usr:card:{user_id}")
    kb.adjust(3, 1)
    return kb.as_markup()


def ban_duration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ 1 день", callback_data=f"usr:doBan:{user_id}:1")
    kb.button(text="📅 7 дней", callback_data=f"usr:doBan:{user_id}:7")
    kb.button(text="🔒 Навсегда", callback_data=f"usr:doBan:{user_id}:0")
    kb.button(text="⬅️ Отмена", callback_data=f"usr:card:{user_id}")
    kb.adjust(3, 1)
    return kb.as_markup()

def schedule_nav() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Пн", callback_data="sched:day:0")
    kb.button(text="Вт", callback_data="sched:day:1")
    kb.button(text="Ср", callback_data="sched:day:2")
    kb.button(text="Чт", callback_data="sched:day:3")
    kb.button(text="Пт", callback_data="sched:day:4")
    kb.button(text="Сб", callback_data="sched:day:5")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(4, 3, 1) # 5 дней в ряд, кнопка меню снизу
    return kb.as_markup()
def persistent_menu() -> ReplyKeyboardMarkup:
    """Клавиатура, которая всегда висит внизу экрана."""
    kb = [
        [KeyboardButton(text="🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)