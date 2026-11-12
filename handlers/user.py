from datetime import datetime, timedelta
from aiogram import F, Router
from aiogram.types import CallbackQuery
from services import schedule
from ui import keyboards, formaters

router = Router()

DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def get_date_for_weekday(target_weekday: int) -> str:
    """Вычисляет дату для выбранного дня недели (0=Пн, 6=Вс)."""
    today = datetime.now()
    # В Python 0 = Понедельник, 6 = Воскресенье. В нашей БД так же.
    current_weekday = today.weekday()

    # Вычисляем разницу дней
    days_ahead = target_weekday - current_weekday
    if days_ahead < 0:  # Если день уже прошел на этой неделе, берем следующую
        days_ahead += 7

    target_date = today + timedelta(days=days_ahead)
    return target_date.strftime("%d.%m.%Y")


@router.callback_query(F.data == "menu:schedule")
async def menu_schedule(cb: CallbackQuery, db_user: dict):
    if not db_user["group_name"]:
        return await cb.answer("Вам не назначена группа!", show_alert=True)

    await cb.message.edit_text(
        f"📅 Расписание для группы <b>{db_user['group_name']}</b>\nВыберите день:",
        reply_markup=keyboards.schedule_nav()
    )


@router.callback_query(F.data.startswith("sched:day:"))
async def view_schedule_day(cb: CallbackQuery, db_user: dict):
    day_idx = int(cb.data.split(":")[2])
    lessons = await schedule.get_schedule(db_user["group_name"], day_idx)

    # Получаем правильную дату для этого дня
    date_str = get_date_for_weekday(day_idx)

    text = formaters.format_schedule_day(
        day_name=DAYS_RU[day_idx],
        date_str=date_str,
        group_name=db_user["group_name"],
        lessons=lessons
    )

    await cb.message.edit_text(text, reply_markup=keyboards.schedule_nav())