import asyncpg
from typing import Optional
from config import DATABASE_URL

_pool: Optional[asyncpg.Pool] = None

async def init_pool():
    global _pool
    for attempt in range(5):
        try:
            _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
            async with _pool.acquire() as conn:
                await conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
    id BIGSERIAL PRIMARY KEY,
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    time_start TEXT NOT NULL,
    time_end TEXT NOT NULL,
    subject TEXT NOT NULL,
    lesson_type TEXT NOT NULL,  -- 'Лекция' или 'Практика'
    teacher TEXT,               -- Имя преподавателя
    room TEXT,                  -- Аудитория
    group_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
                """)
        logging.info("Успешное подключение к БД и создание таблиц.")
        return  # Выходим из функции, если всё ок

    except Exception as e:
        logging.warning(f"Попытка {attempt + 1} подключения к БД не удалась: {e}")
        if attempt == 4:  # Если это была 5-я попытка
            raise
        await asyncio.sleep(2)

async def close_pool():
    if _pool: await _pool.close()

def db() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialized"
    return _pool