from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Dict, Any, Callable, Awaitable, AsyncGenerator
from construction_report_bot.database.session import get_session
from construction_report_bot.database.crud import get_user_by_telegram_id, create_user
from construction_report_bot.config.settings import settings
from construction_report_bot.handlers.common import AuthStates  # Добавляем импорт состояний
from aiogram.fsm.context import FSMContext  # Добавляем импорт контекста FSM
import logging

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации пользователя"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id в зависимости от типа события
        if isinstance(event, Message):
            telegram_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id
            logging.info(f"[AuthMiddleware] Callback Data: {event.data}")
        else:
            return await handler(event, data)
            
        logging.info(f"[AuthMiddleware] Event: {type(event)}, Telegram ID: {telegram_id}")
        logger.debug(f"Проверка доступа для пользователя {telegram_id}")
        logger.debug(f"Список администраторов: {settings.admin_ids}")
        logger.debug(f"Тип telegram_id: {type(telegram_id)}")
        logger.debug(f"Типы ID в admin_ids: {[type(id) for id in settings.admin_ids]}")
        logger.debug(f"Сравнение: {telegram_id in settings.admin_ids}")
        
        if telegram_id in settings.admin_ids:
            logger.info(f"Пользователь {telegram_id} является администратором")
            session_gen: AsyncGenerator = get_session()
            session = None
            user = None # Initialize user to None
            try:
                session = await session_gen.__anext__()
                logging.info("[AuthMiddleware] Admin Check: Getting user from DB")
                user = await get_user_by_telegram_id(session, telegram_id)
                logging.info(f"[AuthMiddleware] Admin Check: DB result: {user}")
                if not user:
                    logging.info("[AuthMiddleware] Admin Check: User not found, creating...")
                    username = (
                        event.from_user.username or 
                        event.from_user.full_name or 
                        "Администратор"
                    )
                    user = await create_user(session, {
                        "telegram_id": telegram_id,
                        "username": username,
                        "role": settings.ADMIN_ROLE
                    })
                    logging.info(f"[AuthMiddleware] Admin Check: Created user: {user}")
                
                if user: # Check if user is successfully found or created
                    data["user"] = user
                    logging.info(f"[AuthMiddleware] Admin Check: User object added to data. Calling handler...")
                    result = await handler(event, data)
                    logging.info("[AuthMiddleware] Admin Check: Handler finished.")
                    return result
                else:
                    logging.error("[AuthMiddleware] Admin Check: Failed to get or create admin user object!")
                    # Optionally, inform the user or just stop
                    if isinstance(event, CallbackQuery):
                         await event.answer("Ошибка проверки администратора", show_alert=True)
                    return None # Stop processing if user object is None
            except Exception as e:
                logging.error(f"[AuthMiddleware] Admin Check: DB Error: {e}", exc_info=True)
                if isinstance(event, CallbackQuery):
                    await event.answer("Ошибка БД при проверке администратора", show_alert=True)
                return None # Stop processing on DB error
            finally:
                if session:
                    await session.close()
                    logging.info("[AuthMiddleware] Admin Check: Session closed.")
        else:
            logging.warning("[AuthMiddleware] ADMIN_USER_IDS is empty in settings")
        
        # Проверяем, является ли пользователь клиентом
        logging.info("[AuthMiddleware] User is not ADMIN, checking if CLIENT")
        session_gen: AsyncGenerator = get_session()
        session = None
        try:
            session = await session_gen.__anext__()
            user = await get_user_by_telegram_id(session, telegram_id)
            if user and user.role == settings.CLIENT_ROLE:
                logging.info("[AuthMiddleware] User is CLIENT")
                data["user"] = user
                result = await handler(event, data)
                return result
            else:
                logging.info("[AuthMiddleware] User is not CLIENT")
        except Exception as e:
            logging.error(f"[AuthMiddleware] Client Check Error: {e}")
        finally:
            if session:
                await session.close()
        
        logging.info("[AuthMiddleware] User is NOT ADMIN or check passed. Proceeding...")
        
        # Для команды /start пропускаем проверку авторизации
        if isinstance(event, Message) and event.text and event.text.startswith('/start'):
            return await handler(event, data)
        
        # Получаем состояние FSM, если доступно
        state = data.get("state")
        
        # Проверяем, находится ли пользователь в состоянии ожидания ввода кода доступа
        if state:
            current_state = await state.get_state()
            logging.info(f"[AuthMiddleware] Current FSM state: {current_state}")
            
            # Если пользователь в состоянии ожидания кода доступа, пропускаем проверку авторизации
            if current_state == "AuthStates:waiting_for_access_code":
                logging.info("[AuthMiddleware] User is waiting for access code, bypassing auth check")
                return await handler(event, data)
        
        # Получаем сессию БД из зависимостей
        session_gen: AsyncGenerator = get_session()
        session = None
        try:
            session = await session_gen.__anext__()
            logging.info("[AuthMiddleware] Non-Admin Check: Getting user from DB")
            user = await get_user_by_telegram_id(session, telegram_id)
            logging.info(f"[AuthMiddleware] Non-Admin Check: DB result: {user}")
            
            if user:
                data["user"] = user
                logging.info("[AuthMiddleware] Non-Admin Check: User found. Calling handler...")
                result = await handler(event, data)
                logging.info("[AuthMiddleware] Non-Admin Check: Handler finished.")
                return result
            else:
                logging.warning("[AuthMiddleware] Non-Admin Check: User not found. Blocking.")
                # Если пользователь не найден, отправляем сообщение об авторизации
                if isinstance(event, Message):
                    await event.answer(
                        "Вы не авторизованы. Используйте команду /start для авторизации."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "Вы не авторизованы. Используйте команду /start для авторизации.",
                        show_alert=True
                    )
                return None
        except Exception as e:
            logging.error(f"[AuthMiddleware] Non-Admin Check: DB Error: {e}", exc_info=True)
            if isinstance(event, CallbackQuery):
                 await event.answer("Ошибка БД при проверке пользователя", show_alert=True)
            return None # Stop processing on DB error
        finally:
            if session:
                await session.close()
                logging.info("[AuthMiddleware] Non-Admin Check: Session closed.") 