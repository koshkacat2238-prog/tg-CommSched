from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import OWNER_ID
from ui import keyboards, texts

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, db_user: dict, bot: Bot):
    # Логика модерации (из прошлых шагов)
    if not db_user["is_approved"] and db_user["role"] != "owner":
        await message.answer("⏳ <b>Заявка отправлена!</b>\nОжидайте, пока администратор одобрит ваш доступ.")

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Принять", callback_data=f"mod:approve:{db_user['user_id']}")
        kb.button(text="❌ Отклонить", callback_data=f"mod:reject:{db_user['user_id']}")

        try:
            await bot.send_message(
                OWNER_ID,
                f"🔔 <b>Новая заявка!</b>\n\n"
                f"👤 {db_user['full_name']}\n"
                f"🆔 <code>{db_user['user_id']}</code>",
                reply_markup=kb.as_markup()
            )
        except Exception:
            pass
        return

    # Показываем меню
    await message.answer(
        texts.WELCOME.format(
            name=db_user['full_name'],
            role=db_user['role'],
            group=db_user['group_name'] or "не назначена"
        ),
        reply_markup=keyboards.persistent_menu()
    )
    await message.answer(
        texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


@router.message(F.text == "🏠 Главное меню")
async def reply_menu(message: Message, db_user: dict):
    await message.answer(
        texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


@router.callback_query(lambda c: c.data == "menu:main")
async def menu_main(cb: CallbackQuery, db_user: dict):
    await cb.message.edit_text(
        texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


# НОВЫЙ ОБРАБОТЧИК ДЛЯ БАГОВ
@router.callback_query(F.data == "menu:report")
async def report_bug(cb: CallbackQuery):
    await cb.message.answer("🐞 Нашли баг или есть предложение по улучшению?\nНапишите разработчику: 2603463@edu.fa.ru")
    await cb.answer()