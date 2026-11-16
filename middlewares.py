from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from services.users import get_or_create_user
from services.bans import get_active_ban, unban_user

class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: Dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        db_user = await get_or_create_user(tg_user.id, tg_user.username, tg_user.full_name)

        # 1. Проверка на бан
        if db_user["is_banned"]:
            # ... (ваш старый код бана) ...
            return

        # 2. Проверка на одобрение (модерацию)
        if not db_user["is_approved"] and db_user["role"] != "owner":
            # Пропускаем только команду /start, чтобы человек увидел сообщение
            if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                pass
            else:
                if isinstance(event, Message):
                    await event.answer("⏳ Ваша заявка на рассмотрении. Пожалуйста, подождите.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Ваша заявка на рассмотрении.", show_alert=True)
                return

        data["db_user"] = db_user
        return await handler(event, data)