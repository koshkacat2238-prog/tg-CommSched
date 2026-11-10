from database import db
async def add_schedule(day_of_week: int, time: str, subject: str, group_name: str) -> int:
    return await db().fetchval("INSERT INTO schedule(day_of_week, time, subject, group_name) VALUES($1,$2,$3,$4) RETURNING id", day_of_week, time, subject, group_name)

async def get_schedule(group_name: str, day_of_week: int | None = None) -> list[dict]:
    if day_of_week is not None:
        rows = await db().fetch("SELECT * FROM schedule WHERE group_name=$1 AND day_of_week=$2 ORDER BY time", group_name, day_of_week)
    else:
        rows = await db().fetch("SELECT * FROM schedule WHERE group_name=$1 ORDER BY day_of_week, time", group_name)
    return [dict(r) for r in rows]