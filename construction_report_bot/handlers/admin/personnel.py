from aiogram import Router, F, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.database.models import ITR, Worker
from construction_report_bot.database.crud import (
    get_all_itr, create_itr, update_itr, delete_itr,
    get_all_workers, create_worker, update_worker, delete_worker
)
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.utils.validators import validate_full_name
from construction_report_bot.config.keyboards import get_personnel_management_keyboard, get_admin_menu_keyboard

# Создаем роутер для управления персоналом
personnel_router = Router()

# Добавляем middleware для проверки роли
personnel_router.message.middleware(admin_required())
personnel_router.callback_query.middleware(admin_required())

# Обработчики управления персоналом
@personnel_router.message(F.text == "👷 Управление персоналом")
@personnel_router.message(Command("personnel"))
@error_handler
async def cmd_personnel_management(message: Message):
    """Обработчик команды управления персоналом"""
    await message.answer(
        "Управление персоналом. Выберите действие:",
        reply_markup=get_personnel_management_keyboard()
    )

# Состояния FSM для управления персоналом
class PersonnelManagementStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_position = State()
    waiting_for_type = State()

# Состояния FSM для редактирования сотрудника
class PersonnelEditStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_position = State()

# ============= ФУНКЦИИ ДЛЯ РАБОТЫ С ИТР =============

# Обработчик списка ИТР
@personnel_router.callback_query(F.data == "itr_list")
@error_handler
@with_session
async def process_itr_list(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает список ИТР с возможностью редактирования
    """
    await callback.answer()
    
    # Получаем список ИТР
    itr_list = await get_all_itr(session)

    if not itr_list:
        await callback.message.edit_text(
            "Список ИТР пуст",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="personnel_back"
            ).as_markup()
        )
        return

    text = "📋 Список ИТР:\n\n"
    builder = InlineKeyboardBuilder()

    for itr in itr_list:
        text += f"👤 {itr.full_name}\n\n"
        builder.button(
            text=f"✏️ {itr.full_name}",
            callback_data=f"edit_itr_{itr.id}"
        )

    builder.button(
        text="🔙 Назад",
        callback_data="personnel_back"
    )
    builder.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup()
    )

# Обработчик добавления ИТР
@personnel_router.callback_query(F.data == "itr_add")
@error_handler
async def process_add_itr(callback: CallbackQuery, state: FSMContext):
    """
    Начинает процесс добавления нового ИТР
    """
    await callback.answer()
    
    await state.set_state(PersonnelManagementStates.waiting_for_name)
    await state.update_data(personnel_type="itr")
    await callback.message.edit_text(
        "Введите ФИО нового ИТР:",
        reply_markup=InlineKeyboardBuilder().button(
            text="🔙 Отмена",
            callback_data="personnel_back"
        ).as_markup()
    )

# Обработчик редактирования ИТР
@personnel_router.callback_query(F.data.startswith("edit_itr_"))
@error_handler
@with_session
async def process_edit_itr(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Показывает меню редактирования ИТР
    """
    await callback.answer()
    
    itr_id = int(callback.data.split("_")[-1])
    
    # Проверяем существование ИТР в базе
    itr = await session.get(ITR, itr_id)
    
    if not itr:
        await callback.message.edit_text(
            "ИТР не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="itr_list"
            ).as_markup()
        )
        return
    
    # Сохраняем ID ИТР и текущее имя в состояние
    await state.update_data(personnel_id=itr.id)
    
    # Создаем клавиатуру с опциями редактирования
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить ФИО", callback_data=f"edit_itr_name_{itr.id}"),
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_itr_{itr.id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="itr_list"))
    builder.adjust(1)

    new_text = (
        f"ИТР: {itr.full_name}\n\n"
        f"Выберите действие:"
    )

    try:
        await callback.message.edit_text(
            text=new_text,
            reply_markup=builder.as_markup()
        )
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, просто отвечаем пользователю
        await callback.message.answer("Данные ИТР актуальны")


# Обработчик кнопки изменения имени ИТР
@personnel_router.callback_query(F.data.startswith("edit_itr_name_"))
@error_handler
@with_session 
async def process_edit_itr_name_button(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик нажатия на кнопку изменения имени ИТР"""
    logging.info(f"--- Start process_edit_itr_name_button --- Callback: {callback.data}")
    print(f"--- Start process_edit_itr_name_button --- Callback: {callback.data}")
    
    await callback.answer()
    
    try:
        logging.info("Получение данных из состояния")
        print("Получение данных из состояния")
        user_data = await state.get_data()
        logging.info(f"Данные из состояния: {user_data}")
        print(f"Данные из состояния: {user_data}")
        
        current_name = user_data.get("current_name", "")
        personnel_id = user_data.get("personnel_id")
        personnel_type = user_data.get("personnel_type") # Добавим тип для логирования
        
        logging.info(f"Извлеченные данные: personnel_id={personnel_id}, current_name='{current_name}', personnel_type='{personnel_type}'")
        print(f"Извлеченные данные: personnel_id={personnel_id}, current_name='{current_name}', personnel_type='{personnel_type}'")
        
        if not personnel_id:
            logging.warning("Ошибка: personnel_id не найден в состоянии")
            print("Ошибка: personnel_id не найден в состоянии")
            await callback.message.edit_text(
                "Ошибка: не найден ID сотрудника",
                reply_markup=InlineKeyboardBuilder().button(
                    text="🔙 Назад",
                    callback_data="itr_list"
                ).as_markup()
            )
            return
            
        # Проверка ИТР в БД 
        logging.info(f"Проверка ИТР с ID {personnel_id} в БД")
        print(f"Проверка ИТР с ID {personnel_id} в БД")
        itr = await session.get(ITR, int(personnel_id))
        if not itr:
            logging.warning(f"ИТР с ID {personnel_id} не найден в БД")
            print(f"ИТР с ID {personnel_id} не найден в БД")
            await callback.message.edit_text(
                "ИТР не найден. Возможно, он был удален.",
                reply_markup=InlineKeyboardBuilder().button(
                    text="🔙 Назад",
                    callback_data="itr_list"
                ).as_markup()
            )
            return
        logging.info(f"ИТР {personnel_id} найден в БД")
        print(f"ИТР {personnel_id} найден в БД")

        # Убедимся, что тип персонала установлен как "itr"
        logging.info("Обновление personnel_type в состоянии на 'itr'")
        print("Обновление personnel_type в состоянии на 'itr'")
        await state.update_data(personnel_type="itr")
        
        logging.info("Установка состояния PersonnelEditStates.waiting_for_new_name")
        print("Установка состояния PersonnelEditStates.waiting_for_new_name")
        await state.set_state(PersonnelEditStates.waiting_for_new_name)
        
        logging.info("Отправка сообщения с запросом нового имени")
        print("Отправка сообщения с запросом нового имени")
        await callback.message.edit_text(
            f"Текущее ФИО: {current_name}\n\n"
            f"Введите новое ФИО ИТР:",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Отмена",
                callback_data="itr_list"
            ).as_markup()
        )
        logging.info("--- End process_edit_itr_name_button ---")
        print("--- End process_edit_itr_name_button ---")
        
    except Exception as e:
        logging.error(f"Ошибка в process_edit_itr_name_button: {e}", exc_info=True)
        print(f"ОШИБКА в process_edit_itr_name_button: {e}")
        await callback.message.edit_text("Произошла внутренняя ошибка при обработке вашего запроса.")
        await state.clear() # Очищаем состояние в случае ошибки

# Обработчик кнопки удаления ИТР
@personnel_router.callback_query(F.data.startswith("delete_itr_"))
@error_handler
@with_session
async def process_delete_itr(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик кнопки удаления ИТР"""
    await callback.answer()
    
    user_data = await state.get_data()
    personnel_id = user_data.get("personnel_id")
    
    if not personnel_id:
        await callback.message.edit_text(
            "Ошибка: не найден ID сотрудника",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="itr_list"
            ).as_markup()
        )
        return
    
    try:
        # Проверяем существование ИТР
        itr = await session.get(ITR, personnel_id)
        if not itr:
            await callback.message.edit_text(
                "ИТР не найден. Возможно, он был удален.",
                reply_markup=InlineKeyboardBuilder().button(
                    text="🔙 Назад",
                    callback_data="itr_list"
                ).as_markup()
            )
            return
        
        # Удаляем ИТР
        await delete_itr(session, personnel_id)
        
        await callback.message.edit_text(
            f"✅ ИТР {itr.full_name} успешно удален",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К списку ИТР",
                callback_data="itr_list"
            ).as_markup()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при удалении ИТР: {e}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при удалении ИТР",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="itr_list"
            ).as_markup()
        )

# ============= ФУНКЦИИ ДЛЯ РАБОТЫ С РАБОЧИМИ =============

# Обработчик списка рабочих
@personnel_router.callback_query(F.data == "worker_list")
@error_handler
@with_session
async def process_workers_list(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает список рабочих с возможностью редактирования
    """
    await callback.answer()
    
    workers_list = await get_all_workers(session)

    if not workers_list:
        await callback.message.edit_text(
            "Список рабочих пуст",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="personnel_back"
            ).as_markup()
        )
        return

    text = "📋 Список рабочих:\n\n"
    builder = InlineKeyboardBuilder()

    for worker in workers_list:
        text += f"👤 {worker.full_name}\n📝 Должность: {worker.position}\n\n"
        builder.button(
            text=f"✏️ {worker.full_name}",
            callback_data=f"edit_worker_{worker.id}"
        )

    builder.button(
        text="🔙 Назад",
        callback_data="personnel_back"
    )
    builder.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup()
    )

# Обработчик добавления рабочего
@personnel_router.callback_query(F.data == "worker_add")
@error_handler
async def process_add_worker(callback: CallbackQuery, state: FSMContext):
    """
    Начинает процесс добавления нового рабочего
    """
    await callback.answer()
    
    await state.set_state(PersonnelManagementStates.waiting_for_name)
    await state.update_data(personnel_type="worker")
    await callback.message.edit_text(
        "Введите ФИО нового рабочего:",
        reply_markup=InlineKeyboardBuilder().button(
            text="🔙 Отмена",
            callback_data="personnel_back"
        ).as_markup()
    )

# Обработчик редактирования рабочего
@personnel_router.callback_query(F.data.startswith("edit_worker_"))
@error_handler
@with_session
async def process_edit_worker(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Показывает меню редактирования рабочего
    """
    await callback.answer()
    
    worker_id = int(callback.data.split("_")[-1])
    
    # Проверяем существование рабочего в базе
    worker = await session.get(Worker, worker_id)
    if not worker:
        await callback.message.edit_text(
            "Рабочий не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="worker_list"
            ).as_markup()
        )
        return
    
    await state.update_data(
        personnel_id=worker_id,
        personnel_type="worker",
        current_name=worker.full_name,
        current_position=worker.position
    )
    
    # Создаем клавиатуру с опциями редактирования
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить ФИО", callback_data="edit_worker_name")
    builder.button(text="✏️ Изменить должность", callback_data="edit_worker_position")
    builder.button(text="🗑️ Удалить", callback_data="delete_worker")
    builder.button(text="🔙 Назад", callback_data="worker_list")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"Рабочий: {worker.full_name}\n"
        f"Должность: {worker.position}\n\n"
        f"Выберите действие:",
        reply_markup=builder.as_markup()
    )

# Обработчик кнопки изменения имени рабочего
@personnel_router.callback_query(F.data == "edit_worker_name")
@error_handler
async def process_edit_worker_name_button(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку изменения имени рабочего"""
    await callback.answer()
    
    user_data = await state.get_data()
    current_name = user_data.get("current_name", "")
    
    await state.set_state(PersonnelEditStates.waiting_for_new_name)
    
    await callback.message.edit_text(
        f"Текущее ФИО: {current_name}\n\n"
        f"Введите новое ФИО рабочего:",
        reply_markup=InlineKeyboardBuilder().button(
            text="🔙 Отмена",
            callback_data="worker_list"
        ).as_markup()
    )

# Обработчик кнопки изменения должности рабочего
@personnel_router.callback_query(F.data == "edit_worker_position")
@error_handler
async def process_edit_worker_position_button(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку изменения должности рабочего"""
    await callback.answer()
    
    user_data = await state.get_data()
    current_position = user_data.get("current_position", "")
    
    await state.set_state(PersonnelEditStates.waiting_for_new_position)
    
    await callback.message.edit_text(
        f"Текущая должность: {current_position}\n\n"
        f"Введите новую должность рабочего:",
        reply_markup=InlineKeyboardBuilder().button(
            text="🔙 Отмена",
            callback_data="worker_list"
        ).as_markup()
    )

# Обработчик кнопки удаления рабочего
@personnel_router.callback_query(F.data == "delete_worker")
@error_handler
@with_session
async def process_delete_worker(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик кнопки удаления рабочего"""
    await callback.answer()
    
    user_data = await state.get_data()
    personnel_id = user_data.get("personnel_id")
    
    if not personnel_id:
        await callback.message.edit_text(
            "Ошибка: не найден ID сотрудника",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="worker_list"
            ).as_markup()
        )
        return
    
    try:
        # Проверяем существование рабочего
        worker = await session.get(Worker, personnel_id)
        if not worker:
            await callback.message.edit_text(
                "Рабочий не найден. Возможно, он был удален.",
                reply_markup=InlineKeyboardBuilder().button(
                    text="🔙 Назад",
                    callback_data="worker_list"
                ).as_markup()
            )
            return
        
        # Удаляем рабочего
        await delete_worker(session, personnel_id)
        
        await callback.message.edit_text(
            f"✅ Рабочий {worker.full_name} успешно удален",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К списку рабочих",
                callback_data="worker_list"
            ).as_markup()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при удалении рабочего: {e}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при удалении рабочего",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Назад",
                callback_data="worker_list"
            ).as_markup()
        )

# ============= ОБЩИЕ ФУНКЦИИ =============

# Обработчик ввода имени нового сотрудника
@personnel_router.message(PersonnelManagementStates.waiting_for_name)
@error_handler
@with_session
async def process_personnel_name(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обработчик ввода имени нового сотрудника
    """
    try:
        if not validate_full_name(message.text):
            await message.answer("❌ Неверный формат ФИО. Пожалуйста, введите ФИО в формате 'Фамилия Имя Отчество' или 'Фамилия И.О.'")
            return

        name = message.text.strip()
        user_data = await state.get_data()
        personnel_type = user_data.get("personnel_type", "")
        
        logging.info(f"Получено имя сотрудника: {name}, тип: {personnel_type}")
        print(f"Получено имя сотрудника: {name}, тип: {personnel_type}")
        if personnel_type == "itr":
            # Для ИТР создаем сразу, без запроса должности
            itr_data = {
                "full_name": name
            }
            itr = await create_itr(session, itr_data)
            await message.answer(
                f"✅ ИТР успешно добавлен:\n\n"
                f"👤 ФИО: {itr.full_name}"
            )
            await state.clear()
            await cmd_personnel_management(message)
        elif personnel_type == "worker":
            # Для рабочего сохраняем имя и запрашиваем должность
            await state.update_data(name=name)
            await state.set_state(PersonnelManagementStates.waiting_for_position)
            await message.answer("Введите должность рабочего:")
        else:
            await message.answer("❌ Ошибка: неизвестный тип сотрудника")
            logging.error(f"Неизвестный тип сотрудника: {personnel_type}")
            await state.clear()
            await cmd_personnel_management(message)
            
    except Exception as e:
        logging.error(f"Ошибка при обработке имени сотрудника: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке имени сотрудника. Пожалуйста, попробуйте снова.")
        await state.clear()
        await cmd_personnel_management(message)

# Обработчик ввода должности нового рабочего
@personnel_router.message(PersonnelManagementStates.waiting_for_position)
@error_handler
@with_session
async def process_personnel_position(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обработка ввода должности нового рабочего
    """
    try:
        position = message.text.strip()
        
        if not position:
            await message.answer("❌ Должность не может быть пустой. Введите должность рабочего:")
            return
        
        user_data = await state.get_data()
        name = user_data.get("name", "")
        
        if not name:
            await message.answer("❌ Ошибка: имя рабочего не найдено")
            await state.clear()
            await cmd_personnel_management(message)
            return
        
        logging.info(f"Добавление рабочего: Имя={name}, Должность={position}")
        
        # Создаем рабочего с должностью
        worker_data = {
            "full_name": name,
            "position": position
        }
        worker = await create_worker(session, worker_data)
        await message.answer(
            f"✅ Рабочий успешно добавлен:\n\n"
            f"👤 ФИО: {worker.full_name}\n"
            f"📝 Должность: {worker.position}"
        )
        
        await state.clear()
        await cmd_personnel_management(message)
        
    except Exception as e:
        logging.error(f"Ошибка при добавлении рабочего: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при добавлении рабочего. Пожалуйста, попробуйте снова.")
        await state.clear()
        await cmd_personnel_management(message)

# Обработчик ввода нового имени сотрудника
@personnel_router.message(PersonnelEditStates.waiting_for_new_name)
@error_handler
@with_session
async def process_new_personnel_name(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обработка ввода нового имени сотрудника
    """
    try:
        name = message.text.strip()
        
        if not validate_full_name(name):
            await message.answer(
                "Неверный формат ФИО. Пожалуйста, введите корректное ФИО "
                "(например: Иванов Иван Иванович или Иванов И.И.):"
            )
            return
        
        user_data = await state.get_data()
        personnel_id = user_data.get("personnel_id")
        personnel_type = user_data.get("personnel_type", "")
        
        if not personnel_id:
            await message.answer("Ошибка: не найден ID сотрудника")
            await state.clear()
            await cmd_personnel_management(message)
            return
        
        try:
            personnel_id = int(personnel_id)
        except (ValueError, TypeError):
            await message.answer("Ошибка: неверный формат ID сотрудника")
            await state.clear()
            await cmd_personnel_management(message)
            return
        
        if personnel_type == "itr":
            # Обновляем ИТР
            itr_data = {"full_name": name}
            await update_itr(session, personnel_id, itr_data)
            await message.answer(f"✅ ФИО ИТР успешно обновлено на: {name}")
            await state.clear()
            await cmd_personnel_management(message)
        elif personnel_type == "worker":
            # Обновляем имя рабочего
            worker_data = {"full_name": name}
            await update_worker(session, personnel_id, worker_data)
            await message.answer(f"✅ ФИО рабочего успешно обновлено на: {name}")
            await state.clear()
            await cmd_personnel_management(message)
        else:
            await message.answer("Ошибка: неизвестный тип сотрудника")
            await state.clear()
            await cmd_personnel_management(message)
        
    except Exception as e:
        logging.error(f"Ошибка при обновлении ФИО сотрудника: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обновлении ФИО. Пожалуйста, попробуйте снова.")
        await state.clear()
        await cmd_personnel_management(message)

# Обработчик ввода новой должности рабочего
@personnel_router.message(PersonnelEditStates.waiting_for_new_position)
@error_handler
@with_session
async def process_new_personnel_position(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обработка ввода новой должности рабочего
    """
    try:
        position = message.text.strip()
        
        if not position:
            await message.answer("Должность не может быть пустой. Введите должность рабочего:")
            return
        
        user_data = await state.get_data()
        personnel_id = user_data.get("personnel_id")
        personnel_type = user_data.get("personnel_type", "")
        
        if not personnel_id:
            await message.answer("Ошибка: не найден ID сотрудника")
            await state.clear()
            await cmd_personnel_management(message)
            return
        
        if personnel_type == "worker":
            # Проверяем, редактируем только имя или имя и должность
            if "new_name" in user_data:
                # Обновляем и имя, и должность
                new_name = user_data.get("new_name")
                await update_worker(session, personnel_id, {"full_name": new_name, "position": position})
                await message.answer(
                    f"✅ Данные рабочего успешно обновлены:\n"
                    f"👤 ФИО: {new_name}\n"
                    f"📝 Должность: {position}"
                )
            else:
                # Обновляем только должность
                worker = await session.get(Worker, personnel_id)
                if not worker:
                    await message.answer("Рабочий не найден. Возможно, он был удален.")
                    await state.clear()
                    await cmd_personnel_management(message)
                    return
                
                await update_worker(session, personnel_id, {"position": position})
                await message.answer(
                    f"✅ Должность рабочего {worker.full_name} успешно обновлена на: {position}"
                )
        else:
            await message.answer("Ошибка: неверный тип сотрудника для обновления должности")
        
        await state.clear()
        await cmd_personnel_management(message)
        
    except Exception as e:
        logging.error(f"Ошибка при обновлении должности рабочего: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обновлении должности. Пожалуйста, попробуйте снова.")
        await state.clear()
        await cmd_personnel_management(message)

# ============= ОБРАБОТЧИКИ НАВИГАЦИИ =============

# Настроим обработчик кнопки "Назад" в контексте списка персонала
@personnel_router.callback_query(F.data == "personnel_back")
@error_handler
async def process_personnel_back(callback: CallbackQuery):
    """Обработка нажатия кнопки Назад в контексте управления персоналом"""
    await callback.answer()
    await callback.message.edit_text(
        "Управление персоналом. Выберите действие:",
        reply_markup=get_personnel_management_keyboard()
    )

# Обработчик кнопки "Назад" для возврата в админ-меню
@personnel_router.callback_query(F.data == "admin_back")
@error_handler
async def process_admin_back(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки Назад для возврата в админ-меню"""
    await callback.answer()
    await state.clear()
    
    # Возвращаемся в админ-меню
    from construction_report_bot.config.keyboards import get_admin_keyboard
    await callback.message.edit_text(
        "Выберите раздел административной панели:",
        reply_markup=await get_admin_keyboard()
    )