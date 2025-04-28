from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
import logging

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
    logging.info(f"[cmd_start] Получена команда /start от пользователя {message.from_user.id}")
    
    # Если пользователь уже авторизован (включая админов)
    if user:
        logging.info(f"[cmd_start] Пользователь {message.from_user.id} уже авторизован как {user.role}")
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
        logging.info(f"[cmd_start] Пользователь {message.from_user.id} не авторизован, запрашиваем код доступа")
        # Если пользователь не авторизован, запрашиваем код доступа
        await message.answer(
            "Добро пожаловать в систему отчетов о строительстве!\n"
            "Пожалуйста, введите код доступа, полученный от администратора."
        )
        await state.set_state(AuthStates.waiting_for_access_code)
        logging.info(f"[cmd_start] Установлено состояние {AuthStates.waiting_for_access_code} для пользователя {message.from_user.id}")

# Обработчик ввода кода доступа
@common_router.message(AuthStates.waiting_for_access_code)
async def process_access_code(message: Message, state: FSMContext):
    """Обработчик ввода кода доступа"""
    access_code = message.text.strip()
    
    # Добавляем логирование
    logging.info(f"[process_access_code] Получен код доступа от пользователя {message.from_user.id}: {access_code}")
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await anext(session_gen)
    
    try:
        # Проверяем код доступа
        logging.info(f"[process_access_code] Проверяем код доступа: {access_code}")
        user = await get_user_by_access_code(session, access_code)
        logging.info(f"[process_access_code] Результат проверки: {user}")
        
        if user:
            # Если код верный, связываем Telegram ID с пользователем
            logging.info(f"[process_access_code] Код верный, обновляем пользователя {user.id}")
            await update_user(
                session, 
                user.id, 
                {
                    "telegram_id": message.from_user.id,
                    "username": message.from_user.username or message.from_user.full_name or "Пользователь"
                }
            )
            
            # Сбрасываем состояние
            await state.clear()
            logging.info(f"[process_access_code] Состояние сброшено, пользователь авторизован")
            
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
            logging.info(f"[process_access_code] Код неверный, сообщаем пользователю")
            await message.answer(
                "Неверный код доступа. Пожалуйста, проверьте код и попробуйте снова."
            )
    except Exception as e:
        logging.error(f"[process_access_code] Ошибка при проверке кода доступа: {e}", exc_info=True)
        await message.answer("Произошла ошибка при проверке кода доступа. Попробуйте позже.")
    finally:
        await session.close()
        logging.info(f"[process_access_code] Сессия закрыта")

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