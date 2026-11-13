from database import db

async def log(actor_id: int | None, action: str, target_id: int | None = None, details: str | None = None):
    async with db().acquire() as conn:
        await conn.execute(
            "INSERT INTO audit_log(actor_id, action, target_id, details) VALUES($1,$2,$3,$4)",
            actor_id, action, target_id, details
        )
async def get_logs(limit: int = 20, target_id: int | None = None) -> list[dict]:
    if target_id is not None:
        rows = await db().fetch(
            "SELECT * FROM audit_log WHERE target_id=$1 ORDER BY id DESC LIMIT $2",
            target_id, limit
        )
    else:
        rows = await db().fetch(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT $1", limit
        )
    return [dict(r) for r in rows]