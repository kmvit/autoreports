from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from construction_report_bot.database.crud import get_user_by_telegram_id, get_user_by_access_code, update_user, create_user
from construction_report_bot.database.session import get_session
from construction_report_bot.config.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from construction_report_bot.config.settings import settings

# Создаем роутер для общих команд
common_router = Router()

# Состояния FSM для авторизации
class AuthStates(StatesGroup):
    waiting_for_access_code = State()

# Обработчик команды /start
@common_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, user=None):
    """Обработчик команды /start"""
    # Если пользователь уже авторизован (включая админов)
    if user:
        # Отправляем приветствие в зависимости от роли
        if user.role == settings.ADMIN_ROLE:
            await message.answer(
                f"Добро пожаловать, администратор {user.username}!",
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            await message.answer(
                f"Добро пожаловать, {user.username}!",
                reply_markup=get_main_menu_keyboard()
            )
    else:
        # Если пользователь не авторизован, запрашиваем код доступа
        await message.answer(
            "Добро пожаловать в систему отчетов о строительстве!\n"
            "Пожалуйста, введите код доступа, полученный от администратора."
        )
        await state.set_state(AuthStates.waiting_for_access_code)

# Обработчик ввода кода доступа
@common_router.message(AuthStates.waiting_for_access_code)
async def process_access_code(message: Message, state: FSMContext):
    """Обработчик ввода кода доступа"""
    access_code = message.text.strip()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await anext(session_gen)
    
    try:
        # Проверяем код доступа
        user = await get_user_by_access_code(session, access_code)
        
        if user:
            # Если код верный, связываем Telegram ID с пользователем
            await update_user(
                session, 
                user.id, 
                {
                    "telegram_id": message.from_user.id,
                    "username": message.from_user.username or message.from_user.full_name or "Пользователь",
                    "access_code": None  # Удаляем код доступа после использования
                }
            )
            
            # Сбрасываем состояние
            await state.clear()
            
            # Отправляем приветствие в зависимости от роли
            if user.role == settings.ADMIN_ROLE:
                await message.answer(
                    "Вы успешно авторизованы как администратор!",
                    reply_markup=get_admin_menu_keyboard()
                )
            else:
                await message.answer(
                    "Вы успешно авторизованы как заказчик!",
                    reply_markup=get_main_menu_keyboard()
                )
        else:
            # Если код неверный, сообщаем об ошибке
            await message.answer(
                "Неверный код доступа. Пожалуйста, проверьте код и попробуйте снова."
            )
    finally:
        await session.close()

# Обработчик команды /help
@common_router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "Бот для отчетов о строительстве\n\n"
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
    )
    await message.answer(help_text)

# Обработчик кнопки "Назад"
@common_router.callback_query(F.data == "back")
async def process_back_button(callback: CallbackQuery):
    """Обработка нажатия кнопки Назад"""
    await callback.answer()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await anext(session_gen)
    
    try:
        # Проверяем, авторизован ли пользователь
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        
        if user:
            if user.role == settings.ADMIN_ROLE:
                await callback.message.edit_text(
                    "Главное меню администратора", 
                    reply_markup=get_admin_menu_keyboard()
                )
            else:
                await callback.message.edit_text(
                    "Главное меню", 
                    reply_markup=get_main_menu_keyboard()
                )
    finally:
        await session.close() 