import asyncio
import hashlib
import hmac
import html
import json
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from database import get_pool

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import BOT_TOKEN, REDIS_URL
from database import close_pool, init_pool
from services import homework as hw_service, users as user_service
from services.parser import fetch_schedule_from_ruz

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await redis_client.close()
    await close_pool()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")


def verify_telegram_init_data(init_data: str | None) -> int | None:
    """Проверяет подпись Telegram WebApp initData и возвращает достоверный user_id."""
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_data = json.loads(parsed.get("user", "{}"))
        return int(user_data["id"]) if "id" in user_data else None
    except Exception:
        return None


def resolve_actor_id(fallback_user_id: int | None, x_telegram_init_data: str | None) -> int:
    verified_id = verify_telegram_init_data(x_telegram_init_data)
    if x_telegram_init_data and verified_id is None:
        raise HTTPException(status_code=401, detail="Некорректная подпись Telegram initData")
    uid = verified_id or fallback_user_id
    if not uid:
        raise HTTPException(status_code=401, detail="Пользователь не авторизован")
    return uid


@app.get("/")
async def read_index():
    return FileResponse("webapp/static/index.html")


@app.get("/privacy")
async def privacy_policy():
    return FileResponse("webapp/static/privacy.html")


# --- МОДЕЛИ ДАННЫХ ---
class HomeworkCreate(BaseModel):
    user_id: Optional[int] = None
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
async def get_user_role(
    user_id: int,
    x_telegram_init_data: Optional[str] = Header(default=None)
):
    uid = resolve_actor_id(user_id, x_telegram_init_data)
    user = await user_service.get_user(uid)
    if not user or user.get("is_banned") or not user.get("is_approved"):
        return {"role": "student", "group_name": user["group_name"] if user else None}
    return {"role": user["role"], "group_name": user["group_name"]}


@app.put("/api/user/{user_id}/settings")
async def save_settings(
    user_id: int,
    settings: UserSettings,
    x_telegram_init_data: Optional[str] = Header(default=None)
):
    uid = resolve_actor_id(user_id, x_telegram_init_data)
    if uid != user_id:
        raise HTTPException(status_code=403, detail="Нельзя менять чужие настройки")
    await user_service.update_user_settings(uid, settings.eng_teacher or "", settings.chin_teacher or "")
    return {"status": "ok"}


@app.post("/api/homework")
async def create_homework(
    data: HomeworkCreate,
    x_telegram_init_data: Optional[str] = Header(default=None)
):
    actor_id = resolve_actor_id(data.user_id, x_telegram_init_data)
    user = await user_service.get_user(actor_id)
    if (
        not user
        or user.get("is_banned")
        or not user.get("is_approved")
        or user["role"] not in ("teacher", "admin", "owner")
    ):
        raise HTTPException(status_code=403, detail="У вас нет прав на добавление ДЗ")

    await hw_service.add_homework(
        subject=data.subject,
        description=data.description,
        lesson_date=data.lesson_date,
        teacher=data.teacher,
        due_date=data.due_date,
        group_name=data.group_name,
        created_by=actor_id
    )

    students = await user_service.get_students_by_group(data.group_name)
    text = (
        f"📚 <b>Новое ДЗ!</b>\n\n"
        f"Группа: <b>{html.escape(data.group_name)}</b>\n"
        f"Предмет: <b>{html.escape(data.subject)}</b>\n"
        f"Задание: {html.escape(data.description)}\n"
        f"Дедлайн: <code>{html.escape(data.due_date)}</code>\n\n"
        f"Посмотреть в расписании: /start"
    )

    async def send_notifications():
        async with httpx.AsyncClient(timeout=10.0) as client:
            for student in students:
                try:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": student["user_id"], "text": text, "parse_mode": "HTML"}
                    )
                    await asyncio.sleep(0.05)
                except Exception:
                    pass

    asyncio.create_task(send_notifications())
    return {"status": "ok"}


@app.put("/api/homework")
async def update_homework_api(
    data: HomeworkCreate,
    x_telegram_init_data: Optional[str] = Header(default=None)
):
    actor_id = resolve_actor_id(data.user_id, x_telegram_init_data)
    user = await user_service.get_user(actor_id)
    if (
        not user
        or user.get("is_banned")
        or not user.get("is_approved")
        or user["role"] not in ("teacher", "admin", "owner")
    ):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    await hw_service.update_homework(
        lesson_date=data.lesson_date,
        subject=data.subject,
        teacher=data.teacher,
        group_name=data.group_name,
        new_description=data.description,
        new_due_date=data.due_date,
        actor_id=actor_id
    )
    return {"status": "ok"}


@app.delete("/api/homework")
async def delete_homework_api(
    group_name: str,
    subject: str,
    lesson_date: str,
    teacher: str = "",
    user_id: Optional[int] = None,
    x_telegram_init_data: Optional[str] = Header(default=None)
):
    actor_id = resolve_actor_id(user_id, x_telegram_init_data)
    user = await user_service.get_user(actor_id)
    if (
        not user
        or user.get("is_banned")
        or not user.get("is_approved")
        or user["role"] not in ("teacher", "admin", "owner")
    ):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    await hw_service.delete_homework_by_lesson(lesson_date, subject, teacher, group_name, actor_id)
    return {"status": "ok"}


@app.get("/api/schedule/{group_name}")
async def get_schedule_api(
    group_name: str,
    user_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None
):
    if not start:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
        start = start_date.strftime("%Y.%m.%d")
    if not end:
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)
        end = end_date.strftime("%Y.%m.%d")

    cache_key = f"sched:{group_name}:{start}:{end}"
    cached_raw = await redis_client.get(cache_key)

    if cached_raw:
        raw_schedule = json.loads(cached_raw)
    else:
        try:
            raw_schedule = await fetch_schedule_from_ruz(group_name, start, end)
            await redis_client.setex(cache_key, 900, json.dumps(raw_schedule))
            await redis_client.setex(f"stale:{cache_key}", 86400, json.dumps(raw_schedule))
        except Exception as e:
            print(f"Ошибка загрузки с сайта вуза: {e}")
            stale_cache = await redis_client.get(f"stale:{cache_key}")
            if stale_cache:
                raw_schedule = json.loads(stale_cache)
            else:
                raise HTTPException(
                    status_code=503,
                    detail="Сайт расписания временно недоступен. Попробуйте позже."
                )

    try:
        start_iso = start.replace(".", "-")
        end_iso = end.replace(".", "-")
        hws = await hw_service.list_homework(group_name, start_iso, end_iso)

        eng_teachers = set()
        chin_teachers = set()
        for les in raw_schedule:
            subj = (les.get("subject") or "").lower()
            teacher = les.get("teacher") or ""
            if teacher:
                if "иностранный" in subj or "английский" in subj:
                    eng_teachers.add(teacher)
                if "китайский" in subj:
                    chin_teachers.add(teacher)

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
                    subj = (les.get("subject") or "").lower()
                    teacher = les.get("teacher") or ""

                    if ("иностранный" in subj or "английский" in subj) and eng_t:
                        if eng_t.lower() not in teacher.lower():
                            continue
                    if "китайский" in subj and chin_t:
                        if chin_t.lower() not in teacher.lower():
                            continue

                    filtered_schedule.append(les)

        return {
            "schedule": filtered_schedule,
            "homeworks": hws,
            "available_teachers": {"eng": sorted(eng_teachers), "chin": sorted(chin_teachers)},
            "current_settings": current_settings
        }
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при обработке данных")

@app.get("/health")
async def healthcheck():
    """Проверка доступности FastAPI и подключения к PostgreSQL для Docker healthcheck."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")