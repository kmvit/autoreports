import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from construction_report_bot.database.crud import (
    get_all_objects,
    get_object_by_id,
    create_base_report,
    get_all_itr,
    get_all_workers,
    get_all_equipment,
    get_report_by_id,
    get_report_with_relations,
    create_report
)
from construction_report_bot.database.models import Report, Object, ITR, Worker, Equipment
from construction_report_bot.config.keyboards import (
    get_admin_report_menu_keyboard,
    get_objects_keyboard,
    get_work_type_keyboard,
    get_work_subtype_keyboard,
    get_report_actions_keyboard,
    get_itr_keyboard,
    get_workers_keyboard,
    get_equipment_keyboard,
    get_photos_keyboard,
    get_comments_keyboard,
    get_back_keyboard
)
from construction_report_bot.handlers.admin.report_edit import validate_report_data
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.utils.logging.logger import log_admin_action, log_error
from construction_report_bot.states.report_states import ReportStates
from construction_report_bot.services.report_service import ReportService

logger = logging.getLogger(__name__)

# Создаем роутер для создания отчетов
admin_report_create_router = Router()
# Добавляем middleware для проверки роли
admin_report_create_router.message.middleware(admin_required())
admin_report_create_router.callback_query.middleware(admin_required())

# Словарь с русскими названиями типов работ
WORK_TYPE_NAMES = {
    "report_engineering": "Инженерные коммуникации",
    "report_internal_networks": "Внутриплощадочные сети",
    "report_landscaping": "Благоустройство",
    "report_general_construction": "Общестроительные работы"
}

# Словарь с русскими названиями подтипов работ
WORK_SUBTYPE_NAMES = {
    "subtype_heating": "Отопление",
    "subtype_water": "Водоснабжение и канализация",
    "subtype_fire": "Пожаротушение",
    "subtype_ventilation": "Вентиляция и кондиционирование",
    "subtype_electricity": "Электроснабжение",
    "subtype_low_current": "Слаботочные системы",
    "subtype_nwc": "НВК",
    "subtype_gnb": "Работы с ГНБ",
    "subtype_es": "ЭС",
    "subtype_monolith": "Монолит",
    "subtype_excavation": "Устройство котлована",
    "subtype_dismantling": "Демонтажные работы",
    "subtype_masonry": "Кладочные работы",
    "subtype_facade": "Фасадные работы",
    "subtype_roofing": "Кровельные работы",
    "subtype_finishing": "Отделочные работы",
    "subtype_territory_improvement": "Благоустройство территории",
    "subtype_landscaping": "Озеленение",
    "subtype_paths": "Устройство дорожек",
    "subtype_platforms": "Устройство площадок",
    "subtype_fencing": "Устройство ограждений",
    "subtype_maf": "Устройство малых архитектурных форм"
}

# Обработчик для начала создания отчета
@admin_report_create_router.callback_query(F.data == "create_report")
@error_handler
@with_session
async def create_report_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Начать создание отчета"""
    await callback.answer()
    
    # Добавляем логирование
    log_admin_action("report_creation_attempt", callback.from_user.id, "Попытка создания отчета")
    
    # Получаем список объектов
    objects = await get_all_objects(session)
    if not objects:
        log_admin_action("report_creation_failed", callback.from_user.id, "Нет доступных объектов")
        await callback.message.edit_text(
            "Нет доступных объектов для создания отчета.",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return
        
    log_admin_action("report_creation_started", callback.from_user.id)
    keyboard = await get_objects_keyboard(session)
    await callback.message.edit_text(
        "Выберите объект для отчета:",
        reply_markup=keyboard
    )
    
    # Устанавливаем состояние
    await state.set_state(ReportStates.select_object)

# Обработчик выбора объекта
@admin_report_create_router.callback_query(F.data.startswith("object_"), ReportStates.select_object)
@error_handler
@with_session
async def process_object_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора объекта"""
    await callback.answer()
    
    # Извлекаем ID объекта из callback_data
    object_id = int(callback.data.split("_")[1])
    logging.info(f"[process_object_selection] Получен object_id из callback_data: {object_id}")
    
    # Сохраняем выбранный объект в данных состояния
    await state.update_data(object_id=object_id)
    
    # Проверяем сохранение в состоянии
    state_data = await state.get_data()
    logging.info(f"[process_object_selection] Данные состояния после сохранения: {state_data}")
    
    # Показываем типы работ
    keyboard = get_work_type_keyboard()
    await callback.message.edit_text(
        "Выберите тип работ:",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.select_work_type)

# Обработчик выбора типа работ
@admin_report_create_router.callback_query(F.data.startswith("work_"), ReportStates.select_work_type)
@error_handler
async def process_work_type_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа работ"""
    await callback.answer()
    
    # Сохраняем выбранный тип работ
    work_type = callback.data.replace("work_", "")
    await state.update_data(work_type=work_type)
    
    # Если выбрали "Благоустройство", то подтипа нет, пропускаем этот шаг
    if work_type == "landscaping":
        await state.update_data(work_subtype=None)
        
        # Показываем типы отчетов
        keyboard = get_report_type_keyboard()
        await callback.message.edit_text(
            "Выберите тип отчета:",
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.select_report_type)
    else:
        # В других случаях показываем подтипы работ
        keyboard = await get_work_subtype_keyboard(f"report_{work_type}")
        await callback.message.edit_text("Выберите подтип работ:", reply_markup=keyboard)
        
        # Обновляем состояние
        await state.set_state(ReportStates.select_work_subtype)

# Обработчик выбора подтипа работ
@admin_report_create_router.callback_query(F.data.startswith("subtype_"), ReportStates.select_work_subtype)
@error_handler
async def process_work_subtype_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора подтипа работ"""
    await callback.answer()
    
    # Сохраняем выбранный подтип работ
    work_subtype = callback.data.replace("subtype_", "")
    await state.update_data(work_subtype=work_subtype)
    
    # Показываем типы отчетов
    keyboard = get_report_type_keyboard()
    await callback.message.edit_text(
        "Выберите тип отчета:",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.select_report_type)

# Обработчик выбора типа отчета
@admin_report_create_router.callback_query(F.data.in_(["morning_report", "evening_report"]), ReportStates.select_report_type)
@error_handler
@with_session
async def process_report_type_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора типа отчета"""
    await callback.answer()
    
    # Сохраняем выбранный тип отчета без удаления суффикса _report
    report_type = callback.data
    logging.info(f"[process_report_type_selection] Выбран тип отчета: {report_type}")
    
    # Получаем данные отчета из состояния
    data = await state.get_data()
    logging.info(f"[process_report_type_selection] Данные из состояния перед созданием отчета: {data}")
    
    # Получаем русские названия для типа и подтипа работ
    work_type = data.get('work_type', 'general_construction')
    work_subtype = data.get('work_subtype')
    
    # Преобразуем идентификаторы в русские названия
    work_type_name = WORK_TYPE_NAMES.get(f"report_{work_type}", work_type)
    work_subtype_name = WORK_SUBTYPE_NAMES.get(f"subtype_{work_subtype}", work_subtype) if work_subtype else None
    
    # Валидируем данные перед созданием отчета
    await validate_report_data({
        'object_id': data['object_id'],
        'report_type': work_type_name,
        'type': report_type.replace('_report', ''),  # Убираем суффикс _report
        'itr_list': [],
        'workers_list': [],
        'equipment_list': []
    })
    
    # Создаем базовый отчет
    report = await create_base_report(session, {
        'object_id': data['object_id'],
        'type': report_type.replace('_report', ''),  # morning или evening
        'report_type': work_type_name,  # тип работ
        'work_type': work_type_name,
        'work_subtype': work_subtype_name
    })
    logging.info(f"[process_report_type_selection] Создан базовый отчет с ID: {report.id}")
    
    # Сохраняем ID отчета и инициализируем пустые списки в состоянии
    state_data = {
        'report_id': report.id,
        'object_id': data['object_id'],
        'report_type': work_type_name,  # Используем русское название типа отчета
        'type': report_type.replace('_report', ''),  # Убираем суффикс _report
        'work_type': work_type_name,
        'work_subtype': work_subtype_name,
        'comments': data.get('comments', ''),
        'itr_list': [],
        'workers_list': [],
        'equipment_list': []
    }
    await state.update_data(**state_data)
    
    # Проверяем обновленное состояние
    updated_state = await state.get_data()
    logging.info(f"[process_report_type_selection] Обновленное состояние: {updated_state}")
    
    # Показываем меню действий с отчетом
    keyboard = await get_report_actions_keyboard(report.id)
    
    # Формируем сообщение без использования сложных f-строк
    message = f"✅ Отчет #{report.id} создан.\n\n"
    message += f"Тип работ: {work_type_name}\n"
    
    # Добавляем подтип работ, если он есть
    if work_subtype_name:
        message += f"Подтип работ: {work_subtype_name}\n"
    
    message += "Выберите действие:"
    
    await callback.message.edit_text(
        message,
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.edit_report)

# Обработчик возврата к выбору объекта
@admin_report_create_router.callback_query(F.data == "back_to_object", ReportStates.select_work_type)
@error_handler
@with_session
async def process_back_to_object(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка возврата к выбору объекта"""
    await callback.answer()
    
    # Получаем список объектов
    objects = await get_all_objects(session)
    
    if not objects:
        await callback.message.edit_text(
            "Нет доступных объектов для создания отчета.",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return
    
    # Показываем список объектов
    keyboard = await get_objects_keyboard(session)
    await callback.message.edit_text(
        "Выберите объект для отчета:",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.select_object)

# Обработчик возврата к выбору типа работ
@admin_report_create_router.callback_query(F.data == "back_to_report_type", ReportStates.select_work_subtype)
@error_handler
async def process_back_to_work_type(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к выбору типа работ"""
    await callback.answer()
    
    # Показываем типы работ
    keyboard = get_work_type_keyboard()
    await callback.message.edit_text(
        "Выберите тип работ:",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.select_work_type)

# Функция для получения клавиатуры типов отчетов
def get_report_type_keyboard():
    """Получить клавиатуру для выбора типа отчета"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Утренний", callback_data="morning_report")],
        [InlineKeyboardButton(text="Вечерний", callback_data="evening_report")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")]
    ])
    return keyboard 