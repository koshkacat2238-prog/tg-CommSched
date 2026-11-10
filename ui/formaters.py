def format_user_card(u: dict) -> str:
    return f"👤 <b>{u['full_name']}</b>\nID: <code>{u['user_id']}</code>\nРоль: <b>{u['role']}</b>\nЗабанен: {u['is_banned']}"