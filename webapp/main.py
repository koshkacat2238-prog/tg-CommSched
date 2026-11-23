import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional
from urllib.parse import parse_qsl

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import BOT_TOKEN, REDIS_URL
from database import close_pool, get_pool, init_pool
from services import homework as hw_service, users as user_service
from services.parser import fetch_schedule_from_ruz

logger = logging.getLogger(__name__)

CF_API_URL = os.getenv("CF_API_URL", "https://api.telegram.org").strip().rstrip("/")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Роли, имеющие право добавлять, редактировать и удалять ДЗ
HW_MANAGER_ROLES = ("headman", "teacher", "admin", "owner")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await redis_client.close()
    await close_pool()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ АВТОРИЗАЦИИ И ПРАВ ---
def verify_telegram_init_data(init_data: str | None) -> int | None:
    """Проверяет подпись Telegram WebApp initData и возвращает числовой user_id."""
    if not init_data:
        raise HTTPException(status_code=401, detail="Отсутствует заголовок X-Telegram-Init-Data")

    parsed = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Некорректный формат initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=403, detail="Подпись initData не прошла проверку")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Данные пользователя не переданы")

    user_data = json.loads(user_raw)
    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="В initData отсутствует id пользователя")

    return int(user_id)


def resolve_actor_id(fallback_user_id: int | None, x_telegram_init_data: str | None) -> int:
    verified_id = verify_telegram_init_data(x_telegram_init_data)
    uid = verified_id or fallback_user_id
    if not uid:
        raise HTTPException(status_code=401, detail="Пользователь не авторизован")
    return uid


def _subject_matches(teacher_subject: str | None, lesson_subject: str) -> bool:
    """Проверяет совпадение предмета учителя с названием предмета из расписания."""
    if not teacher_subject:
        return False
    t_subj = teacher_subject.strip().lower()
    l_subj = (lesson_subject or "").strip().lower()
    if not t_subj or not l_subj:
        return False
    return t_subj in l_subj or l_subj in t_subj


def ensure_teacher_scope(user: dict, group_name: str, subject: str):
    """
    Ограничивает доступ по группе и предмету только для роли 'teacher'.
    Роли 'headman' (староста), 'admin' и 'owner' могут управлять ДЗ по всем предметам группы.
    """
    if user.get("role") != "teacher":
        return

    teacher_subject = (user.get("teacher_subject") or "").strip()
    if not teacher_subject:
        raise HTTPException(
            status_code=403,
            detail="Для вашей учётной записи учителя не назначен предмет. Обратитесь к администратору."
        )

    if user.get("group_name") and user.get("group_name") != group_name:
        raise HTTPException(status_code=403, detail="Вы можете управлять ДЗ только своей группы")

    if not _subject_matches(teacher_subject, subject):
        raise HTTPException(
            status_code=403,
            detail=f"Вы можете управлять ДЗ только по своему предмету ({teacher_subject})"
        )


def _format_hw_notification(
    group_name: str,
    subject: str,
    description: str,
    due_date: str,
    is_edited: bool = False,
) -> str:
    """Формирует текст уведомления о новом или обновлённом ДЗ."""
    header = "✏️ <b>ДЗ обновлено!</b>" if is_edited else "📚 <b>Новое ДЗ!</b>"
    return (
        f"{header}\n\n"
        f"Группа: <b>{html.escape(group_name)}</b>\n"
        f"Предмет: <b>{html.escape(subject)}</b>\n"
        f"Задание: {html.escape(description)}\n"
        f"Дедлайн: <code>{html.escape(due_date)}</code>\n\n"
        f"Посмотреть в расписании: /start"
    )


def _create_tg_http_client() -> httpx.AsyncClient:
    """Создаёт HTTP-клиент для работы через Cloudflare Worker по IPv4 без зависаний keep-alive."""
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(
        timeout=10.0,
        transport=transport,
        headers={"Connection": "close"},
    )


async def _get_hw_target_ids(conn, group_name: str, subject: str, exclude_user_id: int) -> list[int]:
    """Возвращает список user_id получателей уведомления по группе и предмету."""
    recipients = await conn.fetch(
        """
        SELECT user_id, role, teacher_subject
        FROM users
        WHERE group_name = $1
          AND is_approved = TRUE
          AND COALESCE(is_banned, FALSE) = FALSE
        """,
        group_name,
    )

    target_ids = []
    for rec in recipients:
        if rec["user_id"] == exclude_user_id:
            continue

        role = rec["role"]
        if role in ("student", "headman", "admin", "owner"):
            target_ids.append(rec["user_id"])
        elif role == "teacher":
            if _subject_matches(rec["teacher_subject"], subject):
                target_ids.append(rec["user_id"])

    return target_ids


# --- СТАТИЧЕСКИЕ СТРАНИЦЫ ---
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


# --- ЭНДПОИНТЫ API ---
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
        or user["role"] not in HW_MANAGER_ROLES
    ):
        raise HTTPException(status_code=403, detail="У вас нет прав на добавление ДЗ")

    ensure_teacher_scope(user, data.group_name, data.subject)
    teacher_clean = (data.teacher or "").strip()

    await hw_service.add_homework(
        subject=data.subject,
        description=data.description,
        lesson_date=data.lesson_date,
        teacher=data.teacher,
        due_date=data.due_date,
        group_name=data.group_name,
        created_by=actor_id
    )

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM homework_notifications
            WHERE group_name = $1 AND subject = $2 AND lesson_date = $3 AND teacher = $4
            """,
            data.group_name,
            data.subject,
            data.lesson_date,
            teacher_clean,
        )
        target_ids = await _get_hw_target_ids(conn, data.group_name, data.subject, actor_id)

    if not target_ids:
        return {"status": "ok"}

    text = _format_hw_notification(
        group_name=data.group_name,
        subject=data.subject,
        description=data.description,
        due_date=data.due_date,
        is_edited=False,
    )

    async def send_notifications():
        sent_records = []
        async with _create_tg_http_client() as client:
            for uid in target_ids:
                try:
                    resp = await client.post(
                        f"{CF_API_URL}/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": uid, "text": text, "parse_mode": "HTML"}
                    )
                    if resp.status_code == 200:
                        payload = resp.json()
                        if payload.get("ok") and payload.get("result"):
                            msg_id = payload["result"]["message_id"]
                            sent_records.append(
                                (data.group_name, data.subject, data.lesson_date, teacher_clean, uid, msg_id)
                            )
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logger.warning("Не удалось отправить уведомление о ДЗ пользователю %s: %s", uid, exc)

        if sent_records:
            try:
                db_pool = get_pool()
                async with db_pool.acquire() as conn:
                    await conn.executemany(
                        """
                        INSERT INTO homework_notifications (group_name, subject, lesson_date, teacher, chat_id, message_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        sent_records,
                    )
            except Exception as exc:
                logger.error("Ошибка сохранения ID уведомлений о ДЗ в БД: %s", exc)

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
        or user["role"] not in HW_MANAGER_ROLES
    ):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    ensure_teacher_scope(user, data.group_name, data.subject)
    teacher_clean = (data.teacher or "").strip()

    await hw_service.update_homework(
        lesson_date=data.lesson_date,
        subject=data.subject,
        teacher=data.teacher,
        group_name=data.group_name,
        new_description=data.description,
        new_due_date=data.due_date,
        actor_id=actor_id
    )

    pool = get_pool()
    async with pool.acquire() as conn:
        old_notifs = await conn.fetch(
            """
            DELETE FROM homework_notifications
            WHERE group_name = $1 AND subject = $2 AND lesson_date = $3 AND teacher = $4
            RETURNING chat_id, message_id
            """,
            data.group_name,
            data.subject,
            data.lesson_date,
            teacher_clean,
        )
        target_ids = await _get_hw_target_ids(conn, data.group_name, data.subject, actor_id)

    old_targets = [(r["chat_id"], r["message_id"]) for r in old_notifs]
    if not old_targets and not target_ids:
        return {"status": "ok"}

    updated_text = _format_hw_notification(
        group_name=data.group_name,
        subject=data.subject,
        description=data.description,
        due_date=data.due_date,
        is_edited=True,
    )

    async def recreate_notifications():
        sent_records = []
        async with _create_tg_http_client() as client:
            # 1. Удаляем старые уведомления в чатах, чтобы не было дублей
            for chat_id, message_id in old_targets:
                try:
                    await client.post(
                        f"{CF_API_URL}/bot{BOT_TOKEN}/deleteMessage",
                        json={"chat_id": chat_id, "message_id": message_id},
                    )
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logger.warning("Не удалось удалить старое уведомление о ДЗ (chat=%s): %s", chat_id, exc)

            # 2. Отправляем новое уведомление с пуш-оповещением
            for uid in target_ids:
                try:
                    resp = await client.post(
                        f"{CF_API_URL}/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": uid, "text": updated_text, "parse_mode": "HTML"},
                    )
                    if resp.status_code == 200:
                        payload = resp.json()
                        if payload.get("ok") and payload.get("result"):
                            msg_id = payload["result"]["message_id"]
                            sent_records.append(
                                (data.group_name, data.subject, data.lesson_date, teacher_clean, uid, msg_id)
                            )
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logger.warning("Не удалось отправить обновлённое ДЗ пользователю %s: %s", uid, exc)

        if sent_records:
            try:
                db_pool = get_pool()
                async with db_pool.acquire() as conn:
                    await conn.executemany(
                        """
                        INSERT INTO homework_notifications (group_name, subject, lesson_date, teacher, chat_id, message_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        sent_records,
                    )
            except Exception as exc:
                logger.error("Ошибка сохранения ID обновлённых уведомлений о ДЗ в БД: %s", exc)

    asyncio.create_task(recreate_notifications())
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
        or user["role"] not in HW_MANAGER_ROLES
    ):
        raise HTTPException(status_code=403, detail="У вас нет прав")

    ensure_teacher_scope(user, group_name, subject)
    teacher_clean = (teacher or "").strip()

    await hw_service.delete_homework_by_lesson(lesson_date, subject, teacher, group_name, actor_id)

    pool = get_pool()
    async with pool.acquire() as conn:
        deleted_rows = await conn.fetch(
            """
            DELETE FROM homework_notifications
            WHERE group_name = $1 AND subject = $2 AND lesson_date = $3 AND teacher = $4
            RETURNING chat_id, message_id
            """,
            group_name,
            subject,
            lesson_date,
            teacher_clean,
        )

    if deleted_rows:
        targets = [(r["chat_id"], r["message_id"]) for r in deleted_rows]

        async def delete_notifications():
            async with _create_tg_http_client() as client:
                for chat_id, message_id in targets:
                    try:
                        await client.post(
                            f"{CF_API_URL}/bot{BOT_TOKEN}/deleteMessage",
                            json={"chat_id": chat_id, "message_id": message_id},
                        )
                        await asyncio.sleep(0.05)
                    except Exception as exc:
                        logger.warning("Не удалось удалить уведомление о ДЗ (chat=%s): %s", chat_id, exc)

        asyncio.create_task(delete_notifications())

    return {"status": "ok"}


@app.get("/api/schedule/{group_name}")
async def get_schedule_api(
    group_name: str,
    user_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None
):
    requester = None
    teacher_subject_filter = None

    if user_id:
        requester = await user_service.get_user(user_id)
        if requester and requester.get("role") == "teacher":
            if requester.get("group_name"):
                group_name = requester["group_name"]
            teacher_subject_filter = requester.get("teacher_subject")

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

        if requester:
            eng_t = requester.get("eng_teacher")
            chin_t = requester.get("chin_teacher")

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

        if teacher_subject_filter:
            filtered_schedule = [
                les for les in filtered_schedule
                if _subject_matches(teacher_subject_filter, les.get("subject", ""))
            ]

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