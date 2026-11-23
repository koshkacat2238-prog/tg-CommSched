import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import AVAILABLE_GROUPS, OWNER_ID, WEBAPP_URL
from services import users
from ui import keyboards, texts

router = Router()

ROLE_LABELS = {
    "student": "Студент",
    "headman": "Староста",
    "teacher": "Учитель",
    "admin": "Администратор",
    "owner": "Владелец",
}


@router.message(Command("start"))
async def cmd_start(message: Message, db_user: dict):
    # 1. Проверка согласия
    if not db_user["is_agreed"] and db_user["role"] != "owner":
        kb = InlineKeyboardBuilder()
        kb.button(text="📄 Прочитать политику", url=f"{WEBAPP_URL}/privacy")
        kb.button(text="✅ Согласен", callback_data="agree_privacy")
        kb.adjust(1)

        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Для использования бота нам необходимо ваше согласие на обработку персональных данных. "
            "Пожалуйста, ознакомьтесь с политикой и подтвердите согласие:",
            reply_markup=kb.as_markup()
        )
        return

    # 2. Экран ожидания модерации
    if not db_user["is_approved"] and db_user["role"] != "owner":
        await message.answer("⏳ <b>Ваша заявка на рассмотрении!</b>\nОжидайте, пока администратор одобрит ваш доступ.")
        return

    # 3. Показываем главное меню
    role_display = ROLE_LABELS.get(db_user["role"], db_user["role"])
    await message.answer(
        texts.WELCOME.format(
            name=html.escape(db_user["full_name"]),
            role=html.escape(role_display),
            group=html.escape(db_user["group_name"] or "не назначена")
        ),
        reply_markup=keyboards.persistent_menu()
    )
    await message.answer(
        texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


@router.callback_query(F.data == "agree_privacy")
async def handle_agree_privacy(cb: CallbackQuery, db_user: dict, bot: Bot):
    already_agreed = db_user["is_agreed"]
    await users.agree_to_privacy(db_user["user_id"])
    await cb.answer("Согласие принято")

    if isinstance(cb.message, Message):
        try:
            await cb.message.delete()
        except Exception:
            pass

    updated_user = await users.get_user(db_user["user_id"])
    if not updated_user:
        return

    # Отправляем уведомление владельцу только один раз — при первом согласии
    if not already_agreed and not updated_user["is_approved"] and updated_user["role"] != "owner":
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Принять", callback_data=f"mod:approve:{updated_user['user_id']}")
        kb.button(text="❌ Отклонить", callback_data=f"mod:reject:{updated_user['user_id']}")
        try:
            await bot.send_message(
                OWNER_ID,
                f"🔔 <b>Новая заявка!</b>\n\n"
                f"👤 {html.escape(updated_user['full_name'])}\n"
                f"🆔 <code>{updated_user['user_id']}</code>",
                reply_markup=kb.as_markup()
            )
        except Exception:
            pass

    if isinstance(cb.message, Message):
        await cmd_start(cb.message, updated_user)


@router.message(F.text == "🏠 Главное меню")
async def reply_menu(message: Message, db_user: dict):
    await message.answer(
        texts.MENU_MAIN,
        reply_markup=keyboards.main_menu(db_user["role"])
    )


@router.callback_query(F.data == "menu:main")
async def menu_main(cb: CallbackQuery, db_user: dict):
    if isinstance(cb.message, Message):
        try:
            await cb.message.edit_text(
                texts.MENU_MAIN,
                reply_markup=keyboards.main_menu(db_user["role"])
            )
        except TelegramBadRequest:
            pass
    await cb.answer()


@router.callback_query(F.data == "menu:report")
async def report_bug(cb: CallbackQuery):
    if isinstance(cb.message, Message):
        await cb.message.answer("🐞 Нашли баг или есть предложение по улучшению?\nНапишите разработчику: 2603463@edu.fa.ru")
    await cb.answer()


@router.callback_query(F.data == "menu:choose_group")
async def choose_group_prompt(cb: CallbackQuery, db_user: dict):
    # Староста (headman) и студенты могут менять группу свободно; блокируем только закреплённых учителей
    if db_user.get("role") == "teacher" and db_user.get("teacher_subject"):
        await cb.answer(
            f"Ваша учётная запись учителя закреплена за группой {db_user.get('group_name')}.",
            show_alert=True
        )
        return

    kb = InlineKeyboardBuilder()
    for grp in AVAILABLE_GROUPS:
        kb.button(text=grp, callback_data=f"usr:my_grp:{grp}")
    kb.button(text="⬅️ Назад", callback_data="menu:main")
    kb.adjust(2)

    if isinstance(cb.message, Message):
        try:
            await cb.message.edit_text(
                "📁 <b>Выберите вашу учебную группу:</b>",
                reply_markup=kb.as_markup()
            )
        except TelegramBadRequest:
            pass
    await cb.answer()


@router.callback_query(F.data.startswith("usr:my_grp:"))
async def set_my_group(cb: CallbackQuery, db_user: dict):
    if db_user.get("role") == "teacher" and db_user.get("teacher_subject"):
        await cb.answer("Вы не можете сменить закреплённую группу.", show_alert=True)
        return

    new_group = cb.data.split(":", 2)[2]
    if new_group not in AVAILABLE_GROUPS:
        await cb.answer("Недопустимая группа", show_alert=True)
        return

    await users.set_group(db_user["user_id"], new_group, db_user["user_id"])
    await cb.answer(f"✅ Ваша группа: {new_group}", show_alert=True)

    if isinstance(cb.message, Message):
        try:
            await cb.message.edit_text(
                texts.MENU_MAIN,
                reply_markup=keyboards.main_menu(db_user["role"])
            )
        except TelegramBadRequest:
            pass