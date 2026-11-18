import html


def format_user_card(u: dict) -> str:
    safe_name = html.escape(u.get("full_name") or "Без имени")
    safe_group = html.escape(u.get("group_name") or "не назначена")
    ban_status = "Да 🚫" if u.get("is_banned") else "Нет ✅"
    return (
        f"👤 <b>{safe_name}</b>\n"
        f"ID: <code>{u['user_id']}</code>\n"
        f"Роль: <b>{html.escape(u['role'])}</b>\n"
        f"Группа: <b>{safe_group}</b>\n"
        f"Забанен: {ban_status}"
    )