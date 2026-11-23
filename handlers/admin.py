import html
from aiogram import F, Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ROLES
from handlers.states import AddSchedule, SetGroupFSM, BanFSM
from services import users, bans, schedule, audit
from ui import keyboards
from ui.formatters import format_user_card
from database import get_pool

router = Router()


@router.message(Command("cancel"), StateFilter("*"))
async def cancel_any(message: Message, state: FSMContext, db_user: dict):
    await state.clear()
    await message.answer("Отменено.", reply_markup=keyboards.main_menu(db_user["role"]))


# --- Управление пользователями ---
@router.callback_query(F.data == "menu:users")
async def users_group_list(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    await state.clear()

    groups = await users.get_groups_with_users()

    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=f"📁 {g}", callback_data=f"usr:grp:{g}")

    kb.button(text="👤 Без группы", callback_data="usr:grp:None")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2, 1, 1)

    await cb.message.edit_text("👥 Выберите группу для просмотра:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("usr:grp:"))
async def users_in_group(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    group_name = cb.data.split(":", 2)[2]
    users_list = await users.list_users_by_group(group_name)

    kb = InlineKeyboardBuilder()
    for u in users_list:
        status = "🚫" if u["is_banned"] else "👤"
        kb.button(text=f"{status} {u['full_name']} ({u['role']})", callback_data=f"usr:card:{u['user_id']}")

    kb.button(text="⬅️ К группам", callback_data="menu:users")
    kb.adjust(1)

    display_name = "Без группы" if group_name == "None" else html.escape(group_name)
    await cb.message.edit_text(f"👥 Пользователи в группе <b>{display_name}</b>:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("usr:card:"))
async def user_card_view(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    await state.clear()  # Сбрасываем FSM, если админ нажал "Отмена" при бане
    uid = int(cb.data.split(":")[2])
    u = await users.get_user(uid)
    if not u:
        return await cb.answer("Пользователь не найден", show_alert=True)
    await cb.message.edit_text(format_user_card(u), reply_markup=keyboards.user_card(uid, bool(u["is_banned"])))
    await cb.answer()


@router.callback_query(F.data.startswith("usr:role:"))
async def user_role_menu(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    uid = int(cb.data.split(":")[2])
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target):
        return await cb.answer("Нельзя изменить этого пользователя", show_alert=True)
    await cb.message.edit_text("Выберите роль:", reply_markup=keyboards.roles_keyboard(uid, db_user["role"]))
    await cb.answer()


@router.callback_query(F.data.startswith("usr:setrole:"))
async def user_set_role(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    _, _, uid_s, role = cb.data.split(":")
    uid = int(uid_s)
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target, new_role=role):
        return await cb.answer("Недостаточно прав для назначения этой роли", show_alert=True)
    await users.set_role(uid, role, db_user["user_id"])
    await cb.answer("Роль изменена")
    u = await users.get_user(uid)
    if u:
        await cb.message.edit_text(format_user_card(u), reply_markup=keyboards.user_card(uid, bool(u["is_banned"])))


# --- Баны ---
@router.callback_query(F.data.startswith("usr:ban:"))
async def ban_start(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    uid = int(cb.data.split(":")[2])
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target):
        return await cb.answer("Нельзя забанить этого пользователя", show_alert=True)
    await state.update_data(target_uid=uid)
    await state.set_state(BanFSM.reason)
    await cb.message.answer(f"Причина бана <b>{html.escape(target['full_name'])}</b> (или /cancel):")
    await cb.answer()


@router.message(BanFSM.reason, F.text)
async def ban_reason(message: Message, state: FSMContext):
    await state.update_data(reason=message.text.strip())
    data = await state.get_data()
    await message.answer("Срок:", reply_markup=keyboards.ban_duration_keyboard(data["target_uid"]))


@router.callback_query(F.data.startswith("usr:doBan:"))
async def ban_apply(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    _, _, uid_s, days_s = cb.data.split(":")
    uid, days = int(uid_s), int(days_s)
    target = await users.get_user(uid)
    if not users.can_manage(db_user, target):
        return await cb.answer("Нельзя забанить этого пользователя", show_alert=True)
    data = await state.get_data()
    await bans.ban_user(uid, db_user["user_id"], data.get("reason", "Без причины"), days if days > 0 else None)
    await state.clear()
    await cb.message.edit_text("🚫 Пользователь забанен.", reply_markup=keyboards.back_to_menu())
    await cb.answer()


@router.callback_query(F.data.startswith("usr:unban:"))
async def user_unban(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    uid = int(cb.data.split(":")[2])
    await bans.unban_user(uid, db_user["user_id"], "Ручной разбан админом")
    await cb.answer("✅ Пользователь разбанен", show_alert=True)

    u = await users.get_user(uid)
    if u:
        await cb.message.edit_text(
            format_user_card(u),
            reply_markup=keyboards.user_card(uid, bool(u["is_banned"]))
        )


@router.callback_query(F.data == "menu:bans")
async def active_bans(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    bans_list = await bans.list_active_bans()
    text = "✅ Активных банов нет." if not bans_list else "🚫 <b>Активные баны:</b>\n\n"
    for b in bans_list:
        full_name = html.escape(b.get("full_name") or "Неизвестный")
        reason = html.escape(b.get("reason") or "—")
        exp = b["expires_at"].strftime("%Y-%m-%d %H:%M") if b["expires_at"] else "навсегда"
        text += f"• {full_name} (ID <code>{b['user_id']}</code>) до {exp}. Причина: {reason}\n"
    await cb.message.edit_text(text, reply_markup=keyboards.back_to_menu())
    await cb.answer()


# --- Аудит ---
@router.callback_query(F.data == "menu:logs")
async def logs_menu(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    logs = await audit.get_logs(20)
    lines = ["📜 <b>Логи:</b>\n"]
    for l in logs:
        action = html.escape(l["action"] or "")
        details = html.escape(l["details"] or "")
        lines.append(f"• {l['created_at'].strftime('%m-%d %H:%M')} {action} (ID {l['actor_id']}) {details}")
    await cb.message.edit_text("\n".join(lines), reply_markup=keyboards.back_to_menu())
    await cb.answer()


# --- Ручное добавление расписания ---
@router.callback_query(F.data == "menu:add_schedule")
async def add_sched_start(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)
    await state.set_state(AddSchedule.group)
    await cb.message.edit_text("Шаг 1/8. Введите название группы (например, МЭиТ26-8):")
    await cb.answer()


@router.message(AddSchedule.group, F.text)
async def add_sched_group(message: Message, state: FSMContext):
    await state.update_data(group=message.text.strip())
    await state.set_state(AddSchedule.day)
    await message.answer("Шаг 2/8. Введите день недели (1=Пн, 2=Вт... 7=Вс):")


@router.message(AddSchedule.day, F.text)
async def add_sched_day(message: Message, state: FSMContext):
    try:
        d = int(message.text.strip())
        assert 1 <= d <= 7
    except Exception:
        return await message.answer("Ошибка! Введите число от 1 до 7:")

    await state.update_data(day=d - 1)
    await state.set_state(AddSchedule.time_start)
    await message.answer("Шаг 3/8. Введите ВРЕМЯ НАЧАЛА (например, 10:10):")


@router.message(AddSchedule.time_start, F.text)
async def add_sched_t_start(message: Message, state: FSMContext):
    await state.update_data(time_start=message.text.strip())
    await state.set_state(AddSchedule.time_end)
    await message.answer("Шаг 4/8. Введите ВРЕМЯ ОКОНЧАНИЯ (например, 11:40):")


@router.message(AddSchedule.time_end, F.text)
async def add_sched_t_end(message: Message, state: FSMContext):
    await state.update_data(time_end=message.text.strip())
    await state.set_state(AddSchedule.subject)
    await message.answer("Шаг 5/8. Введите НАЗВАНИЕ ПРЕДМЕТА:")


@router.message(AddSchedule.subject, F.text)
async def add_sched_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(AddSchedule.lesson_type)
    await message.answer("Шаг 6/8. Введите ТИП ЗАНЯТИЯ (Лекция или Практика):")


@router.message(AddSchedule.lesson_type, F.text)
async def add_sched_type(message: Message, state: FSMContext):
    await state.update_data(lesson_type=message.text.strip())
    await state.set_state(AddSchedule.teacher)
    await message.answer("Шаг 7/8. Введите ФАМИЛИЮ ПРЕПОДАВАТЕЛЯ (или '-' если нет):")


@router.message(AddSchedule.teacher, F.text)
async def add_sched_teacher(message: Message, state: FSMContext):
    t = message.text.strip()
    await state.update_data(teacher=t if t != "-" else "")
    await state.set_state(AddSchedule.room)
    await message.answer("Шаг 8/8. Введите АУДИТОРИЮ (например, ЛП49/2/419):")


@router.message(AddSchedule.room, F.text)
async def add_sched_room(message: Message, state: FSMContext, db_user: dict):
    r = message.text.strip()
    data = await state.get_data()

    await schedule.add_schedule(
        day_of_week=data["day"],
        time_start=data["time_start"],
        time_end=data["time_end"],
        subject=data["subject"],
        lesson_type=data["lesson_type"],
        teacher=data["teacher"],
        room=r if r != "-" else "",
        group_name=data["group"]
    )
    await state.clear()
    await message.answer(
        "✅ Занятие успешно добавлено в базу!",
        reply_markup=keyboards.main_menu(db_user["role"])
    )


# --- Назначение группы ---
@router.callback_query(F.data.startswith("usr:group:"))
async def user_group_prompt(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Недостаточно прав", show_alert=True)

    uid = int(cb.data.split(":")[2])
    await state.update_data(target_uid=uid)
    await state.set_state(SetGroupFSM.waiting)

    await cb.message.answer("Введите название группы (или '-' чтобы очистить, /cancel для отмены):")
    await cb.answer()


@router.message(SetGroupFSM.waiting, F.text)
async def user_group_input(message: Message, db_user: dict, state: FSMContext):
    data = await state.get_data()
    group = message.text.strip()
    if group == "-":
        group = ""

    await users.set_group(data["target_uid"], group, db_user["user_id"])
    await state.clear()

    await message.answer(
        f"✅ Группа обновлена: <b>{html.escape(group) or '—'}</b>",
        reply_markup=keyboards.main_menu(db_user["role"]),
    )


# --- Модерация заявок ---
@router.callback_query(F.data.startswith("mod:approve:"))
async def approve_user_handler(cb: CallbackQuery, db_user: dict, bot: Bot):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)

    uid = int(cb.data.split(":")[2])
    await users.approve_user(uid, db_user["user_id"])

    await cb.message.edit_text(f"✅ Пользователь <code>{uid}</code> одобрен.")
    await cb.answer()
    try:
        await bot.send_message(uid, "✅ <b>Ваша заявка одобрена!</b>\nНажмите /start, чтобы войти.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("mod:reject:"))
async def reject_user_handler(cb: CallbackQuery, db_user: dict, bot: Bot):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)

    uid = int(cb.data.split(":")[2])
    await users.reject_user(uid, db_user["user_id"])

    await cb.message.edit_text(f"❌ Пользователь <code>{uid}</code> отклонен и удален.")
    await cb.answer()
    try:
        await bot.send_message(uid, "❌ <b>Ваша заявка отклонена.</b>\nВы не можете пользоваться этим ботом.")
    except Exception:
        pass


@router.callback_query(F.data == "menu:pending")
async def pending_users(cb: CallbackQuery, db_user: dict):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)

    rows = await users.list_pending_users()
    if not rows:
        await cb.message.edit_text("✅ Нет новых заявок.", reply_markup=keyboards.back_to_menu())
        return await cb.answer()

    text = "⏳ <b>Пользователи на модерации:</b>\n\n"
    kb = InlineKeyboardBuilder()
    for r in rows[:20]:
        safe_name = html.escape(r["full_name"])
        safe_user = html.escape(r["username"] or "—")
        text += f"👤 {safe_name} (@{safe_user})\nID: <code>{r['user_id']}</code>\n\n"
        kb.button(text=f"✅ {r['full_name'][:20]}", callback_data=f"mod:approve:{r['user_id']}")
        kb.button(text=f"❌ {r['full_name'][:20]}", callback_data=f"mod:reject:{r['user_id']}")

    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2)
    await cb.message.edit_text(text, reply_markup=kb.as_markup())
    await cb.answer()


@router.message(Command("bind_teacher"))
async def bind_teacher_cmd(message: Message, db_user: dict):
    """Привязывает преподавателя к одной группе и предмету: /bind_teacher <tg_id> <группа> <предмет>"""
    if db_user.get("role") not in ("admin", "owner"):
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4:
        return await message.answer(
            "Использование:\n<code>/bind_teacher ID_пользователя Группа Предмет</code>\n\n"
            "Пример:\n<code>/bind_teacher 123456789 МЭиТ26-8 Китайский</code>"
        )

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.answer("ID пользователя должен быть числом.")

    group_name = parts[2].strip()
    subject = parts[3].strip()

    pool = get_pool()
    async with pool.acquire() as conn:
        updated = await conn.fetchrow(
            """
            UPDATE users
            SET role = 'teacher',
                is_approved = TRUE,
                group_name = $2,
                teacher_subject = $3
            WHERE telegram_id = $1
            RETURNING telegram_id
            """,
            target_id,
            group_name,
            subject,
        )

    if not updated:
        return await message.answer("Пользователь с таким ID не найден в базе (он должен сначала нажать /start).")

    await message.answer(
        f"✅ Преподаватель <code>{target_id}</code> привязан:\n"
        f"• Группа: <b>{group_name}</b>\n"
        f"• Предмет: <b>{subject}</b>"
    )
