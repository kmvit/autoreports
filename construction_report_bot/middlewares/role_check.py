from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Dict, Any, Callable, Awaitable, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from construction_report_bot.config.settings import settings
from construction_report_bot.database.crud import get_user_by_telegram_id
from construction_report_bot.utils.logging.logger import log_admin_action, log_error

class RoleMiddleware(BaseMiddleware):
    """Middleware для проверки роли пользователя"""
    
    def __init__(self, allowed_roles: Optional[List[str]] = None):
        self.allowed_roles = allowed_roles or []
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Если нет списка разрешенных ролей, пропускаем всех
        if not self.allowed_roles:
            return await handler(event, data)
        
        # Проверяем, что у нас есть пользователь в данных
        if "user" not in data:
            if isinstance(event, Message):
                await event.answer("Вы должны быть авторизованы для выполнения этого действия.")
            return None
        
        user = data["user"]
        
        # Проверяем, имеет ли пользователь необходимую роль
        if user.role not in self.allowed_roles:
            if isinstance(event, Message):
                await event.answer("У вас нет прав для выполнения этого действия.")
            return None
        
        return await handler(event, data)

class AdminMiddleware(BaseMiddleware):
    """Middleware для проверки прав администратора"""
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Проверка прав администратора"""
        try:
            print(f"[AdminMiddleware] Processing event: {event}")
            print(f"[AdminMiddleware] Event type: {type(event)}")
            if isinstance(event, CallbackQuery):
                print(f"[AdminMiddleware] Callback data: {event.data}")
            
            # Получаем сессию из данных
            session: AsyncSession = data.get('session')
            if not session:
                print("[AdminMiddleware] No session found")
                log_error(None, event.from_user.id, "Отсутствует сессия БД")
                if isinstance(event, Message):
                    await event.answer("Ошибка доступа к базе данных")
                else:
                    await event.message.edit_text("Ошибка доступа к базе данных")
                return
            
            # Проверяем права администратора
            user = await get_user_by_telegram_id(session, event.from_user.id)
            print(f"[AdminMiddleware] User found: {user}")
            if not user or user.role != "admin":
                print(f"[AdminMiddleware] Access denied for user {event.from_user.id}")
                log_admin_action("access_denied", event.from_user.id, "Попытка доступа к админ-панели")
                if isinstance(event, Message):
                    await event.answer("У вас нет прав для выполнения этой операции")
                else:
                    await event.message.edit_text("У вас нет прав для выполнения этой операции")
                return
            
            print("[AdminMiddleware] Access granted, calling handler")
            # Если все проверки пройдены, вызываем обработчик
            return await handler(event, data)
        except Exception as e:
            print(f"[AdminMiddleware] Error: {e}")
            log_error(e, event.from_user.id, "Ошибка в AdminMiddleware")
            if isinstance(event, Message):
                await event.answer("Произошла ошибка при проверке прав доступа")
            else:
                await event.message.edit_text("Произошла ошибка при проверке прав доступа")
            return

# Функции для создания middleware для конкретных ролей
def admin_required():
    """Создает middleware, требующий роль администратора"""
    return RoleMiddleware([settings.ADMIN_ROLE])

def client_required():
    """Создает middleware, требующий роль клиента"""
    return RoleMiddleware([settings.CLIENT_ROLE])

def any_role_required():
    """Создает middleware, требующий любую авторизованную роль"""
    return RoleMiddleware([settings.ADMIN_ROLE, settings.CLIENT_ROLE]) 