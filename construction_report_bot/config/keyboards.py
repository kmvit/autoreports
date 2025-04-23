from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any

from construction_report_bot.database.models import ITR, Worker, Equipment

# Общие клавиатуры
def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Основное меню для всех пользователей"""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📊 История отчетов"), KeyboardButton(text="📑 Отчет за сегодня"))
    return builder.as_markup(resize_keyboard=True)

# Клавиатуры для администратора
def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Расширенное меню администратора"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="👥 Управление заказчиками"),
        KeyboardButton(text="🏗️ Управление объектами")
    )
    builder.row(
        KeyboardButton(text="👷 Управление персоналом"),
        KeyboardButton(text="🚜 Управление техникой")
    )
    builder.row(KeyboardButton(text="📝 Управление отчетами"))
    return builder.as_markup(resize_keyboard=True)

def get_client_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления заказчиками"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Список заказчиков", callback_data="client_list"),
        InlineKeyboardButton(text="➕ Добавить заказчика", callback_data="client_add")
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить", callback_data="client_delete"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    )
    return builder.as_markup()

def get_object_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления объектами"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Список объектов", callback_data="object_list"),
        InlineKeyboardButton(text="➕ Добавить объект", callback_data="object_add")
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить объект", callback_data="object_delete")
    )
    return builder.as_markup()

def get_personnel_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления персоналом"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Список ИТР", callback_data="itr_list"),
        InlineKeyboardButton(text="➕ Добавить ИТР", callback_data="itr_add")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список рабочих", callback_data="worker_list"),
        InlineKeyboardButton(text="➕ Добавить рабочего", callback_data="worker_add")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))
    return builder.as_markup()

def get_equipment_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления техникой"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Список техники", callback_data="equipment_list"),
        InlineKeyboardButton(text="➕ Добавить технику", callback_data="equipment_add")
    )
    return builder.as_markup()

def get_report_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа отчета"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌅 Утренний отчет", callback_data="morning_report"),
        InlineKeyboardButton(text="🌆 Вечерний отчет", callback_data="evening_report")
    )
    return builder.as_markup()

# Клавиатуры для заказчика
def get_report_filter_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для фильтрации отчетов"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 По дате", callback_data="filter_date"),
        InlineKeyboardButton(text="🏗️ По объекту", callback_data="filter_object")
    )
    builder.row(
        InlineKeyboardButton(text="🌅/🌆 По типу отчета", callback_data="filter_report_type"),
        InlineKeyboardButton(text="🔍 Сбросить фильтры", callback_data="filter_reset")
    )
    return builder.as_markup()

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
    return builder.as_markup()

def get_object_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад для объектов"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="object_back"))
    return builder.as_markup()

# Дополнительные клавиатуры для администратора
async def get_admin_report_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню администратора для отчетов"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 Создать отчет", callback_data="create_report"),
        InlineKeyboardButton(text="📋 Мои отчеты", callback_data="my_reports")
    )
    builder.row(
        InlineKeyboardButton(text="📤 Отправить отчет", callback_data="send_report"),
        InlineKeyboardButton(text="📊 Экспорт отчетов", callback_data="export_report")
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main"))
    return builder.as_markup()

async def get_objects_keyboard(session: AsyncSession) -> InlineKeyboardMarkup:
    """Клавиатура выбора объекта"""
    from construction_report_bot.database.crud import get_all_objects
    
    objects = await get_all_objects(session)
    builder = InlineKeyboardBuilder()
    
    for obj in objects:
        builder.row(InlineKeyboardButton(text=obj.name, callback_data=f"object_{obj.id}"))
    
    builder.row(InlineKeyboardButton(text="Назад", callback_data="back"))
    return builder.as_markup()

async def get_work_subtype_keyboard(report_type: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора подтипа работ"""
    builder = InlineKeyboardBuilder()
    
    subtypes = {
        "report_engineering": [
            ["Отопление", "subtype_heating"],
            ["Водоснабжение и канализация", "subtype_water"],
            ["Пожаротушение", "subtype_fire"],
            ["Вентиляция и кондиционирование", "subtype_ventilation"],
            ["Электроснабжение", "subtype_electricity"],
            ["Слаботочные системы", "subtype_low_current"]
        ],
        "report_internal_networks": [
            ["НВК", "subtype_nwc"],
            ["Работы с ГНБ", "subtype_gnb"],
            ["ЭС", "subtype_es"]
        ],
        "report_general_construction": [
            ["Монолит", "subtype_monolith"],
            ["Устройство котлована", "subtype_excavation"],
            ["Демонтажные работы", "subtype_dismantling"],
            ["Кладочные работы", "subtype_masonry"],
            ["Фасадные работы", "subtype_facade"],
            ["Кровельные работы", "subtype_roofing"],
            ["Отделочные работы", "subtype_finishing"]
        ]
    }
    
    if report_type in subtypes:
        for subtype in subtypes[report_type]:
            builder.row(InlineKeyboardButton(text=subtype[0], callback_data=subtype[1]))
    
    builder.row(InlineKeyboardButton(text="Назад", callback_data="back_to_report_type"))
    return builder.as_markup()


async def get_report_actions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура действий с отчетом"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Добавить ИТР", callback_data="add_itr"))
    builder.row(InlineKeyboardButton(text="Добавить рабочих", callback_data="add_workers"))
    builder.row(InlineKeyboardButton(text="Добавить технику", callback_data="add_equipment"))
    builder.row(InlineKeyboardButton(text="Добавить фотографии", callback_data="add_photos"))
    builder.row(InlineKeyboardButton(text="Добавить комментарии", callback_data="add_comments"))
    builder.row(InlineKeyboardButton(text="Сохранить отчет", callback_data="save_report"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_report"))
    return builder.as_markup()

async def get_itr_keyboard(itr_list: List[ITR], selected_ids: List[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора ИТР"""
    builder = InlineKeyboardBuilder()
    
    for itr in itr_list:
        # Добавляем галочку, если ИТР уже выбран
        text = f"{'✅ ' if selected_ids and itr.id in selected_ids else ''}{itr.full_name}"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"itr_{itr.id}"))
    
    builder.row(InlineKeyboardButton(text="Назад", callback_data="back_to_actions"))
    return builder.as_markup()

async def get_workers_keyboard(workers_list: List[Worker], selected_ids: List[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора рабочих"""
    builder = InlineKeyboardBuilder()
    
    for worker in workers_list:
        # Добавляем галочку, если рабочий уже выбран
        text = f"{'✅ ' if selected_ids and worker.id in selected_ids else ''}{worker.full_name} ({worker.position})"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"worker_{worker.id}"))
    
    builder.row(InlineKeyboardButton(text="Готово", callback_data="workers_done"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data="back_to_actions"))
    return builder.as_markup()

async def get_equipment_keyboard(equipment_list: List[Equipment], selected_ids: List[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора техники"""
    builder = InlineKeyboardBuilder()
    
    for equipment in equipment_list:
        # Добавляем галочку, если техника уже выбрана
        text = f"{'✅ ' if selected_ids and equipment.id in selected_ids else ''}{equipment.name}"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"equipment_{equipment.id}"))
    
    builder.row(InlineKeyboardButton(text="Готово", callback_data="equipment_done"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data="back_to_actions"))
    return builder.as_markup()

async def get_photos_keyboard(photos: List[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура для работы с фотографиями"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Готово", callback_data="photos_done"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="back_to_actions"))
    return builder.as_markup()

async def get_comments_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для работы с комментариями"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="back_to_actions"))
    return builder.as_markup()

async def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для возврата в административное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Вернуться в админ-панель", callback_data="admin_back"))
    return builder.as_markup()

def get_work_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа работ"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Инженерные коммуникации", callback_data="work_engineering"))
    builder.row(InlineKeyboardButton(text="Внутриплощадочные сети", callback_data="work_internal_networks"))
    builder.row(InlineKeyboardButton(text="Благоустройство", callback_data="work_landscaping"))
    builder.row(InlineKeyboardButton(text="Общестроительные работы", callback_data="work_general_construction"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data="back_to_object"))
    return builder.as_markup() 