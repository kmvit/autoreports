from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.database.crud import (
    get_all_clients, create_client, update_client, delete_client,
    create_user, get_client_by_id
)
from construction_report_bot.config.keyboards import (
    get_client_management_keyboard, get_back_keyboard, get_admin_keyboard
)
from construction_report_bot.config.settings import settings
from construction_report_bot.utils.decorators import error_handler, extract_id_from_callback, with_session
from construction_report_bot.utils.validators import (
    validate_full_name, validate_organization, validate_contact_info, generate_access_code
)

# Создаем роутер для управления заказчиками
admin_client_router = Router()

# Добавляем middleware для проверки роли
admin_client_router.message.middleware(admin_required())
admin_client_router.callback_query.middleware(admin_required())

# Состояния FSM для управления заказчиками
class ClientManagementStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_organization = State()
    waiting_for_contact_info = State()

# Состояния FSM для редактирования заказчика
class ClientEditStates(StatesGroup):
    waiting_for_new_full_name = State()
    waiting_for_new_organization = State()
    waiting_for_new_contact_info = State()

# Обработчики управления заказчиками
@admin_client_router.message(F.text == "👥 Управление заказчиками")
@error_handler
async def cmd_client_management(message: Message):
    """Обработчик команды управления заказчиками"""
    await message.answer(
        "Управление заказчиками. Выберите действие:",
        reply_markup=get_client_management_keyboard()
    )

@admin_client_router.callback_query(F.data == "client_list")
@error_handler
@with_session
async def process_client_list(callback: CallbackQuery, session: AsyncSession):
    """Обработка запроса списка заказчиков"""
    await callback.answer()
    
    # Получаем список заказчиков
    clients = await get_all_clients(session)
    
    if clients:
        # Формируем текст со списком заказчиков
        clients_text = "📋 Список заказчиков:\n\n"
        for i, client in enumerate(clients, start=1):
            try:
                access_code = "Не установлен"
                if client.user and client.user.access_code:
                    access_code = client.user.access_code
                
                clients_text += (
                    f"{i}. {client.full_name}\n"
                    f"   Организация: {client.organization}\n"
                    f"   Контакты: {client.contact_info}\n"
                    f"   Код доступа: {access_code}\n\n"
                )
            except Exception as e:
                logging.error(f"Ошибка при формировании данных клиента {client.id}: {e}")
                clients_text += (
                    f"{i}. {client.full_name}\n"
                    f"   Организация: {client.organization}\n"
                    f"   Контакты: {client.contact_info}\n"
                    f"   Код доступа: Ошибка получения\n\n"
                )
        
        # Добавляем кнопки управления для каждого заказчика
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        
        # Логируем информацию о клиентах и их ID
        for client in clients:
            logging.info(f"Клиент: {client.full_name}, ID: {client.id}")
            callback_data = f"edit_client_{client.id}"
            logging.info(f"Callback data для кнопки: {callback_data}")
            
            builder.row(
                InlineKeyboardButton(
                    text=f"✏️ {client.full_name}",
                    callback_data=callback_data
                )
            )
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="client_back"))
        
        # Проверяем, изменилось ли содержимое сообщения
        if (callback.message.text != clients_text or 
            callback.message.reply_markup != builder.as_markup()):
            await callback.message.edit_text(
                clients_text,
                reply_markup=builder.as_markup()
            )
        else:
            # Если содержимое не изменилось, просто отвечаем пользователю
            await callback.answer("Список заказчиков актуален")
    else:
        await callback.message.edit_text(
            "Список заказчиков пуст.",
            reply_markup=get_back_keyboard()
        )

@admin_client_router.callback_query(F.data == "client_add")
@error_handler
async def process_client_add(callback: CallbackQuery, state: FSMContext):
    """Обработка запроса на добавление заказчика"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Добавление нового заказчика.\n"
        "Введите ФИО заказчика (например: Иванов Иван Иванович):"
    )
    
    await state.set_state(ClientManagementStates.waiting_for_full_name)

@admin_client_router.message(ClientManagementStates.waiting_for_full_name)
@error_handler
async def process_client_name(message: Message, state: FSMContext):
    """Обработка ввода имени заказчика"""
    full_name = message.text.strip()
    
    if not validate_full_name(full_name):
        await message.answer(
            "Неверный формат ФИО. Пожалуйста, введите корректное ФИО "
            "(например: Иванов Иван Иванович):"
        )
        return
    
    await state.update_data(full_name=full_name)
    await message.answer("Введите название организации заказчика:")
    await state.set_state(ClientManagementStates.waiting_for_organization)

@admin_client_router.message(ClientManagementStates.waiting_for_organization)
@error_handler
async def process_client_organization(message: Message, state: FSMContext):
    """Обработка ввода организации заказчика"""
    organization = message.text.strip()
    
    if not validate_organization(organization):
        await message.answer(
            "Неверный формат названия организации. Пожалуйста, введите корректное название:"
        )
        return
    
    await state.update_data(organization=organization)
    await message.answer(
        "Введите контактную информацию заказчика\n"
        "(телефон в формате +7XXXXXXXXXX или email):"
    )
    await state.set_state(ClientManagementStates.waiting_for_contact_info)

@admin_client_router.message(ClientManagementStates.waiting_for_contact_info)
@error_handler
@with_session
async def process_client_contact_info(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода контактной информации заказчика"""
    contact_info = message.text.strip()
    
    if not validate_contact_info(contact_info):
        await message.answer(
            "Неверный формат контактной информации. Пожалуйста, введите "
            "корректный телефон (+7XXXXXXXXXX) или email:"
        )
        return
    
    user_data = await state.get_data()
    
    # Генерируем код доступа
    access_code = generate_access_code()
    
    # Создаем пользователя
    user = await create_user(session, {
        "role": settings.CLIENT_ROLE,
        "access_code": access_code,
        "username": user_data["full_name"]
    })
    
    # Создаем клиента
    await create_client(session, {
        "user_id": user.id,
        "full_name": user_data["full_name"],
        "organization": user_data["organization"],
        "contact_info": contact_info
    })
    
    # Отправляем код доступа
    await message.answer(
        f"✅ Заказчик успешно добавлен!\n\n"
        f"📝 Информация о заказчике:\n"
        f"ФИО: {user_data['full_name']}\n"
        f"Организация: {user_data['organization']}\n"
        f"Контакты: {contact_info}\n\n"
        f"🔑 Код доступа для заказчика: `{access_code}`\n\n"
        f"Передайте этот код заказчику для авторизации в боте.",
        parse_mode="Markdown"
    )
    
    # Сбрасываем состояние
    await state.clear()

# Обработчики редактирования заказчика
@admin_client_router.callback_query(lambda c: c.data.startswith("edit_client_") and not any(x in c.data for x in ["name", "org", "contact"]))
@error_handler
@with_session
async def process_client_edit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на редактирование заказчика"""
    await callback.answer()
    
    # Извлекаем ID клиента из формата "edit_client_ID"
    client_id = extract_id_from_callback(callback.data, "edit_client_")
    
    # Получаем данные заказчика
    client = await get_client_by_id(session, client_id)
    
    if not client:
        logging.error(f"Заказчик с ID {client_id} не найден")
        await callback.message.edit_text(
            "Заказчик не найден.",
            reply_markup=get_back_keyboard()
        )
        return
    
    # Сохраняем ID заказчика в состоянии
    await state.update_data(client_id=client_id)
    
    # Создаем клавиатуру для редактирования
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить ФИО", callback_data=f"edit_client_name_{client_id}"),
        InlineKeyboardButton(text="🏢 Изменить организацию", callback_data=f"edit_client_org_{client_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📞 Изменить контакты", callback_data=f"edit_client_contact_{client_id}"),
        InlineKeyboardButton(text="🗑️ Удалить заказчика", callback_data=f"delete_client_{client_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="client_list"))
    
    # Формируем новый текст сообщения
    new_text = (
        f"Редактирование заказчика:\n\n"
        f"ФИО: {client.full_name}\n"
        f"Организация: {client.organization}\n"
        f"Контакты: {client.contact_info}\n\n"
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
        await callback.answer("Данные заказчика актуальны")

@admin_client_router.callback_query(F.data.startswith("delete_client_"))
@error_handler
async def process_client_delete(callback: CallbackQuery):
    """Обработка запроса на удаление заказчика"""
    await callback.answer()
    
    # Извлекаем ID клиента из формата "delete_client_ID"
    client_id = extract_id_from_callback(callback.data, "delete_client_")
    
    # Создаем клавиатуру подтверждения
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"client_delete_confirm_{client_id}"),
        InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"edit_client_{client_id}")
    )
    
    try:
        await callback.message.edit_text(
            "⚠️ Вы уверены, что хотите удалить этого заказчика?\n"
            "Это действие нельзя отменить.",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.")

@admin_client_router.callback_query(F.data.startswith("client_delete_confirm_"))
@error_handler
@with_session
async def process_confirm_delete_client(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка подтверждения удаления клиента"""
    client_id = int(callback.data.split("_")[-1])
    
    client = await get_client_by_id(session, client_id)
    if not client:
        await callback.message.edit_text(
            "❌ Клиент не найден",
            reply_markup=await get_admin_keyboard()
        )
        return
    
    full_name = client.full_name  # Сохраняем имя заранее для использования после удаления
    
    try:
        await delete_client(session, client_id)
        
        logging.info(f"Клиент {full_name} (ID: {client_id}) успешно удален")
        
        await callback.message.edit_text(
            f"✅ Клиент {full_name} успешно удален",
            reply_markup=await get_admin_keyboard()
        )
    except Exception as e:
        # Развернутое логирование ошибки для диагностики
        logging.error(f"Ошибка при удалении клиента {full_name} (ID: {client_id}): {str(e)}")
        
        # Упрощенное сообщение для пользователя
        error_message = "Произошла ошибка при удалении клиента."
        if "ForeignKeyViolationError" in str(e):
            error_message = "Не удалось удалить клиента из-за связанных данных. Свяжитесь с администратором."
        
        await callback.message.edit_text(
            f"❌ {error_message}",
            reply_markup=await get_admin_keyboard()
        )

# Обработчики редактирования полей заказчика
@admin_client_router.callback_query(F.data.startswith("edit_client_name_"))
@error_handler
@with_session
async def process_edit_client_name(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на изменение ФИО заказчика"""
    await callback.answer()
    
    # Выделяем ID из формата "edit_client_name_ID"
    client_id = extract_id_from_callback(callback.data, "edit_client_name_")
    
    # Проверяем существование клиента
    client = await get_client_by_id(session, client_id)
    if not client:
        logging.error(f"Заказчик с ID {client_id} не найден")
        await callback.message.edit_text(
            "Заказчик не найден.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.update_data(client_id=client_id)
    
    try:
        await callback.message.edit_text(
            "Введите новое ФИО заказчика (например: Иванов Иван Иванович):"
        )
        await state.set_state(ClientEditStates.waiting_for_new_full_name)
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, пробуем отправить новое
        await callback.message.answer(
            "Введите новое ФИО заказчика (например: Иванов Иван Иванович):"
        )
        await state.set_state(ClientEditStates.waiting_for_new_full_name)

@admin_client_router.message(ClientEditStates.waiting_for_new_full_name)
@error_handler
@with_session
async def process_new_client_name(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода нового ФИО заказчика"""
    full_name = message.text.strip()
    
    if not validate_full_name(full_name):
        await message.answer(
            "Неверный формат ФИО. Пожалуйста, введите корректное ФИО "
            "(например: Иванов Иван Иванович):"
        )
        return
    
    user_data = await state.get_data()
    client_id = user_data["client_id"]
    
    # Обновляем ФИО заказчика
    await update_client(session, client_id, {"full_name": full_name})
    
    await message.answer(
        f"✅ ФИО заказчика успешно обновлено на: {full_name}",
        reply_markup=get_back_keyboard()
    )
    
    await state.clear()

@admin_client_router.callback_query(F.data.startswith("edit_client_org_"))
@error_handler
@with_session
async def process_edit_client_org(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на изменение организации заказчика"""
    await callback.answer()
    
    # Выделяем ID из формата "edit_client_org_ID"
    client_id = extract_id_from_callback(callback.data, "edit_client_org_")
    
    # Проверяем существование клиента
    client = await get_client_by_id(session, client_id)
    if not client:
        logging.error(f"Заказчик с ID {client_id} не найден")
        await callback.message.edit_text(
            "Заказчик не найден.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.update_data(client_id=client_id)
    
    try:
        await callback.message.edit_text(
            "Введите новое название организации заказчика:"
        )
        await state.set_state(ClientEditStates.waiting_for_new_organization)
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, пробуем отправить новое
        await callback.message.answer(
            "Введите новое название организации заказчика:"
        )
        await state.set_state(ClientEditStates.waiting_for_new_organization)

@admin_client_router.message(ClientEditStates.waiting_for_new_organization)
@error_handler
@with_session
async def process_new_client_org(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода нового названия организации заказчика"""
    organization = message.text.strip()
    
    if not validate_organization(organization):
        await message.answer(
            "Неверный формат названия организации. Пожалуйста, введите корректное название:"
        )
        return
    
    user_data = await state.get_data()
    client_id = user_data["client_id"]
    
    # Обновляем организацию заказчика
    await update_client(session, client_id, {"organization": organization})
    
    await message.answer(
        f"✅ Название организации заказчика успешно обновлено на: {organization}",
        reply_markup=get_back_keyboard()
    )
    
    await state.clear()

@admin_client_router.callback_query(F.data.startswith("edit_client_contact_"))
@error_handler
@with_session
async def process_edit_client_contact(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка запроса на изменение контактной информации заказчика"""
    await callback.answer()
    
    # Выделяем ID из формата "edit_client_contact_ID"
    client_id = extract_id_from_callback(callback.data, "edit_client_contact_")
    
    # Проверяем существование клиента
    client = await get_client_by_id(session, client_id)
    if not client:
        logging.error(f"Заказчик с ID {client_id} не найден")
        await callback.message.edit_text(
            "Заказчик не найден.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.update_data(client_id=client_id)
    
    try:
        await callback.message.edit_text(
            "Введите новую контактную информацию заказчика\n"
            "(телефон в формате +7XXXXXXXXXX или email):"
        )
        await state.set_state(ClientEditStates.waiting_for_new_contact_info)
    except Exception as edit_error:
        logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        # Если сообщение не изменилось, пробуем отправить новое
        await callback.message.answer(
            "Введите новую контактную информацию заказчика\n"
            "(телефон в формате +7XXXXXXXXXX или email):"
        )
        await state.set_state(ClientEditStates.waiting_for_new_contact_info)

@admin_client_router.message(ClientEditStates.waiting_for_new_contact_info)
@error_handler
@with_session
async def process_new_client_contact(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка ввода новой контактной информации заказчика"""
    contact_info = message.text.strip()
    
    if not validate_contact_info(contact_info):
        await message.answer(
            "Неверный формат контактной информации. Пожалуйста, введите "
            "корректный телефон (+7XXXXXXXXXX) или email:"
        )
        return
    
    user_data = await state.get_data()
    client_id = user_data["client_id"]
    
    # Обновляем контактную информацию заказчика
    await update_client(session, client_id, {"contact_info": contact_info})
    
    await message.answer(
        f"✅ Контактная информация заказчика успешно обновлена на: {contact_info}",
        reply_markup=get_back_keyboard()
    )
    
    await state.clear()

# Настроим обработчик кнопки "Назад" в контексте списка клиентов
@admin_client_router.callback_query(F.data == "client_back")
@error_handler
async def process_client_back(callback: CallbackQuery):
    """Обработка нажатия кнопки Назад в контексте управления заказчиками"""
    await callback.answer()
    await callback.message.edit_text(
        "Управление заказчиками. Выберите действие:",
        reply_markup=get_client_management_keyboard()
    )

@admin_client_router.callback_query(F.data == "client_edit")
@error_handler
@with_session
async def process_client_edit_menu(callback: CallbackQuery, session: AsyncSession):
    """Обработка запроса на редактирование/удаление заказчика"""
    await callback.answer()
    
    # Получаем список заказчиков
    clients = await get_all_clients(session)
    
    if not clients:
        await callback.message.edit_text(
            "Список заказчиков пуст.",
            reply_markup=get_back_keyboard()
        )
        return
    
    # Формируем текст со списком заказчиков
    clients_text = "📋 Выберите заказчика для редактирования/удаления:\n\n"
    for i, client in enumerate(clients, start=1):
        clients_text += (
            f"{i}. {client.full_name}\n"
            f"   Организация: {client.organization}\n"
            f"   Контакты: {client.contact_info}\n\n"
        )
    
    # Создаем клавиатуру с кнопками для каждого заказчика
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {client.full_name}",
                callback_data=f"edit_client_{client.id}"
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="client_back"))
    
    await callback.message.edit_text(
        clients_text,
        reply_markup=builder.as_markup()
    )

@admin_client_router.callback_query(F.data == "client_delete")
@error_handler
@with_session
async def process_client_delete_menu(callback: CallbackQuery, session: AsyncSession):
    """Обработка запроса на удаление заказчика"""
    await callback.answer()
    
    # Получаем список заказчиков
    clients = await get_all_clients(session)
    
    if not clients:
        await callback.message.edit_text(
            "Список заказчиков пуст.",
            reply_markup=get_back_keyboard()
        )
        return
    
    # Формируем текст со списком заказчиков
    clients_text = "🗑️ Выберите заказчика для удаления:\n\n"
    for i, client in enumerate(clients, start=1):
        clients_text += (
            f"{i}. {client.full_name}\n"
            f"   Организация: {client.organization}\n"
            f"   Контакты: {client.contact_info}\n\n"
        )
    
    # Создаем клавиатуру с кнопками для каждого заказчика
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.row(
            InlineKeyboardButton(
                text=f"🗑️ {client.full_name}",
                callback_data=f"client_delete_confirm_{client.id}"
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="client_back"))
    
    await callback.message.edit_text(
        clients_text,
        reply_markup=builder.as_markup()
    )

@admin_client_router.callback_query(F.data == "admin_back")
@error_handler
@with_session
async def process_admin_back(callback: CallbackQuery, session: AsyncSession):
    """Обработка нажатия кнопки Назад в контексте управления заказчиками"""
    await callback.answer()
    await callback.message.edit_text(
        "Главное меню администратора:",
        reply_markup=get_admin_keyboard()
    ) 