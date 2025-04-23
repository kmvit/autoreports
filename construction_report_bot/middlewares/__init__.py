from aiogram import Dispatcher
from .auth import AuthMiddleware
from .role_check import RoleMiddleware, admin_required, client_required, any_role_required

def setup_middlewares(dp: Dispatcher):
    """Настройка middleware для диспетчера"""
    # Регистрируем middleware для сообщений
    dp.message.middleware(AuthMiddleware())
    
    # Регистрируем middleware для callback-запросов
    dp.callback_query.middleware(AuthMiddleware())

__all__ = [
    'AuthMiddleware', 'RoleMiddleware', 
    'admin_required', 'client_required', 'any_role_required',
    'setup_middlewares'
] 