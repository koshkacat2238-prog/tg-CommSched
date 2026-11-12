from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ui import keyboards, texts

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, db_user: dict):
    """
    Обработчик команды /start.
    Middleware уже передал нам db_user, поэтому мы знаем роль и имя человека.
    """
    # Формируем приветствие (текст берем из texts.py, подставляя имя и роль)
    welcome_text = texts.WELCOME.format(
        name=db_user["full_name"],
        role=db_user["role"],
        group=db_user["group_name"] or "не назначена"
    )

    await message.answer(
        text=welcome_text,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: dict):
    """Обработчик команды /menu для вызова главного меню."""
    await message.answer(
        text=texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


@router.callback_query(F.data == "menu:main")
async def menu_main(cb: CallbackQuery, db_user: dict):
    """
    Обработчик кнопки '⬅️ В меню'.
    Мы не отправляем новое сообщение, а редактируем старое (чтобы не засорять чат).
    """
    await cb.message.edit_text(
        text=texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )
    # Обязательно отвечаем на callback, чтобы кнопка перестала "крутиться"
    await cb.answer()