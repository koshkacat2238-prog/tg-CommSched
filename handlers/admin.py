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
from ui.formaters import format_user_card

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


# 1. Ловим нажатие кнопки в меню
@router.callback_query(F.data == "menu:add_schedule")
async def add_sched_start(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Нет прав", show_alert=True)

    # Включаем ожидание первого ответа
    await state.set_state(AddSchedule.group)
    await cb.message.edit_text("Шаг 1/8. Введите название группы (например, МЭиТ26-8):")


# 2. Получаем группу и спрашиваем день
@router.message(AddSchedule.group)
async def add_sched_group(message: Message, state: FSMContext):
    await state.update_data(group=message.text.strip())  # Сохраняем в память
    await state.set_state(AddSchedule.day)  # Переключаем состояние
    await message.answer("Шаг 2/8. Введите день недели (1=Пн, 2=Вт... 7=Вс):")


# 3. Получаем день и спрашиваем время начала
@router.message(AddSchedule.day)
async def add_sched_day(message: Message, state: FSMContext):
    try:
        d = int(message.text.strip())
        assert 1 <= d <= 7
    except:
        return await message.answer("Ошибка! Введите число от 1 до 7:")

    await state.update_data(day=d - 1)  # В базе дни от 0 до 6
    await state.set_state(AddSchedule.time_start)
    await message.answer("Шаг 3/8. Введите ВРЕМЯ НАЧАЛА (например, 10:10):")


# 4. Получаем время начала и спрашиваем время конца
@router.message(AddSchedule.time_start)
async def add_sched_t_start(message: Message, state: FSMContext):
    await state.update_data(time_start=message.text.strip())
    await state.set_state(AddSchedule.time_end)
    await message.answer("Шаг 4/8. Введите ВРЕМЯ ОКОНЧАНИЯ (например, 11:40):")


# 5. Получаем время конца и спрашиваем предмет
@router.message(AddSchedule.time_end)
async def add_sched_t_end(message: Message, state: FSMContext):
    await state.update_data(time_end=message.text.strip())
    await state.set_state(AddSchedule.subject)
    await message.answer("Шаг 5/8. Введите НАЗВАНИЕ ПРЕДМЕТА:")


# 6. Получаем предмет и спрашиваем тип
@router.message(AddSchedule.subject)
async def add_sched_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(AddSchedule.lesson_type)
    await message.answer("Шаг 6/8. Введите ТИП ЗАНЯТИЯ (Лекция или Практика):")


# 7. Получаем тип и спрашиваем преподавателя
@router.message(AddSchedule.lesson_type)
async def add_sched_type(message: Message, state: FSMContext):
    await state.update_data(lesson_type=message.text.strip())
    await state.set_state(AddSchedule.teacher)
    await message.answer("Шаг 7/8. Введите ФАМИЛИЮ ПРЕПОДАВАТЕЛЯ (или '-' если нет):")


# 8. Получаем преподавателя и спрашиваем аудиторию
@router.message(AddSchedule.teacher)
async def add_sched_teacher(message: Message, state: FSMContext):
    t = message.text.strip()
    await state.update_data(teacher=t if t != "-" else "")
    await state.set_state(AddSchedule.room)
    await message.answer("Шаг 8/8. Введите АУДИТОРИЮ (например, ЛП49/2/419):")


# 9. Получаем аудиторию, собираем все данные и сохраняем в БД
@router.message(AddSchedule.room)
async def add_sched_room(message: Message, state: FSMContext, db_user: dict):
    r = message.text.strip()

    # Достаем ВСЕ данные, которые накопили за предыдущие 7 шагов
    data = await state.get_data()

    # Отправляем в сервис (в базу данных)
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

    # Очищаем память (выходим из режима добавления)
    await state.clear()

    await message.answer(
        "✅ Занятие успешно добавлено в базу!",
        reply_markup=keyboards.main_menu(db_user["role"])
    )

# --- НАЗНАЧЕНИЕ ГРУППЫ ---
@router.callback_query(F.data.startswith("usr:group:"))
async def user_group_prompt(cb: CallbackQuery, db_user: dict, state: FSMContext):
    if db_user["role"] not in ADMIN_ROLES:
        return await cb.answer("Недостаточно прав", show_alert=True)

    uid = int(cb.data.split(":")[2])
    await state.update_data(target_uid=uid)
    await state.set_state(SetGroupFSM.waiting)  # Включаем режим ожидания текста

    await cb.message.answer("Введите название группы (или '-' чтобы очистить, /cancel для отмены):")
    await cb.answer()


@router.message(SetGroupFSM.waiting)
async def user_group_input(message: Message, db_user: dict, state: FSMContext):
    # Этот хендлер сработает, когда вы напишете текст, пока бот в состоянии SetGroupFSM.waiting
    data = await state.get_data()
    group = message.text.strip()
    if group == "-":
        group = ""

    await users.set_group(data["target_uid"], group, db_user["user_id"])
    await state.clear()  # Выключаем режим ожидания

    await message.answer(
        f"✅ Группа обновлена: <b>{group or '—'}</b>",
        reply_markup=keyboards.main_menu(db_user["role"]),
    )