from datetime import datetime, timedelta, timezone
from database import db
from services import audit

async def get_active_ban(user_id: int) -> dict | None:
    row = await db().fetchrow("SELECT * FROM bans WHERE user_id=$1 AND is_active=TRUE ORDER BY id DESC LIMIT 1", user_id)
    return dict(row) if row else None

async def ban_user(user_id: int, admin_id: int, reason: str, days: int | None):
    expires = (datetime.now(timezone.utc) + timedelta(days=days)) if days else None
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("INSERT INTO bans(user_id, admin_id, reason, expires_at) VALUES($1,$2,$3,$4)", user_id, admin_id, reason, expires)
            await conn.execute("UPDATE users SET is_banned=TRUE WHERE user_id=$1", user_id)
            await audit.log(admin_id, "ban_user", user_id, f"reason={reason} expires={expires}")

async def unban_user(user_id: int, admin_id: int | None, reason: str = ""):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE bans SET is_active=FALSE WHERE user_id=$1 AND is_active=TRUE", user_id)
            await conn.execute("UPDATE users SET is_banned=FALSE WHERE user_id=$1", user_id)
            await audit.log(admin_id, "unban_user", user_id, f"reason={reason}")

async def list_active_bans() -> list[dict]:
    return [dict(r) for r in await db().fetch("SELECT * FROM bans WHERE is_active=TRUE ORDER BY id DESC")]