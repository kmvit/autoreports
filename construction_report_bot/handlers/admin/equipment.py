from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from construction_report_bot.database.models import Equipment
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import logging

from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.database.crud import (
    get_all_equipment, create_equipment, update_equipment, delete_equipment,
    get_equipment_by_id
)
from construction_report_bot.config.keyboards import (
    get_equipment_management_keyboard, get_back_keyboard, get_equipment_keyboard
)
from construction_report_bot.utils.decorators import error_handler, extract_id_from_callback, with_session

# Создаем роутер для управления техникой
equipment_router = Router()

# Добавляем middleware для проверки роли
equipment_router.message.middleware(admin_required())
equipment_router.callback_query.middleware(admin_required())

# Состояния FSM для управления техникой
class EquipmentManagementStates(StatesGroup):
    waiting_for_name = State()

# Состояния FSM для редактирования техники
class EquipmentEditStates(StatesGroup):
    waiting_for_new_name = State()

# Обработчики управления техникой
@equipment_router.message(F.text == "🚜 Управление техникой")
@error_handler
async def cmd_equipment_management(message: Message):
    """Обработчик команды управления техникой"""
    await message.answer(
        "Управление техникой. Выберите действие:",
        reply_markup=get_equipment_management_keyboard()
    )

@equipment_router.callback_query(F.data == "equipment_list")
@error_handler
@with_session
async def process_equipment_list(callback: CallbackQuery, session: AsyncSession):
    """Обработка запроса списка техники"""
    await callback.answer()
    
    # Получаем список техники
    equipment_list = await get_all_equipment(session)
    
    if equipment_list:
        # Формируем текст со списком техники
        equipment_text = "📋 Список техники:\n\n"
        for i, equipment in enumerate(equipment_list, start=1):
            equipment_text += f"{i}. {equipment.name}\n"
        
        # Добавляем кнопки управления для каждой единицы техники
        builder = InlineKeyboardBuilder()
        
        for equipment in equipment_list:
            builder.row(
                InlineKeyboardButton(
                    text=f"✏️ {equipment.name}",
                    callback_data=f"edit_equipment_{equipment.id}"
                )
            )
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="equipment_back"))
        
        await callback.message.edit_text(
            equipment_text,
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            "Список техники пуст.",
            reply_markup=get_back_keyboard()
        )

@equipment_router.callback_query(F.data == "equipment_add")
@error_handler
async def process_add_equipment(callback: CallbackQuery, state: FSMContext):
    """Обработка нажатия кнопки добавления техники"""
    await state.set_state(EquipmentManagementStates.waiting_for_name)
    await callback.message.edit_text(
        "Введите название техники:",
        reply_markup=get_back_keyboard()
    )

@equipment_router.message(EquipmentManagementStates.waiting_for_name)
@error_handler
@with_session
async def process_equipment_name(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода названия техники"""
    equipment_name = message.text.strip()
    
    if not equipment_name:
        await message.answer("Название техники не может быть пустым. Введите название техники:")
        return
    
    # Создаем новую технику
    new_equipment = Equipment(
        name=equipment_name
    )
    
    session.add(new_equipment)
    await session.commit()
    
    await state.clear()
    await message.answer(
        f"✅ Техника '{equipment_name}' успешно добавлена!",
        reply_markup=get_equipment_management_keyboard()
    )

@equipment_router.callback_query(lambda c: c.data.startswith("edit_equipment_") and not any(x in c.data for x in ["name", "type", "status"]))
@error_handler
@with_session
async def process_equipment_edit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на редактирование техники"""
    await callback.answer()
    
    # Извлекаем ID техники из формата "edit_equipment_ID"
    equipment_id = extract_id_from_callback(callback.data, "edit_equipment_")
    
    # Получаем данные техники
    equipment = await get_equipment_by_id(session, equipment_id)
    
    if not equipment:
        logging.error(f"Техника с ID {equipment_id} не найдена")
        await callback.message.edit_text(
            "Техника не найдена.",
            reply_markup=get_back_keyboard()
        )
        return
    
    # Сохраняем ID техники в состоянии
    await state.update_data(equipment_id=equipment_id)
    
    # Создаем клавиатуру для редактирования
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_equipment_name_{equipment_id}"),
        InlineKeyboardButton(text="🗑️ Удалить технику", callback_data=f"delete_equipment_{equipment_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="equipment_list"))
    
    # Формируем новый текст сообщения
    new_text = (
        f"Редактирование техники:\n\n"
        f"Название: {equipment.name}\n\n"
        f"Выберите действие:"
    )
    
    # Редактируем сообщение
    try:
        await callback.message.edit_text(
            text=new_text,
            reply_markup=builder.as_markup()
        )
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, просто отвечаем пользователю
        await callback.answer("Данные техники актуальны")

@equipment_router.callback_query(F.data.startswith("delete_equipment_"))
@error_handler
async def process_equipment_delete(callback: CallbackQuery):
    """Обработка запроса на удаление техники"""
    await callback.answer()
    
    # Извлекаем ID техники из формата "delete_equipment_ID"
    equipment_id = extract_id_from_callback(callback.data, "delete_equipment_")
    
    # Создаем клавиатуру подтверждения
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_equipment_{equipment_id}"),
        InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"edit_equipment_{equipment_id}")
    )
    
    try:
        await callback.message.edit_text(
            "⚠️ Вы уверены, что хотите удалить эту технику?\n"
            "Это действие нельзя отменить.",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.")

@equipment_router.callback_query(F.data.startswith("confirm_delete_equipment_"))
@error_handler
@with_session
async def confirm_equipment_delete(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение удаления техники"""
    await callback.answer()
    
    # Извлекаем ID техники из формата "confirm_delete_equipment_ID"
    equipment_id = extract_id_from_callback(callback.data, "confirm_delete_equipment_")
    
    # Удаляем технику
    await delete_equipment(session, equipment_id)
    
    await callback.message.edit_text(
        "✅ Техника успешно удалена.",
        reply_markup=get_back_keyboard()
    )

# Обработчики редактирования полей техники
@equipment_router.callback_query(F.data.startswith("edit_equipment_name_"))
@error_handler
@with_session
async def process_edit_equipment_name(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на изменение наименования техники"""
    await callback.answer()
    
    # Выделяем ID из формата "edit_equipment_name_ID"
    equipment_id = extract_id_from_callback(callback.data, "edit_equipment_name_")
    
    # Проверяем существование техники
    equipment = await get_equipment_by_id(session, equipment_id)
    if not equipment:
        logging.error(f"Техника с ID {equipment_id} не найдена")
        await callback.message.edit_text(
            "Техника не найдена.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.update_data(equipment_id=equipment_id)
    
    try:
        await callback.message.edit_text(
            "Введите новое название техники:"
        )
        await state.set_state(EquipmentEditStates.waiting_for_new_name)
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, пробуем отправить новое
        await callback.message.answer(
            "Введите новое название техники:"
        )
        await state.set_state(EquipmentEditStates.waiting_for_new_name)

@equipment_router.message(EquipmentEditStates.waiting_for_new_name)
@error_handler
@with_session
async def process_new_equipment_name(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода нового наименования техники"""
    name = message.text.strip()
    
    if not name:
        await message.answer("Название техники не может быть пустым. Введите название техники:")
        return
    
    user_data = await state.get_data()
    equipment_id = user_data["equipment_id"]
    
    # Обновляем наименование техники
    await update_equipment(session, equipment_id, {"name": name})
    
    await message.answer(
        f"✅ Название техники успешно обновлено на: {name}",
        reply_markup=get_back_keyboard()
    )
    
    await state.clear()

# Настроим обработчик кнопки "Назад" в контексте списка техники
@equipment_router.callback_query(F.data == "equipment_back")
@error_handler
async def process_equipment_back(callback: CallbackQuery):
    """Обработка нажатия кнопки Назад в контексте управления техникой"""
    await callback.answer()
    await callback.message.edit_text(
        "Управление техникой. Выберите действие:",
        reply_markup=get_equipment_management_keyboard()
    )

