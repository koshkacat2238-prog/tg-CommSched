from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import date, timedelta

from services.parser import fetch_schedule_from_ruz
from services import homework as hw_service, users as user_service
from database import init_pool

app = FastAPI()
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")


@app.on_event("startup")
async def startup():
    await init_pool()


@app.get("/")
async def read_index():
    return FileResponse("webapp/static/index.html")


class UserSettings (BaseModel):
    eng_teacher: str
    ch_teacher: str

@app.put("/api/user/{user_id}/settings")
async def save_settings(user_id: int, settings: UserSettings):
    await user_service.update_user_settings(user_id, settings.eng_teacher, settings.chin_teacher)
    return {"status": "ok"}


class HomeworkCreate(BaseModel):
    user_id: int
    group_name: str
    subject: str
    description: str
    lesson_date: str
    teacher: str
    due_date: str


@app.get("/api/role/{user_id}")
async def get_user_role(user_id: int):
    user = await user_service.get_user(user_id)
    if not user: return {"role": "student"}
    return {"role": user["role"]}


@app.post("/api/homework")
async def create_homework(data: HomeworkCreate):
    user = await user_service.get_user(data.user_id)
    if not user or user["role"] not in ("teacher", "admin", "owner"):
        raise HTTPException(status_code=403, detail="У вас нет прав на добавление ДЗ")

    await hw_service.add_homework(
        subject=data.subject, description=data.description, lesson_date=data.lesson_date,
        teacher=data.teacher, due_date=data.due_date, group_name=data.group_name, created_by=data.user_id
    )
    return {"status": "ok"}


@app.put("/api/homework")
async def update_homework_api(data: HomeworkCreate):
    user = await user_service.get_user(data.user_id)
    if not user or user["role"] not in ("teacher", "admin", "owner"):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    await hw_service.update_homework(
        lesson_date=data.lesson_date, subject=data.subject, teacher=data.teacher,
        group_name=data.group_name, new_description=data.description, new_due_date=data.due_date, actor_id=data.user_id
    )
    return {"status": "ok"}


@app.delete("/api/homework")
async def delete_homework_api(user_id: int, group_name: str, subject: str, lesson_date: str, teacher: str):
    user = await user_service.get_user(user_id)
    if not user or user["role"] not in ("teacher", "admin", "owner"):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    await hw_service.delete_homework_by_lesson(lesson_date, subject, teacher, group_name, user_id)
    return {"status": "ok"}


@app.get("/api/schedule/{group_name}")
async def get_schedule_api(group_name: str, user_id: int = None, start: str = None, end: str = None):
    # ^^^^^^^ ВОТ ЭТОГО ПАРАМЕТРА НЕ ХВАТАЛО

    if not start:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
        start = start_date.strftime("%Y.%m.%d")
    if not end:
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)
        end = end_date.strftime("%Y.%m.%d")

    try:
        schedule = await fetch_schedule_from_ruz(group_name, start, end)
        hws = await hw_service.list_homework(group_name)

        # ФИЛЬТРАЦИЯ ПО НАСТРОЙКАМ ПОЛЬЗОВАТЕЛЯ
        if user_id:
            user = await user_service.get_user(user_id)
            if user:
                eng_t = user.get("eng_teacher")
                chin_t = user.get("chin_teacher")

                filtered_schedule = []
                for les in schedule:
                    subj = les['subject'].lower()
                    teacher = les.get('teacher', '')

                    # Фильтр английского
                    if ('иностранный' in subj or 'английский' in subj) and eng_t:
                        if eng_t.lower() not in teacher.lower():
                            continue

                    # Фильтр китайского
                    if 'китайский' in subj and chin_t:
                        if chin_t.lower() not in teacher.lower():
                            continue

                    filtered_schedule.append(les)
                schedule = filtered_schedule

        return {"schedule": schedule, "homeworks": hws}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=str(e))