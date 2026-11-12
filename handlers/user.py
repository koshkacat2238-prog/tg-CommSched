from aiogram import F, Router
from aiogram.types import CallbackQuery
from services import schedule
from ui import keyboards  # <--- ВОТ ЭТА СТРОЧКА РЕШАЕТ ПРОБЛЕМУ

router = Router()


@router.callback_query(F.data == "menu:schedule")
async def view_schedule(cb: CallbackQuery, db_user: dict):
    if not db_user["group_name"]:
        return await cb.answer("Вам не назначена группа! Обратитесь к админу.", show_alert=True)

    # Берем расписание из базы
    lessons = await schedule.get_schedule(db_user["group_name"])

    if not lessons:
        return await cb.message.edit_text(
            f"📅 На неделю для группы {db_user['group_name']} занятий нет.",
            reply_markup=keyboards.back_to_menu()
        )

    # Форматируем текст
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    text = f"📅 Расписание для группы {db_user['group_name']}:\n\n"
    for lesson in lessons:
        text += f"{days[lesson['day_of_week']]} в {lesson['time']} — {lesson['subject']}\n"

    await cb.message.edit_text(text, reply_markup=keyboards.back_to_menu())