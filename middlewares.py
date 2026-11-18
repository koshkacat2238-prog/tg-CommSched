from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from services.users import get_or_create_user
from services.bans import get_active_ban, unban_user


class AuthMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:

        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        # Получаем или создаем пользователя
        db_user = await get_or_create_user(tg_user.id, tg_user.username, tg_user.full_name)

        # ==========================================
        # 1. ПРОВЕРКА НА БАН (С автоснятием)
        # ==========================================
        if db_user["is_banned"]:
            ban = await get_active_ban(tg_user.id)
            expired = ban and ban["expires_at"] and ban["expires_at"] <= datetime.now(timezone.utc)

            if expired:
                # Если срок бана истек, снимаем его на лету
                await unban_user(tg_user.id, None, "auto-expired")
                db_user = await get_or_create_user(tg_user.id, tg_user.username, tg_user.full_name)
            elif ban:
                # Если бан активен, сообщаем причину и блокируем
                text = f"🚫 Доступ заблокирован.\nПричина: {ban['reason']}"
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer("Вы заблокированы", show_alert=True)
                return  # СТОП. Дальше не пускаем.

        # ==========================================
        # 2. ПРОВЕРКА НА СОГЛАСИЕ С ОБРАБОТКОЙ ПД
        # ==========================================
        if not db_user["is_agreed"] and db_user["role"] != "owner":
            is_start = isinstance(event, Message) and event.text and event.text.startswith("/start")
            is_agree_btn = isinstance(event, CallbackQuery) and event.data == "agree_privacy"

            if not (is_start or is_agree_btn):
                if isinstance(event, Message):
                    await event.answer("⚠️ Пожалуйста, дайте согласие на обработку данных (нажмите /start).")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Дайте согласие на обработку данных", show_alert=True)
                return  # СТОП. Дальше не пускаем.

        # ==========================================
        # 3. ПРОВЕРКА НА ОДОБРЕНИЕ (МОДЕРАЦИЯ)
        # ==========================================
        if not db_user["is_approved"] and db_user["role"] != "owner":
            # Пропускаем только команду /start, чтобы человек увидел экран ожидания
            is_start = isinstance(event, Message) and event.text and event.text.startswith("/start")

            if not is_start:
                if isinstance(event, Message):
                    await event.answer("⏳ Ваша заявка на рассмотрении. Пожалуйста, подождите.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Заявка на рассмотрении", show_alert=True)
                return  # СТОП. Дальше не пускаем.

        # Если все проверки пройдены, передаем данные в хендлер
        data["db_user"] = db_user
        return await handler(event, data)