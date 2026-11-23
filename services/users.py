from typing import Optional
from database import db, get_pool
from services import audit
from config import OWNER_ID


async def get_user(user_id: int) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, username, full_name, role, group_name,
                   is_approved, is_banned, eng_teacher, chin_teacher, teacher_subject
            FROM users
            WHERE user_id = $1
            """,
            user_id,
        )
        return dict(row) if row else None


async def get_or_create_user(user_id: int, username: str | None, full_name: str) -> dict:
    user = await get_user(user_id)
    if user:
        # Обновляем имя/юзернейм, если они изменились в Telegram
        if user["username"] != username or user["full_name"] != full_name:
            await db().execute(
                "UPDATE users SET username=$1, full_name=$2 WHERE user_id=$3",
                username, full_name, user_id
            )
            user["username"] = username
            user["full_name"] = full_name
        return user

    role = "owner" if user_id == OWNER_ID else "student"
    is_approved = (user_id == OWNER_ID)
    is_agreed = (user_id == OWNER_ID)

    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO users(user_id, username, full_name, role, is_approved, is_agreed)
                VALUES($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO UPDATE
                    SET username = EXCLUDED.username,
                        full_name = EXCLUDED.full_name
                RETURNING *
                """,
                user_id, username, full_name, role, is_approved, is_agreed
            )
            await audit.log(
                user_id, "user_register", user_id,
                f"role={role} approved={is_approved}", conn=conn
            )

    return dict(row)


async def approve_user(user_id: int, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET is_approved=TRUE WHERE user_id=$1", user_id)
            await audit.log(actor_id, "approve_user", user_id, "User approved", conn=conn)


async def reject_user(user_id: int, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM users WHERE user_id=$1", user_id)
            await audit.log(actor_id, "reject_user", user_id, "User rejected and deleted", conn=conn)


async def list_pending_users() -> list[dict]:
    rows = await db().fetch("SELECT * FROM users WHERE is_approved=FALSE ORDER BY created_at ASC")
    return [dict(r) for r in rows]


async def list_users(limit: int = 30) -> list[dict]:
    rows = await db().fetch("SELECT * FROM users ORDER BY created_at DESC LIMIT $1", limit)
    return [dict(r) for r in rows]


def can_manage(actor: dict | None, target: dict | None, new_role: str | None = None) -> bool:
    if not actor or not target:
        return False
    if actor["user_id"] == target["user_id"]:
        return False
    if actor["role"] == "owner" and target["role"] != "owner":
        return new_role != "owner"
    if actor["role"] == "admin" and target["role"] not in ("admin", "owner"):
        # Обычный админ не может назначать админов или владельцев
        if new_role in ("admin", "owner"):
            return False
        return True
    return False


async def set_role(user_id: int, role: str, actor_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET role=$1 WHERE user_id=$2", role, user_id)
            await audit.log(actor_id, "set_role", user_id, f"role={role}", conn=conn)


async def set_group(user_id: int, group: str, actor_id: int):
    group_val = group or None
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET group_name=$1 WHERE user_id=$2", group_val, user_id)
            await audit.log(actor_id, "set_group", user_id, f"group={group_val}", conn=conn)


async def update_user_settings(user_id: int, eng_teacher: str, chin_teacher: str):
    await db().execute(
        "UPDATE users SET eng_teacher=$1, chin_teacher=$2 WHERE user_id=$3",
        eng_teacher or None, chin_teacher or None, user_id
    )


async def get_groups_with_users() -> list[str]:
    rows = await db().fetch(
        "SELECT DISTINCT group_name FROM users WHERE group_name IS NOT NULL AND group_name != '' ORDER BY group_name"
    )
    return [r["group_name"] for r in rows]


async def list_users_by_group(group_name: str) -> list[dict]:
    if group_name == "None":
        rows = await db().fetch(
            "SELECT * FROM users WHERE group_name IS NULL OR group_name = '' ORDER BY created_at DESC"
        )
    else:
        rows = await db().fetch(
            "SELECT * FROM users WHERE group_name = $1 ORDER BY created_at DESC",
            group_name
        )
    return [dict(r) for r in rows]


async def get_students_by_group(group_name: str) -> list[dict]:
    """Возвращает всех одобренных и не забаненных пользователей конкретной группы."""
    rows = await db().fetch(
        "SELECT user_id FROM users WHERE group_name = $1 AND is_approved = TRUE AND is_banned = FALSE",
        group_name
    )
    return [dict(r) for r in rows]


async def agree_to_privacy(user_id: int):
    await db().execute("UPDATE users SET is_agreed = TRUE WHERE user_id = $1", user_id)