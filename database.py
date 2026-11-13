import asyncio
import logging
import asyncpg
from typing import Optional
from config import DATABASE_URL

_pool: Optional[asyncpg.Pool] = None


async def init_pool():
    global _pool

    # Делаем 5 попыток подключения
    for attempt in range(5):
        try:
            # Создаем пул соединений
            _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

            # Создаем таблицы (выполняем один раз при успешном подключении)
            async with _pool.acquire() as conn:
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','teacher','admin','owner')),
                    group_name TEXT,
                    is_banned BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS bans (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    admin_id BIGINT,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    expires_at TIMESTAMPTZ,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGSERIAL PRIMARY KEY,
                    actor_id BIGINT,
                    action TEXT NOT NULL,
                    target_id BIGINT,
                    details TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS schedule (
                    id BIGSERIAL PRIMARY KEY,
                    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    lesson_type TEXT NOT NULL,
                    teacher TEXT,
                    room TEXT,
                    group_name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS homework (
                    id BIGSERIAL PRIMARY KEY,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    created_by BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """)

            # Если код дошел до сюда, значит всё успешно
            logging.info("Успешное подключение к БД и создание таблиц.")
            return  # Выходим из цикла и функции

        except Exception as e:
            logging.warning(f"Попытка {attempt + 1}/5 подключения к БД не удалась: {e}")
            if attempt == 4:  # Если это была 5-я (последняя) попытка
                raise  # Выбрасываем ошибку наверх, чтобы бот упал
            await asyncio.sleep(2)  # Ждем 2 секунды перед следующей попыткой


async def close_pool():
    if _pool:
        await _pool.close()


def db() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialized"
    return _pool