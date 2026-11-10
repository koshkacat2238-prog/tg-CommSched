from datetime import datetime
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ROLES
from handlers.states import AddSchedule, SetGroupFSM, BanFSM
from services import users, bans, schedule, audit
from ui import keyboards, texts
from ui.formatters import format_user_card

router = Router()

@router.message(Command("cancel"), StateFilter("*"))
async def cancel_any(message: Message, state: FSMContext, db_user: dict):
    await state.clear()
    await message.answer("Отменено.", reply_markup=keyboards.main_menu(db_user["role"]))

# --- Управление пользователями ---
@router.callback_query(F.data == "menu:users")
async def users_list(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    users_list = await users.list_users(30)
    kb = InlineKeyboardBuilder()
    for u in users_list:
        status = "🚫" if u["is_banned"] else "👤"
        kb.button(text=f"{status} {u['full_name']} ({u['role']})", callback_data=f"usr:card:{u['user_id']}")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1)
    await cb.message.edit_text("👥 Пользователи:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("usr:card:"))
async def user_card_view(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    uid = int(cb.data.split(":")[2])
    u = await users.get_user(uid)
    await cb.message.edit_text(format_user_card(u), reply_markup=keyboards.user_card(uid, bool(u["is_banned"])))

@router.callback_query(F.data.startswith("usr:role:"))
async def user_role_menu(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    uid = int(cb.data.split(":")[2])
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target): return await cb.answer("Нельзя изменить этого пользователя", show_alert=True)
    await cb.message.edit_text("Выберите роль:", reply_markup=keyboards.roles_keyboard(uid))

@router.callback_query(F.data.startswith("usr:setrole:"))
async def user_set_role(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    _, _, uid_s, role = cb.data.split(":")
    uid = int(uid_s)
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target): return await cb.answer("Нельзя", show_alert=True)
    await users.set_role(uid, role, db_user["user_id"])
    await cb.answer("Роль изменена")
    u = await users.get_user(uid)
    await cb.message.edit_text(format_user_card(u), reply_markup=keyboards.user_card(uid, bool(u["is_banned"])))

# --- Баны ---
@router.callback_query(F.data.startswith("usr:ban:"))
async def ban_start(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    uid = int(cb.data.split(":")[2])
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target): return await cb.answer("Нельзя забанить", show_alert=True)
    await state.update_data(target_uid=uid)
    await state.set_state(BanFSM.reason)
    await cb.message.answer(f"Причина бана <b>{target['full_name']}</b>:")

@router.message(BanFSM.reason)
async def ban_reason(message: Message, state: FSMContext):
    await state.update_data(reason=message.text.strip())
    data = await state.get_data()
    await message.answer("Срок:", reply_markup=keyboards.ban_duration_keyboard(data["target_uid"]))

@router.callback_query(F.data.startswith("usr:doBan:"))
async def ban_apply(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    _, _, uid_s, days_s = cb.data.split(":")
    uid, days = int(uid_s), int(days_s)
    data = await state.get_data()
    await bans.ban_user(uid, db_user["user_id"], data.get("reason", "Без причины"), days if days > 0 else None)
    await state.clear()
    await cb.message.edit_text("🚫 Пользователь забанен.", reply_markup=keyboards.back_to_menu())

@router.callback_query(F.data == "menu:bans")
async def active_bans(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    bans_list = await bans.list_active_bans()
    text = "✅ Активных банов нет." if not bans_list else "🚫 Активные баны:\n\n"
    for b in bans_list:
        t = await users.get_user(b["user_id"])
        exp = b["expires_at"].strftime("%Y-%m-%d %H:%M") if b["expires_at"] else "навсегда"
        text += f"• {t['full_name']} (ID {b['user_id']}) до {exp}. Причина: {b['reason']}\n"
    await cb.message.edit_text(text, reply_markup=keyboards.back_to_menu())

# --- Аудит ---
@router.callback_query(F.data == "menu:logs")
async def logs_menu(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES: return await cb.answer("Нет прав", show_alert=True)
    logs = await audit.get_logs(20) # Для простоты добавлен get_logs в audit.py (см. примечание ниже)
    lines = ["📜 <b>Логи:</b>\n"]
    for l in logs:
        lines.append(f"• {l['created_at'].strftime('%m-%d %H:%M')} {l['action']} (ID {l['actor_id']}) {l['details'] or ''}")
    await cb.message.edit_text("\n".join(lines), reply_markup=keyboards.back_to_menu())