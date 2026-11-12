def format_user_card(u: dict) -> str:
    return f"👤 <b>{u['full_name']}</b>\nID: <code>{u['user_id']}</code>\nРоль: <b>{u['role']}</b>\nЗабанен: {u['is_banned']}"


def format_schedule_day(day_name: str, date_str: str, group_name: str, lessons: list[dict]) -> str:
    text = f"🗓 <b>{day_name} ({date_str})</b>\n"
    text += f"Группа <b>{group_name}</b>\n\n"

    if not lessons:
        return text + "Занятий нет. Отдыхаем! 🎉"

    for les in lessons:
        # Выбираем эмодзи для типа занятия
        lesson_type = les.get('lesson_type', '')
        icon = "🧩" if "практика" in lesson_type.lower() else "🎓"

        time_start = les.get('time_start', les.get('time', ''))
        time_end = les.get('time_end', '')
        time_str = f"{time_start} – {time_end}" if time_end else time_start
        text += f"🕐 <b>{les['time_start']} – {les['time_end']}</b>\n"
        text += f"<b>{les['subject']}</b>\n"
        if lesson_type:
            text += f"{icon} {lesson_type}"

        teacher = les.get('teacher', '')
        if teacher:
            text += f" | {teacher}"
        text += "\n"

        room = les.get('room', '')
        if room:
            text += f"📍 Ауд. {room}\n"

        text += "➖➖➖➖➖➖➖➖\n"

    return text