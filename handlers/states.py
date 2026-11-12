from aiogram.fsm.state import State, StatesGroup

class AddSchedule(StatesGroup):
    group = State()
    day = State()
    time_start = State()
    time_end = State()
    subject = State()
    lesson_type = State()
    teacher = State()
    room = State()

class SetGroupFSM(StatesGroup):
    waiting = State()

class BanFSM(StatesGroup):
    reason = State()