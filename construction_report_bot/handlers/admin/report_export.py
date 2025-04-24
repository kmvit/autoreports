import logging
import os
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from construction_report_bot.database.crud import (
    get_report_by_id,
    get_report_with_relations,
    get_all_reports
)
from construction_report_bot.database.models import Report, ReportPhoto
from construction_report_bot.config.settings import settings
from construction_report_bot.config.keyboards import (
    get_admin_report_menu_keyboard
)
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.utils.logging.logger import log_admin_action, log_error
from construction_report_bot.services.report_service import ReportService
from construction_report_bot.utils.export_utils import export_report_to_pdf, export_report_to_excel

logger = logging.getLogger(__name__)

# Создаем роутер для экспорта отчетов
admin_report_export_router = Router()
# Добавляем middleware для проверки роли
admin_report_export_router.message.middleware(admin_required())
admin_report_export_router.callback_query.middleware(admin_required())

# Обработчик для кнопки экспорта отчетов
@admin_report_export_router.callback_query(F.data == "export_report")
@error_handler
@with_session
async def process_export_reports_menu(callback: CallbackQuery, session: AsyncSession):
    """Обработка нажатия на кнопку экспорта отчетов"""
    await callback.answer()
    
    try:
        # Получаем все отчеты
        reports = await get_all_reports(session)
        
        if not reports:
            await callback.message.edit_text(
                "Отчетов не найдено.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Формируем клавиатуру с отчетами
        keyboard = []
        for report in reports:
            # Добавляем эмодзи в зависимости от статуса
            status_emoji = "✅" if report.status == "completed" else "📝"
            button_text = f"{status_emoji} {report.type} от {report.date.strftime('%d.%m.%Y %H:%M')}"
            callback_data = f"export_report_{report.id}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")])
        
        await callback.message.edit_text(
            "Выберите отчет для экспорта:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logging.error(f"Ошибка при получении списка отчетов: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении списка отчетов",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик для экспорта отчета
@admin_report_export_router.callback_query(F.data.startswith("export_report_"))
@error_handler
@with_session
async def process_export_report(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка экспорта отчета"""
    # Получаем ID отчета из callback_data
    report_id = int(callback.data.split("_")[2])
    logging.info(f"Попытка экспорта отчета #{report_id}")
    
    try:
        # Получаем отчет из БД
        report = await get_report_with_relations(session, report_id)
        if not report:
            logging.warning(f"[process_export_report] Отчет #{report_id} не найден в базе данных")
            await callback.message.edit_text(
                "Отчет не найден.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Сохраняем ID отчета в состоянии
        await state.update_data(report_id=report_id)
        
        # Создаем клавиатуру для выбора формата
        keyboard = [
            [InlineKeyboardButton(text="📊 Excel", callback_data=f"export_excel_{report_id}")],
            [InlineKeyboardButton(text="📄 PDF", callback_data=f"export_pdf_{report_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="export_report")]
        ]
        
        await callback.message.edit_text(
            "Выберите формат экспорта:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logging.error(f"Ошибка при подготовке экспорта отчета: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при подготовке экспорта отчета",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик для экспорта в Excel
@admin_report_export_router.callback_query(F.data.startswith("export_excel_"))
@error_handler
@with_session
async def process_export_excel(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка экспорта отчета в Excel"""
    # Получаем ID отчета из callback_data
    report_id = int(callback.data.split("_")[2])
    logging.info(f"Попытка экспорта отчета #{report_id} в Excel")
    
    try:
        # Получаем отчет из БД
        report = await get_report_with_relations(session, report_id)
        if not report:
            logging.warning(f"[process_export_excel] Отчет #{report_id} не найден в базе данных")
            await callback.message.edit_text(
                "Отчет не найден.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Создаем директорию для экспорта, если её нет
        export_dir = os.path.join(settings.BASE_DIR, settings.EXPORT_DIR)
        os.makedirs(export_dir, exist_ok=True)
        
        # Формируем имя файла
        filename = f"report_{report_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(export_dir, filename)
        
        # Экспортируем отчет в Excel
        export_report_to_excel([report], filepath)
        
        # Отправляем файл отчета
        document = FSInputFile(filepath)
        await callback.message.answer_document(
            document=document,
            caption=f"📊 Отчет #{report_id} успешно экспортирован в Excel"
        )
        
        # Возвращаемся в меню администратора
        await callback.message.edit_text(
            "Выберите действие:",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при экспорте отчета в Excel: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при экспорте отчета в Excel",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик для экспорта в PDF
@admin_report_export_router.callback_query(F.data.startswith("export_pdf_"))
@error_handler
@with_session
async def process_export_pdf(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка экспорта отчета в PDF"""
    # Получаем ID отчета из callback_data
    report_id = int(callback.data.split("_")[2])
    logging.info(f"Попытка экспорта отчета #{report_id} в PDF")
    
    try:
        # Получаем отчет из БД
        report = await get_report_with_relations(session, report_id)
        if not report:
            logging.warning(f"[process_export_pdf] Отчет #{report_id} не найден в базе данных")
            await callback.message.edit_text(
                "Отчет не найден.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Создаем директорию для экспорта, если её нет
        export_dir = os.path.join(settings.BASE_DIR, settings.EXPORT_DIR)
        os.makedirs(export_dir, exist_ok=True)
        
        # Формируем имя файла
        filename = f"report_{report_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(export_dir, filename)
        
        # Экспортируем отчет в PDF
        export_report_to_pdf([report], filepath)
        
        # Отправляем файл отчета
        document = FSInputFile(filepath)
        await callback.message.answer_document(
            document=document,
            caption=f"📄 Отчет #{report_id} успешно экспортирован в PDF"
        )
        
        # Возвращаемся в меню администратора
        await callback.message.edit_text(
            "Выберите действие:",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при экспорте отчета в PDF: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при экспорте отчета в PDF",
            reply_markup=await get_admin_report_menu_keyboard()
        ) 