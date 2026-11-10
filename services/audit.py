from database import db

async def log(actor_id: int | None, action: str, target_id: int | None = None, details: str | None = None):
    async with db().acquire() as conn:
        await conn.execute(
            "INSERT INTO audit_log(actor_id, action, target_id, details) VALUES($1,$2,$3,$4)",
            actor_id, action, target_id, details
        )