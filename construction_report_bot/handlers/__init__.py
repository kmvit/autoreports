from aiogram import Dispatcher
from .common import common_router
from .admin import register_admin_handlers
from .client import register_client_handlers

def register_all_handlers(dp: Dispatcher):
    """Регистрирует все обработчики"""
    # Регистрация общих обработчиков
    dp.include_router(common_router)
    
    # Регистрация обработчиков администратора
    register_admin_handlers(dp)
    
    # Регистрация обработчиков клиента
    register_client_handlers(dp) 