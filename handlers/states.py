from aiogram.fsm.state import State, StatesGroup

class AddSchedule(StatesGroup):
    group = State()
    day = State()
    time = State()
    subject = State()

class SetGroupFSM(StatesGroup):
    waiting = State()

class BanFSM(StatesGroup):
    reason = State()