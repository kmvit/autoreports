import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from construction_report_bot.database.crud import (
    get_report_by_id,
    get_object_by_id,
    delete_report
)
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.utils.logging.logger import log_admin_action

logger = logging.getLogger(__name__)

# Создаем роутер для удаления отчетов
report_delete_router = Router()
# Добавляем middleware для проверки роли
report_delete_router.callback_query.middleware(admin_required())

@report_delete_router.callback_query(F.data.startswith("delete_report_"))
@error_handler
@with_session
async def delete_report_handler(callback: CallbackQuery, session: AsyncSession):
    """Обработчик удаления отчета"""
    report_id = int(callback.data.split("_")[-1])
    
    # Получаем информацию об отчете перед удалением
    report = await get_report_by_id(session, report_id)
    if report:
        object_info = await get_object_by_id(session, report.object_id)
        object_name = object_info.name if object_info else "Неизвестный объект"
        
        # Создаем клавиатуру для подтверждения удаления
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{report_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="show_all_reports")
            ]
        ]
        
        await callback.message.edit_text(
            f"Вы уверены, что хотите удалить отчет '{object_name} {report.type} от {report.date.strftime('%d.%m.%Y %H:%M')}'?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            "Отчет не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        )

@report_delete_router.callback_query(F.data.startswith("confirm_delete_"))
@error_handler
@with_session
async def confirm_delete_report(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение удаления отчета"""
    report_id = int(callback.data.split("_")[-1])
    
    # Удаляем отчет
    success = await delete_report(session, report_id)
    
    if success:
        # Регистрируем действие в логах
        log_admin_action(callback.from_user.id, f"Удален отчет #{report_id}")
        
        await callback.message.edit_text(
            "Отчет успешно удален.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к отчетам", callback_data="show_all_reports")]
            ])
        )
    else:
        await callback.message.edit_text(
            "Ошибка при удалении отчета.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        ) 