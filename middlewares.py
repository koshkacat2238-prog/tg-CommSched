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

        if db_user["is_banned"]:
            ban = await get_active_ban(tg_user.id)
            expired = ban and ban["expires_at"] and ban["expires_at"] <= datetime.now(timezone.utc)

            if expired:
                await unban_user(tg_user.id, None, "auto-expired")
                db_user = await get_or_create_user(tg_user.id, tg_user.username, tg_user.full_name)
            elif ban:
                text = f"🚫 Доступ заблокирован.\nПричина: {ban['reason']}"
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer("Вы заблокированы", show_alert=True)
                return

        data["db_user"] = db_user
        return await handler(event, data)