from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Dict, Any, Callable, Awaitable, AsyncGenerator
from construction_report_bot.database.session import get_session
from construction_report_bot.database.crud import get_user_by_telegram_id, create_user
from construction_report_bot.config.settings import settings
import logging

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
        # Проверяем, является ли пользователь администратором
        admin_ids = [int(id.strip()) for id in settings.ADMIN_USER_IDS.split(',') if id.strip()]
        if telegram_id in admin_ids:
            logging.info("[AuthMiddleware] User is ADMIN")
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
        
        logging.info("[AuthMiddleware] User is NOT ADMIN or check passed. Proceeding...")
        # Для команды /start пропускаем проверку авторизации
        if isinstance(event, Message) and event.text and event.text.startswith('/start'):
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