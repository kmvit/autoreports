from aiogram.fsm.state import State, StatesGroup

class ReportStates(StatesGroup):
    """Состояния FSM для создания отчетов"""
    select_object = State()
    select_report_type = State()
    select_work_type = State()
    select_work_subtype = State()
    select_time_of_day = State()
    select_actions = State()
    add_itr = State()
    add_workers = State()
    add_equipment = State()
    add_photos = State()
    add_comments = State()
    confirm_report = State()
    edit_report = State()  # Состояние для редактирования отчета
    select_report_to_send = State()  # Выбор отчета для отправки
    select_report_recipient = State()  # Выбор получателя отчета 