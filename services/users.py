from typing import Optional
from database import db
from services import audit
from config import OWNER_ID


async def get_user(user_id: int) -> Optional[dict]:
    row = await db().fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
    return dict(row) if row else None


async def get_or_create_user(user_id: int, username: str | None, full_name: str) -> dict:
    user = await get_user(user_id)
    if user:
        return user

    role = "owner" if user_id == OWNER_ID else "student"
    is_approved = True if user_id == OWNER_ID else False

    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO users(user_id, username, full_name, role, is_approved) "
                "VALUES($1,$2,$3,$4,$5) RETURNING *",
                user_id, username, full_name, role, is_approved
            )
            await audit.log(user_id, "user_register", user_id, f"role={role} approved={is_approved}")

    return dict(row)

async def approve_user(user_id: int, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET is_approved=TRUE WHERE user_id=$1", user_id)
            await audit.log(actor_id, "approve_user", user_id, "User approved")

async def reject_user(user_id: int, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM users WHERE user_id=$1", user_id)
            await audit.log(actor_id, "reject_user", user_id, "User rejected and deleted")

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

async def update_user_settings(user_id: int, eng_teacher: str, chin_teacher: str):
    async with db().acquire() as conn:
        await conn.execute(
            "UPDATE users SET eng_teacher=$1, chin_teacher=$2 WHERE user_id=$3",
            eng_teacher or None, chin_teacher or None, user_id
        )
async def get_groups_with_users() -> list[str]:
    """Возвращает список уникальных групп, у которых есть участники."""
    rows = await db().fetch(
        "SELECT DISTINCT group_name FROM users WHERE group_name IS NOT NULL AND group_name != '' ORDER BY group_name"
    )
    return [r['group_name'] for r in rows]

async def list_users_by_group(group_name: str) -> list[dict]:
    """Возвращает список пользователей из конкретной группы."""
    if group_name == "None": # Специальный маркер для тех, у кого нет группы
        rows = await db().fetch("SELECT * FROM users WHERE group_name IS NULL OR group_name = '' ORDER BY created_at DESC")
    else:
        rows = await db().fetch("SELECT * FROM users WHERE group_name = $1 ORDER BY created_at DESC", group_name)
    return [dict(r) for r in rows]