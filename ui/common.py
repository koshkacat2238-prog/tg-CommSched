#заглушка для /start
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from ui import keyboards, texts

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, db_user: dict):
    await message.answer(texts.WELCOME.format(name=db_user['full_name'], role=db_user['role']), reply_markup=keyboards.main_menu(db_user["role"]))

@router.callback_query(lambda c: c.data == "menu:main")
async def menu_main(cb: CallbackQuery, db_user: dict):
    await cb.message.edit_text(texts.MENU_MAIN, reply_markup=keyboards.main_menu(db_user["role"]))