import html
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

        db_user = await get_or_create_user(tg_user.id, tg_user.username, tg_user.full_name)

        # 1. ПРОВЕРКА НА БАН (С автоснятием)
        if db_user["is_banned"]:
            ban = await get_active_ban(tg_user.id)
            expired = ban and ban["expires_at"] and ban["expires_at"] <= datetime.now(timezone.utc)

            if expired:
                await unban_user(tg_user.id, None, "auto-expired")
                db_user = await get_or_create_user(tg_user.id, tg_user.username, tg_user.full_name)
            elif ban:
                safe_reason = html.escape(ban["reason"] or "Не указана")
                text = f"🚫 Доступ заблокирован.\nПричина: {safe_reason}"
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer("Вы заблокированы", show_alert=True)
                return

        is_start = isinstance(event, Message) and bool(event.text and event.text.startswith("/start"))
        is_agree_btn = isinstance(event, CallbackQuery) and event.data == "agree_privacy"

        # 2. ПРОВЕРКА НА СОГЛАСИЕ С ОБРАБОТКОЙ ПД
        if not db_user["is_agreed"] and db_user["role"] != "owner":
            if not (is_start or is_agree_btn):
                if isinstance(event, Message):
                    await event.answer("⚠️ Пожалуйста, дайте согласие на обработку данных (нажмите /start).")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Дайте согласие на обработку данных", show_alert=True)
                return
            # Пропускаем /start и нажатие кнопки согласия сразу в хендлер
            data["db_user"] = db_user
            return await handler(event, data)

        # 3. ПРОВЕРКА НА ОДОБРЕНИЕ (МОДЕРАЦИЯ)
        if not db_user["is_approved"] and db_user["role"] != "owner":
            if not (is_start or is_agree_btn):
                if isinstance(event, Message):
                    await event.answer("⏳ Ваша заявка на рассмотрении. Пожалуйста, подождите.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Заявка на рассмотрении", show_alert=True)
                return

        data["db_user"] = db_user
        return await handler(event, data)