"""Общие утилиты для работы с данными и форматированием."""

import logging
from typing import Union, List, Tuple
from datetime import datetime
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from construction_report_bot.database.models import Report, Object
from construction_report_bot.database.crud import get_object_by_id

# Создаем логгер
logger = logging.getLogger(__name__)

async def handle_error(message: Union[Message, CallbackQuery], error: Exception, back_callback: str = "back_to_main"):
    """Обрабатывает ошибку и показывает сообщение с кнопкой 'Назад'"""
    logger.error(f"Ошибка: {str(error)}", exc_info=True)
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(
            f"Произошла ошибка: {str(error)}"
        )
    else:
        await message.answer(
            f"Произошла ошибка: {str(error)}"
        )

async def get_object_info(session: AsyncSession, object_id: int) -> Tuple[Object, str]:
    """Получает информацию об объекте и его отформатированное имя"""
    object_info = await get_object_by_id(session, object_id)
    object_name = object_info.name if object_info else "Неизвестный объект"
    return object_info, object_name

def format_datetime(dt: datetime, date_format: str = "%d.%m.%Y", time_format: str = "%H:%M") -> Tuple[str, str]:
    """Форматирует дату и время"""
    date_str = dt.strftime(date_format)
    time_str = dt.strftime(time_format)
    return date_str, time_str

async def check_reports_exist(message: Union[Message, CallbackQuery], reports: List[Report], 
                            edit: bool = False) -> bool:
    """Проверяет наличие отчетов и показывает сообщение, если их нет"""
    if not reports:
        if edit and isinstance(message, CallbackQuery):
            await message.message.edit_text("Отчетов не найдено.")
        else:
            await message.answer("Отчетов не найдено.")
        return False
    return True 