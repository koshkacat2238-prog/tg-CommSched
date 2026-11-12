from database import db
async def add_schedule(
    day_of_week: int,
    time_start: str,
    time_end: str,
    subject: str,
    lesson_type: str,
    teacher: str,
    room: str,
    group_name: str
) -> int:
    return await db().fetchval(
        "INSERT INTO schedule("
        "day_of_week, time_start, time_end, subject, lesson_type, teacher, room, group_name"
        ") VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
        day_of_week, time_start, time_end, subject, lesson_type, teacher, room, group_name
    )
async def get_schedule(group_name: str, day_of_week: int | None = None) -> list[dict]:
    if day_of_week is not None:
        rows = await db().fetch("SELECT * FROM schedule WHERE group_name=$1 AND day_of_week=$2 ORDER BY time", group_name, day_of_week)
    else:
        rows = await db().fetch("SELECT * FROM schedule WHERE group_name=$1 ORDER BY day_of_week, time", group_name)
    return [dict(r) for r in rows]