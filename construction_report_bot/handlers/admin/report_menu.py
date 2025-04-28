import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import List

from construction_report_bot.database.crud import (
    get_all_reports,
    get_report_by_id,
    get_reports_by_status,
    get_all_objects,
    get_all_itr,
    get_reports_by_object,
    get_reports_by_itr,
    get_reports_by_type,
    get_reports_by_date,
    get_object_by_id
)
from construction_report_bot.config.keyboards import get_admin_report_menu_keyboard, get_back_keyboard
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.utils.logging.logger import log_admin_action, log_error
from construction_report_bot.states.report_states import ReportStates, ReportManagementStates
from construction_report_bot.services.report_service import ReportService

logger = logging.getLogger(__name__)

# Создаем роутер для меню администратора
admin_report_menu_router = Router()
# Добавляем middleware для проверки роли
admin_report_menu_router.message.middleware(admin_required())
admin_report_menu_router.callback_query.middleware(admin_required())

# Обработчик для меню администратора
@admin_report_menu_router.message(F.text == "📝 Управление отчетами")
async def show_admin_report_menu(message: Message):
    """Показать меню администратора для отчетов"""
    keyboard = await get_admin_report_menu_keyboard()
    await message.answer(
        "Меню администратора для отчетов:",
        reply_markup=keyboard
    )

@admin_report_menu_router.callback_query(F.data == "admin_report_menu")
async def show_admin_report_menu_callback(callback: CallbackQuery):
    """Показать меню администратора для отчетов через callback"""
    keyboard = await get_admin_report_menu_keyboard()
    await callback.message.edit_text(
        "Меню администратора для отчетов:",
        reply_markup=keyboard
    )

@admin_report_menu_router.callback_query(F.data == "my_reports")
@error_handler
@with_session
async def process_my_reports(callback: CallbackQuery, session: AsyncSession):
    """Обработка просмотра своих отчетов"""
    # Создаем клавиатуру с фильтром по дате
    keyboard = [
        [InlineKeyboardButton(text="📅 По дате", callback_data="filter_reports_date")],
        [InlineKeyboardButton(text="📋 Показать все", callback_data="show_all_reports")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")]
    ]
    
    await callback.message.edit_text(
        "Выберите фильтр для просмотра отчетов:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@admin_report_menu_router.callback_query(F.data.startswith("filter_reports_"))
@error_handler
@with_session
async def apply_report_filter(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Применение фильтра к отчетам"""
    filter_type = callback.data.replace("filter_reports_", "")
    
    # Сохраняем тип фильтра в состоянии
    await state.update_data(filter_type=filter_type)
    
    if filter_type == "date":
        # Запрашиваем дату
        await callback.message.edit_text(
            "Введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )
        await state.set_state(ReportStates.waiting_for_date)

@admin_report_menu_router.message(ReportStates.waiting_for_date)
@error_handler
@with_session
async def process_date_filter(message: Message, session: AsyncSession, state: FSMContext):
    """Обработка ввода даты для фильтрации"""
    try:
        # Парсим дату
        date = datetime.strptime(message.text, "%d.%m.%Y")
        
        # Получаем отчеты по дате
        reports = await get_reports_by_date(session, date)
        
        if reports:
            # Формируем клавиатуру с отчетами
            keyboard = []
            for report in reports:
                report_object = await get_object_by_id(session, report.object_id)
                # Добавляем эмодзи в зависимости от статуса
                status_emoji = "✅" if report.status == "completed" else "📝"
                button_text = f"{status_emoji} {report_object.name} {report.type} от {report.date.strftime('%d.%m.%Y %H:%M')}"
                callback_data = f"edit_report_{report.id}"
                keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
            
            # Добавляем кнопку "Назад"
            keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")])
            
            await message.answer(
                f"Отчеты за {date.strftime('%d.%m.%Y')}:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
        else:
            await message.answer(
                f"Отчетов за {date.strftime('%d.%m.%Y')} не найдено.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
                ])
            )
        
        # Сбрасываем состояние
        await state.clear()
        
    except ValueError:
        await message.answer(
            "Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )

@admin_report_menu_router.callback_query(F.data == "show_all_reports")
@error_handler
@with_session
async def show_all_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать все отчеты без фильтрации"""
    # Получаем все отчеты пользователя
    reports = await get_all_reports(session, callback.from_user.id)
    
    if reports:
        # Формируем клавиатуру с отчетами
        keyboard = []
        for report in reports:

            report_object = await get_object_by_id(session, report.object_id)
            
            # Добавляем эмодзи в зависимости от статуса
            status_emoji = "✅" if report.status == "sent" else "📝"
            button_text = f"{status_emoji} {report_object.name} {report.type} от {report.date.strftime('%d.%m.%Y %H:%M')}"
            callback_data = f"edit_report_{report.id}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
            
            # Добавляем кнопку удаления для каждого отчета
            delete_button_text = f"🗑️ Удалить"
            delete_callback_data = f"delete_report_{report.id}"
            keyboard.append([InlineKeyboardButton(text=delete_button_text, callback_data=delete_callback_data)])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")])
        
        await callback.message.edit_text(
            "Ваши отчеты:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            "У вас пока нет отчетов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )

@admin_report_menu_router.message(Command("reports"))
@error_handler
async def cmd_reports(message: Message, state: FSMContext):
    """Обработчик команды /reports"""
    await state.set_state(ReportManagementStates.waiting_for_type)
    await message.answer(
        "Выберите тип отчета:",
        reply_markup=get_report_type_keyboard()
    )

# Функция для получения клавиатуры типов отчетов
def get_report_type_keyboard():
    """Получить клавиатуру для выбора типа отчета"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Утренний", callback_data="morning_report")],
        [InlineKeyboardButton(text="Вечерний", callback_data="evening_report")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")]
    ])
    return keyboard 
