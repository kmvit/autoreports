from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.database.crud import (
    get_all_objects, create_object, update_object, delete_object,
    get_object_by_id
)
from construction_report_bot.config.keyboards import (
    get_object_management_keyboard, get_object_back_keyboard
)
from construction_report_bot.utils.decorators import error_handler, extract_id_from_callback, with_session

# Создаем роутер для управления объектами
object_router = Router()

# Добавляем middleware для проверки роли
object_router.message.middleware(admin_required())
object_router.callback_query.middleware(admin_required())

# Состояния FSM для управления объектами
class ObjectManagementStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_client_selection = State()

# Состояния FSM для редактирования объекта
class ObjectEditStates(StatesGroup):
    waiting_for_new_name = State()

# Обработчики управления объектами
@object_router.message(F.text == "🏗️ Управление объектами")
@error_handler
async def cmd_object_management(message: Message):
    """Обработчик команды управления объектами"""
    await message.answer(
        "Управление объектами. Выберите действие:",
        reply_markup=get_object_management_keyboard()
    )

@object_router.callback_query(F.data == "object_list")
@error_handler
@with_session
async def process_object_list(callback: CallbackQuery, session: AsyncSession):
    """Обработка запроса списка объектов"""
    await callback.answer()
    
    # Получаем список объектов
    objects = await get_all_objects(session)
    
    if objects:
        # Формируем текст со списком объектов
        objects_text = "📋 Список объектов:\n\n"
        for i, obj in enumerate(objects, start=1):
            objects_text += f"{i}. {obj.name}\n"
        
        # Добавляем кнопки управления для каждого объекта
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        
        for obj in objects:
            builder.row(
                InlineKeyboardButton(
                    text=f"✏️ {obj.name}",
                    callback_data=f"edit_object_{obj.id}"
                )
            )
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="object_back"))
        
        await callback.message.edit_text(
            objects_text,
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            "Список объектов пуст.",
            reply_markup=get_object_back_keyboard()
        )

@object_router.callback_query(F.data == "object_add")
@error_handler
async def process_object_add(callback: CallbackQuery, state: FSMContext):
    """Обработка запроса на добавление объекта"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Добавление нового объекта.\n"
        "Введите название объекта:"
    )
    
    await state.set_state(ObjectManagementStates.waiting_for_name)

@object_router.message(ObjectManagementStates.waiting_for_name)
@error_handler
@with_session
async def process_object_name(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода названия объекта"""
    name = message.text.strip()
    
    if not name:
        await message.answer("Название объекта не может быть пустым. Введите название объекта:")
        return
    
    # Создаем объект
    await create_object(session, {"name": name})
    
    await message.answer(f"✅ Объект \"{name}\" успешно добавлен!")
    
    # Сбрасываем состояние
    await state.clear()

# Обработчики редактирования объекта
@object_router.callback_query(lambda c: c.data.startswith("edit_object_") and not c.data.startswith("edit_object_name_"))
@error_handler
@with_session
async def process_object_edit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на редактирование объекта"""
    await callback.answer()
    
    # Извлекаем ID объекта из формата "edit_object_ID"
    object_id = extract_id_from_callback(callback.data, "edit_object_")
    
    # Получаем данные объекта
    obj = await get_object_by_id(session, object_id)
    
    if not obj:
        logging.error(f"Объект с ID {object_id} не найден")
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=get_object_back_keyboard()
        )
        return
    
    # Сохраняем ID объекта в состоянии
    await state.update_data(object_id=object_id)
    
    # Создаем клавиатуру для редактирования
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_object_name_{object_id}"),
        InlineKeyboardButton(text="🗑️ Удалить объект", callback_data=f"delete_object_{object_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="object_back"))
    
    # Формируем новый текст сообщения
    new_text = (
        f"Редактирование объекта:\n\n"
        f"Название: {obj.name}\n\n"
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
        await callback.answer("Данные объекта актуальны")

@object_router.callback_query(F.data.startswith("delete_object_"))
@error_handler
async def process_object_delete(callback: CallbackQuery):
    """Обработка запроса на удаление объекта"""
    await callback.answer()
    
    # Извлекаем ID объекта из формата "delete_object_ID"
    object_id = extract_id_from_callback(callback.data, "delete_object_")
    
    # Создаем клавиатуру подтверждения
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_object_{object_id}"),
        InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"edit_object_{object_id}")
    )
    
    try:
        await callback.message.edit_text(
            "⚠️ Вы уверены, что хотите удалить этот объект?\n"
            "Это действие нельзя отменить.",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.")

@object_router.callback_query(F.data.startswith("confirm_delete_object_"))
@error_handler
@with_session
async def confirm_object_delete(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение удаления объекта"""
    await callback.answer()
    
    # Извлекаем ID объекта из формата "confirm_delete_object_ID"
    object_id = extract_id_from_callback(callback.data, "confirm_delete_object_")
    
    # Удаляем объект
    await delete_object(session, object_id)
    
    await callback.message.edit_text(
        "✅ Объект успешно удален.",
        reply_markup=get_object_back_keyboard()
    )

# Обработчики редактирования полей объекта
@object_router.callback_query(F.data.startswith("edit_object_name_"))
@error_handler
@with_session
async def process_edit_object_name(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на изменение названия объекта"""
    await callback.answer()
    
    # Выделяем ID из формата "edit_object_name_ID"
    object_id = extract_id_from_callback(callback.data, "edit_object_name_")
    
    # Проверяем существование объекта
    obj = await get_object_by_id(session, object_id)
    if not obj:
        logging.error(f"Объект с ID {object_id} не найден")
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=get_object_back_keyboard()
        )
        return
    
    await state.update_data(object_id=object_id)
    
    try:
        await callback.message.edit_text(
            "Введите новое название объекта:"
        )
        await state.set_state(ObjectEditStates.waiting_for_new_name)
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, пробуем отправить новое
        await callback.message.answer(
            "Введите новое название объекта:"
        )
        await state.set_state(ObjectEditStates.waiting_for_new_name)

@object_router.message(ObjectEditStates.waiting_for_new_name)
@error_handler
@with_session
async def process_new_object_name(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода нового названия объекта"""
    name = message.text.strip()
    
    if not name:
        await message.answer("Название объекта не может быть пустым. Введите название объекта:")
        return
    
    user_data = await state.get_data()
    object_id = user_data["object_id"]
    
    # Обновляем название объекта
    await update_object(session, object_id, {"name": name})
    
    await message.answer(
        f"✅ Название объекта успешно обновлено на: {name}",
        reply_markup=get_object_back_keyboard()
    )
    
    await state.clear()

@object_router.callback_query(F.data == "object_back")
@error_handler
async def process_object_back(callback: CallbackQuery):
    """Обработка нажатия кнопки Назад в контексте управления объектами"""
    await callback.answer()
    await callback.message.edit_text(
        "Управление объектами. Выберите действие:",
        reply_markup=get_object_management_keyboard()
    )

@object_router.callback_query(F.data == "object_delete")
@error_handler
@with_session
async def process_object_delete_menu(callback: CallbackQuery, session: AsyncSession):
    """Обработка запроса на удаление объекта"""
    await callback.answer()
    
    # Получаем список объектов
    objects = await get_all_objects(session)
    
    if objects:
        # Формируем текст со списком объектов
        objects_text = "🗑️ Выберите объект для удаления:\n\n"
        for i, obj in enumerate(objects, start=1):
            objects_text += f"{i}. {obj.name}\n"
        
        # Добавляем кнопки управления для каждого объекта
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        
        for obj in objects:
            builder.row(
                InlineKeyboardButton(
                    text=f"🗑️ {obj.name}",
                    callback_data=f"delete_object_{obj.id}"
                )
            )
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="object_back"))
        
        await callback.message.edit_text(
            objects_text,
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            "Список объектов пуст.",
            reply_markup=get_object_back_keyboard()
        ) 