from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.database.crud import (
    get_all_clients, get_all_objects, create_object, update_object, delete_object,
    get_object_by_id, get_client_by_id
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
    waiting_for_client_selection = State()

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
        
        from sqlalchemy import text
        
        for i, obj in enumerate(objects, start=1):
            # Получаем заказчиков для каждого объекта
            query = text("""
                SELECT c.full_name, c.organization
                FROM clients c
                JOIN client_objects co ON c.id = co.client_id
                WHERE co.object_id = :object_id
            """)
            result = await session.execute(query, {"object_id": obj.id})
            clients = result.fetchall()
            
            # Добавляем информацию о заказчиках
            objects_text += f"{i}. {obj.name}\n"
            if clients:
                client_info = ", ".join([f"{client.full_name} ({client.organization})" for client in clients])
                objects_text += f"   📌 Заказчик: {client_info}\n"
            else:
                objects_text += f"   📌 Заказчик: не назначен\n"
            objects_text += "\n"
        
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
    
    # Сохраняем название объекта в состоянии
    await state.update_data(object_name=name)
    
    # Получаем список заказчиков
    clients = await get_all_clients(session)
    
    if clients:
        # Формируем текст со списком заказчиков
        clients_text = "📋 Выберите заказчика для объекта:\n\n"
        for i, client in enumerate(clients, start=1):
            clients_text += f"{i}. {client.full_name} ({client.organization})\n"
        
        # Создаем клавиатуру для выбора заказчика
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        
        for client in clients:
            builder.row(
                InlineKeyboardButton(
                    text=f"✅ {client.full_name}",
                    callback_data=f"select_client_{client.id}"
                )
            )
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="object_back"))
        
        await message.answer(
            clients_text,
            reply_markup=builder.as_markup()
        )
        
        # Переходим к ожиданию выбора заказчика
        await state.set_state(ObjectManagementStates.waiting_for_client_selection)
    else:
        await message.answer(
            "Список заказчиков пуст. Сначала добавьте заказчиков.",
            reply_markup=get_object_back_keyboard()
        )
        # Сбрасываем состояние
        await state.clear()

@object_router.callback_query(lambda c: c.data.startswith("select_client_"))
@error_handler
@with_session
async def process_client_selection_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора заказчика через callback"""
    await callback.answer()
    
    # Извлекаем ID заказчика из формата "select_client_ID"
    client_id = extract_id_from_callback(callback.data, "select_client_")
    
    # Получаем данные из состояния
    data = await state.get_data()
    object_name = data.get("object_name")
    
    if not object_name:
        await callback.message.edit_text(
            "Произошла ошибка: название объекта не найдено.",
            reply_markup=get_object_back_keyboard()
        )
        await state.clear()
        return
    
    try:
        # Создаем объект только с названием
        new_object = await create_object(session, {"name": object_name})
        
        # Получаем клиента по ID
        client = await get_client_by_id(session, client_id)
        
        if client:
            # Используем SQL-запрос для добавления связи в таблицу client_objects
            from sqlalchemy import text
            await session.execute(
                text("INSERT INTO client_objects (client_id, object_id) VALUES (:client_id, :object_id)"),
                {"client_id": client_id, "object_id": new_object.id}
            )
            await session.commit()
            
            await callback.message.edit_text(
                f"✅ Объект \"{object_name}\" успешно добавлен и привязан к заказчику {client.full_name}!",
                reply_markup=get_object_back_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"✅ Объект \"{object_name}\" добавлен, но заказчик не найден.",
                reply_markup=get_object_back_keyboard()
            )
    except Exception as e:
        logging.error(f"Ошибка при создании объекта: {e}")
        await callback.message.edit_text(
            f"Произошла ошибка при создании объекта: {e}",
            reply_markup=get_object_back_keyboard()
        )
        # При ошибке откатываем транзакцию
        await session.rollback()
    
    # Сбрасываем состояние
    await state.clear()

# Обработчики редактирования объекта
@object_router.callback_query(lambda c: c.data.startswith("edit_object_") and not c.data.startswith("edit_object_name_") and not c.data.startswith("edit_object_client_"))
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
    
    # Получаем заказчиков объекта
    from sqlalchemy import select, text
    from sqlalchemy.orm import selectinload
    
    # Запрос для получения заказчиков объекта
    query = text("""
        SELECT c.id, c.full_name, c.organization
        FROM clients c
        JOIN client_objects co ON c.id = co.client_id
        WHERE co.object_id = :object_id
    """)
    result = await session.execute(query, {"object_id": object_id})
    object_clients = result.fetchall()
    
    # Создаем клавиатуру для редактирования
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_object_name_{object_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 Изменить заказчика", callback_data=f"edit_object_client_{object_id}"),
        InlineKeyboardButton(text="🗑️ Удалить объект", callback_data=f"delete_object_{object_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="object_back"))
    
    # Формируем текст с информацией о заказчиках
    clients_text = "Нет привязанных заказчиков"
    if object_clients:
        clients_text = "Привязанные заказчики:\n"
        for i, client in enumerate(object_clients, start=1):
            clients_text += f"{i}. {client.full_name} ({client.organization})\n"
    
    # Формируем новый текст сообщения
    new_text = (
        f"Редактирование объекта:\n\n"
        f"Название: {obj.name}\n\n"
        f"{clients_text}\n\n"
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
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"object_delete_confirm_{object_id}"),
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

@object_router.callback_query(F.data.startswith("object_delete_confirm_"))
@error_handler
@with_session
async def confirm_object_delete(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение удаления объекта"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта из формата "object_delete_confirm_ID"
        object_id_str = callback.data.replace("object_delete_confirm_", "")
        object_id = int(object_id_str)
        
        # Перед удалением объекта, удаляем все связи с заказчиками
        from sqlalchemy import text
        await session.execute(
            text("DELETE FROM client_objects WHERE object_id = :object_id"),
            {"object_id": object_id}
        )
        
        # Удаляем объект
        result = await delete_object(session, object_id)
        
        if result:
            await callback.message.edit_text(
                "✅ Объект успешно удален.",
                reply_markup=get_object_back_keyboard()
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось удалить объект. Возможно, он уже был удален.",
                reply_markup=get_object_back_keyboard()
            )
    except Exception as e:
        logging.error(f"Ошибка при удалении объекта: {e}")
        await callback.message.edit_text(
            f"❌ Произошла ошибка при удалении объекта: {e}",
            reply_markup=get_object_back_keyboard()
        )
        await session.rollback()

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

@object_router.callback_query(F.data.startswith("edit_object_client_"))
@error_handler
@with_session
async def process_edit_object_client(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на изменение заказчика объекта"""
    await callback.answer()
    
    try:
        # Выделяем ID объекта из формата "edit_object_client_ID"
        # Исправляем извлечение ID, так как формат "edit_object_client_ID"
        object_id_str = callback.data.replace("edit_object_client_", "")
        object_id = int(object_id_str)
        
        # Проверяем существование объекта
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
        
        # Получаем список всех заказчиков
        clients = await get_all_clients(session)
        
        if not clients:
            await callback.message.edit_text(
                "Список заказчиков пуст. Сначала добавьте заказчиков.",
                reply_markup=get_object_back_keyboard()
            )
            return
        
        # Получаем текущих заказчиков объекта
        from sqlalchemy import text
        query = text("""
            SELECT client_id FROM client_objects 
            WHERE object_id = :object_id
        """)
        result = await session.execute(query, {"object_id": object_id})
        current_client_ids = [row[0] for row in result.fetchall()]
        
        # Формируем текст и клавиатуру для выбора заказчика
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        
        clients_text = f"Выберите нового заказчика для объекта \"{obj.name}\":\n\n"
        for client in clients:
            is_selected = client.id in current_client_ids
            prefix = "✅ " if is_selected else ""
            builder.row(
                InlineKeyboardButton(
                    text=f"{prefix}{client.full_name} ({client.organization})",
                    callback_data=f"select_object_client_{object_id}_{client.id}"
                )
            )
        
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_object_{object_id}"))
        
        await callback.message.edit_text(
            clients_text,
            reply_markup=builder.as_markup()
        )
        
        # Устанавливаем состояние ожидания выбора клиента
        await state.set_state(ObjectEditStates.waiting_for_client_selection)
    except Exception as e:
        logging.error(f"Ошибка в process_edit_object_client: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при обработке запроса.",
            reply_markup=get_object_back_keyboard()
        )

@object_router.callback_query(lambda c: c.data.startswith("select_object_client_"))
@error_handler
@with_session
async def process_select_object_client(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора заказчика для объекта"""
    await callback.answer()
    
    # Извлекаем ID объекта и заказчика из формата "select_object_client_OBJECT_ID_CLIENT_ID"
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.message.edit_text(
            "Некорректный формат данных.",
            reply_markup=get_object_back_keyboard()
        )
        return
    
    object_id = int(parts[3])
    client_id = int(parts[4])
    
    try:
        # Проверяем существование объекта и клиента
        obj = await get_object_by_id(session, object_id)
        client = await get_client_by_id(session, client_id)
        
        if not obj or not client:
            await callback.message.edit_text(
                "Объект или заказчик не найден.",
                reply_markup=get_object_back_keyboard()
            )
            return
        
        # Удаляем все текущие связи объекта с заказчиками
        from sqlalchemy import text
        await session.execute(
            text("DELETE FROM client_objects WHERE object_id = :object_id"),
            {"object_id": object_id}
        )
        
        # Добавляем новую связь
        await session.execute(
            text("INSERT INTO client_objects (client_id, object_id) VALUES (:client_id, :object_id)"),
            {"client_id": client_id, "object_id": object_id}
        )
        
        await session.commit()
        
        await callback.message.edit_text(
            f"✅ Заказчик объекта \"{obj.name}\" успешно изменен на {client.full_name}.",
            reply_markup=get_object_back_keyboard()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при изменении заказчика объекта: {e}")
        await callback.message.edit_text(
            f"Произошла ошибка при изменении заказчика объекта: {e}",
            reply_markup=get_object_back_keyboard()
        )
        await session.rollback()
    
    # Сбрасываем состояние
    await state.clear() 