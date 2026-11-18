from database import db
from services import audit


async def add_homework(
    subject: str,
    description: str,
    lesson_date: str,
    teacher: str,
    due_date: str,
    group_name: str,
    created_by: int
) -> int:
    async with db().acquire() as conn:
        async with conn.transaction():
            new_id = await conn.fetchval(
                "INSERT INTO homework(subject, description, lesson_date, teacher, due_date, group_name, created_by) "
                "VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id",
                subject, description, lesson_date, teacher or "", due_date, group_name, created_by
            )
            await audit.log(
                created_by, "add_homework", None,
                f"subject={subject} group={group_name}", conn=conn
            )
            return new_id


async def list_homework(
    group_name: str,
    start_date: str | None = None,
    end_date: str | None = None
) -> list[dict]:
    if start_date and end_date:
        rows = await db().fetch(
            "SELECT * FROM homework WHERE group_name=$1 AND lesson_date BETWEEN $2 AND $3 ORDER BY lesson_date, id",
            group_name, start_date, end_date
        )
    else:
        rows = await db().fetch(
            "SELECT * FROM homework WHERE group_name=$1 ORDER BY id DESC LIMIT 100",
            group_name
        )
    return [dict(r) for r in rows]


async def update_homework(
    lesson_date: str,
    subject: str,
    teacher: str,
    group_name: str,
    new_description: str,
    new_due_date: str,
    actor_id: int
) -> None:
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE homework SET description=$1, due_date=$2 "
                "WHERE lesson_date=$3 AND subject=$4 AND COALESCE(teacher, '')=$5 AND group_name=$6",
                new_description, new_due_date, lesson_date, subject, teacher or "", group_name
            )
            await audit.log(
                actor_id, "update_homework", None,
                f"subject={subject} date={lesson_date}", conn=conn
            )


async def delete_homework_by_lesson(
    lesson_date: str,
    subject: str,
    teacher: str,
    group_name: str,
    actor_id: int
) -> None:
    async with db().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM homework WHERE lesson_date=$1 AND subject=$2 AND COALESCE(teacher, '')=$3 AND group_name=$4",
                lesson_date, subject, teacher or "", group_name
            )
            await audit.log(
                actor_id, "delete_homework", None,
                f"subject={subject} date={lesson_date}", conn=conn
            )