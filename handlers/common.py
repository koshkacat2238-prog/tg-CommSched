from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import OWNER_ID, WEBAPP_URL
from ui import keyboards, texts
from services import users
from database import db

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, db_user: dict, bot: Bot):
    # 1. Проверка согласия
    if not db_user["is_agreed"] and db_user["role"] != "owner":
        kb = InlineKeyboardBuilder()
        kb.button(text="📄 Прочитать политику", url=f"{WEBAPP_URL}/privacy")
        kb.button(text="✅ Согласен", callback_data="agree_privacy")
        kb.adjust(1)

        # ВОТ ЗДЕСЬ МЫ ОТПРАВЛЯЕМ СООБЩЕНИЕ
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Для использования бота нам необходимо ваше согласие на обработку персональных данных. "
            "Пожалуйста, ознакомьтесь с политикой и подтвердите согласие:",
            reply_markup=kb.as_markup()
        )
        return  # <--- ВАЖНО: останавливаем функцию, чтобы бот не показывал меню

    # 2. Логика модерации (из прошлых шагов)
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

    # 3. Показываем меню
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


# НОВЫЙ ОБРАБОТЧИК: Согласие
@router.callback_query(F.data == "agree_privacy")
async def handle_agree_privacy(cb: CallbackQuery, db_user: dict, bot: Bot):
    await users.agree_to_privacy(db_user["user_id"])
    await cb.answer("Согласие принято")

    if isinstance(cb.message, Message):
        try:
            await cb.message.delete()
        except Exception:
            pass

    # Получаем обновленные данные
    updated_user = await users.get_user(db_user["user_id"])
    if not updated_user:  # <--- Добавили защиту
        return

    # Вызываем старт, чтобы показать меню или экран модерации
    await cmd_start(cb.message, updated_user, bot)

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

async def get_students_by_group(group_name: str) -> list[dict]:
    """Возвращает всех одобренных студентов конкретной группы."""
    rows = await db().fetch(
        "SELECT user_id FROM users WHERE group_name = $1 AND is_approved = TRUE AND is_banned = FALSE",
        group_name
    )
    return [dict(r) for r in rows]


@router.callback_query(F.data == "menu:choose_group")
async def choose_group_prompt(cb: CallbackQuery):
    await cb.message.edit_text(
        "Выберите вашу учебную группу из списка ниже:",
        reply_markup=keyboards.select_group_keyboard()
    )
    await cb.answer()


@router.callback_query(F.data.startswith("usr:my_grp:"))
async def set_my_group(cb: CallbackQuery, db_user: dict):
    # Достаем группу из callback_data (текст после 3-го двоеточия)
    new_group = cb.data.split(":")[2]

    # Сохраняем в базу (используем функцию set_group, передавая ID пользователя как actor)
    await users.set_group(db_user["user_id"], new_group, db_user["user_id"])

    await cb.answer(f"✅ Ваша группа: {new_group}", show_alert=True)

    # Возвращаем пользователя в главное меню
    await cb.message.edit_text(
        texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )