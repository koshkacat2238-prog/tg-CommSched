from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import date, timedelta
from typing import Optional
import redis.asyncio as redis
import json
import httpx
import asyncio

from services.parser import fetch_schedule_from_ruz
from services import homework as hw_service, users as user_service
from database import init_pool, close_pool
from config import REDIS_URL, BOT_TOKEN

app = FastAPI()
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Создаем клиент Redis
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("startup")
async def startup():
    await init_pool()


@app.on_event("shutdown")
async def shutdown():
    await redis_client.close()
    await close_pool()


@app.get("/")
async def read_index():
    return FileResponse("webapp/static/index.html")


# --- МОДЕЛИ ДАННЫХ ---
class HomeworkCreate(BaseModel):
    user_id: int
    group_name: str
    subject: str
    description: str
    lesson_date: str
    teacher: str
    due_date: str


class UserSettings(BaseModel):
    eng_teacher: Optional[str] = None
    chin_teacher: Optional[str] = None


# --- ЭНДПОИНТЫ ---

@app.get("/api/role/{user_id}")
async def get_user_role(user_id: int):
    user = await user_service.get_user(user_id)
    if not user:
        return {"role": "student", "group_name": None}
    return {"role": user["role"], "group_name": user["group_name"]}

@app.get("/privacy")
async def privacy_policy():
    return FileResponse("webapp/static/privacy.html")

@app.put("/api/user/{user_id}/settings")
async def save_settings(user_id: int, settings: UserSettings):
    await user_service.update_user_settings(user_id, settings.eng_teacher or "", settings.chin_teacher or "")
    return {"status": "ok"}


@app.post("/api/homework")
async def create_homework(data: HomeworkCreate):
    # 1. Проверка прав
    user = await user_service.get_user(data.user_id)
    if not user or user["role"] not in ("teacher", "admin", "owner"):
        raise HTTPException(status_code=403, detail="У вас нет прав на добавление ДЗ")

    # 2. Сохранение в БД
    await hw_service.add_homework(
        subject=data.subject,
        description=data.description,
        lesson_date=data.lesson_date,
        teacher=data.teacher,
        due_date=data.due_date,
        group_name=data.group_name,
        created_by=data.user_id
    )

    # 3. Отправка уведомлений студентам этой группы (в фоне)
    students = await user_service.get_students_by_group(data.group_name)
    text = (
        f"📚 <b>Новое ДЗ!</b>\n\n"
        f"Группа: <b>{data.group_name}</b>\n"
        f"Предмет: <b>{data.subject}</b>\n"
        f"Задание: {data.description}\n"
        f"Дедлайн: <code>{data.due_date}</code>\n\n"
        f"Посмотреть в расписании: /start"
    )

    async def send_notifications():
        async with httpx.AsyncClient() as client:
            for student in students:
                try:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": student["user_id"], "text": text, "parse_mode": "HTML"}
                    )
                    await asyncio.sleep(0.05)  # Задержка, чтобы не превысить лимиты Telegram
                except Exception:
                    pass

    asyncio.create_task(send_notifications())

    return {"status": "ok"}


@app.put("/api/homework")
async def update_homework_api(data: HomeworkCreate):
    user = await user_service.get_user(data.user_id)
    if not user or user["role"] not in ("teacher", "admin", "owner"):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    await hw_service.update_homework(
        lesson_date=data.lesson_date,
        subject=data.subject,
        teacher=data.teacher,
        group_name=data.group_name,
        new_description=data.description,
        new_due_date=data.due_date,
        actor_id=data.user_id
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
    # 1. Установка дат по умолчанию (текущая неделя)
    if not start:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
        start = start_date.strftime("%Y.%m.%d")
    if not end:
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)
        end = end_date.strftime("%Y.%m.%d")

    # 2. Проверка кэша Redis
    cache_key = f"sched:{group_name}:{start}:{end}"
    cached_raw = await redis_client.get(cache_key)

    if cached_raw:
        raw_schedule = json.loads(cached_raw)
    else:
        # Если в кэше нет, идем на сайт вуза
        try:
            raw_schedule = await fetch_schedule_from_ruz(group_name, start, end)
            # Сохраняем в кэш на 15 минут (900 сек)
            await redis_client.setex(cache_key, 900, json.dumps(raw_schedule))
            # Сохраняем "долгий" кэш на случай падения вуза на 24 часа
            await redis_client.setex(f"stale:{cache_key}", 86400, json.dumps(raw_schedule))
        except Exception as e:
            print(f"Ошибка загрузки с сайта вуза: {e}")
            # Если сайт упал, ищем старый кэш
            stale_cache = await redis_client.get(f"stale:{cache_key}")
            if stale_cache:
                raw_schedule = json.loads(stale_cache)
            else:
                raise HTTPException(
                    status_code=503,
                    detail="Сайт расписания временно недоступен. Попробуйте позже."
                )

    # 3. Обработка данных и фильтрация
    try:
        hws = await hw_service.list_homework(group_name)

        # Собираем уникальных преподавателей для списка в настройках
        eng_teachers = set()
        chin_teachers = set()
        for les in raw_schedule:
            subj = les['subject'].lower()
            teacher = les.get('teacher', '')
            if teacher:
                if 'иностранный' in subj or 'английский' in subj:
                    eng_teachers.add(teacher)
                if 'китайский' in subj:
                    chin_teachers.add(teacher)

        # Фильтрация по настройкам пользователя
        filtered_schedule = raw_schedule
        current_settings = {"eng_teacher": None, "chin_teacher": None}

        if user_id:
            user = await user_service.get_user(user_id)
            if user:
                eng_t = user.get("eng_teacher")
                chin_t = user.get("chin_teacher")

                current_settings["eng_teacher"] = eng_t
                current_settings["chin_teacher"] = chin_t

                filtered_schedule = []
                for les in raw_schedule:
                    subj = les['subject'].lower()
                    teacher = les.get('teacher', '')

                    # Скрываем английский, если препод не совпадает
                    if ('иностранный' in subj or 'английский' in subj) and eng_t:
                        if eng_t.lower() not in teacher.lower():
                            continue
                    # Скрываем китайский, если препод не совпадает
                    if 'китайский' in subj and chin_t:
                        if chin_t.lower() not in teacher.lower():
                            continue

                    filtered_schedule.append(les)

        # 4. Возврат результата
        return {
            "schedule": filtered_schedule,
            "homeworks": hws,
            "available_teachers": {"eng": list(eng_teachers), "chin": list(chin_teachers)},
            "current_settings": current_settings
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке данных")