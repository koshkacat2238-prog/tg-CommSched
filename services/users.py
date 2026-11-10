from typing import Optional
from database import db
from services import audit
from config import OWNER_ID


async def get_user(user_id: int) -> Optional[dict]:
    row = await db().fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
    return dict(row) if row else None


async def get_or_create_user(user_id: int, username: str | None, full_name: str) -> dict:
    user = await get_user(user_id)
    if user: return user

    role = "owner" if user_id == OWNER_ID else "student"
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO users(user_id, username, full_name, role) VALUES($1,$2,$3,$4)",
                user_id, username, full_name, role
            )
            await audit.log(conn, user_id, "user_register", user_id, f"role={role}")
    return await get_user(user_id)


async def list_users(limit: int = 30) -> list[dict]:
    rows = await db().fetch("SELECT * FROM users ORDER BY created_at DESC LIMIT $1", limit)
    return [dict(r) for r in rows]


def can_manage(actor: dict, target: dict) -> bool:
    if actor["role"] == "owner" and target["role"] != "owner": return True
    if actor["role"] == "admin" and target["role"] not in ("admin", "owner"): return True
    return False


async def set_role(user_id: int, role: str, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET role=$1 WHERE user_id=$2", role, user_id)
            await audit.log(actor_id, "set_role", user_id, f"role={role}")


async def set_group(user_id: int, group: str, actor_id: int):
    group_val = group or None
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET group_name=$1 WHERE user_id=$2", group_val, user_id)
            await audit.log(actor_id, "set_group", user_id, f"group={group_val}")