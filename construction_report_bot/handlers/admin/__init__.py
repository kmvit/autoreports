from aiogram import Dispatcher
from .client import admin_client_router
from .report_menu import admin_report_menu_router
from .report_create import admin_report_create_router
from .report_edit import admin_report_edit_router
from .report_export import admin_report_export_router
from .object import object_router
from .personnel import personnel_router
from .equipment import equipment_router

def register_admin_handlers(dp: Dispatcher) -> None:
    """
    Регистрация всех обработчиков для админ-панели
    """
    dp.include_router(admin_report_menu_router)
    dp.include_router(admin_report_create_router)
    dp.include_router(admin_report_edit_router)
    dp.include_router(admin_report_export_router)
    dp.include_router(object_router)
    dp.include_router(admin_client_router)
    dp.include_router(equipment_router)
    dp.include_router(personnel_router)
    