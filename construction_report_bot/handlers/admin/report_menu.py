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
    get_object_by_id,
    get_reports_grouped_by_objects,
    delete_report
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
            # Группируем отчеты по объектам
            grouped_reports = {}
            for report in reports:
                object_id = report.object_id
                if object_id not in grouped_reports:
                    grouped_reports[object_id] = []
                grouped_reports[object_id].append(report)
            
            # Формируем клавиатуру с объектами
            keyboard = []
            for object_id, object_reports in grouped_reports.items():
                # Получаем информацию об объекте
                object_info = await get_object_by_id(session, object_id)
                if not object_info:
                    continue
                    
                # Подсчитываем количество отчетов для объекта
                report_count = len(object_reports)
                
                # Добавляем кнопку для объекта
                button_text = f"🏗️ {object_info.name} ({report_count} отчетов)"
                callback_data = f"date_object_reports_{date.strftime('%Y%m%d')}_{object_id}"
                keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
            
            # Добавляем кнопку "Назад"
            keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")])
            
            await message.answer(
                f"Выберите объект для просмотра отчетов за {date.strftime('%d.%m.%Y')}:",
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

@admin_report_menu_router.callback_query(F.data.startswith("date_object_reports_"))
@error_handler
@with_session
async def show_date_object_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать типы отчетов (утренний/вечерний) для выбранного объекта за определенную дату"""
    logger.info(f"[show_date_object_reports] Начало обработки callback_data: {callback.data}")
    
    # Получаем дату и ID объекта из callback_data
    parts = callback.data.split("_")
    date_str = parts[3]
    object_id = int(parts[4])
    logger.info(f"[show_date_object_reports] Извлечены данные: date_str={date_str}, object_id={object_id}")
    
    # Преобразуем строку даты в объект datetime
    date = datetime.strptime(date_str, '%Y-%m-%d')
    logger.info(f"[show_date_object_reports] Преобразована дата: {date}")
    
    # Получаем информацию об объекте
    object_info = await get_object_by_id(session, object_id)
    if not object_info:
        logger.error(f"[show_date_object_reports] Объект не найден: {object_id}")
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )
        return
    
    # Получаем отчеты для объекта
    reports = await get_reports_by_object(session, object_id)
    logger.info(f"[show_date_object_reports] Получено отчетов: {len(reports)}")
    
    # Фильтруем отчеты по дате
    filtered_reports = [r for r in reports if r.date.date() == date.date()]
    logger.info(f"[show_date_object_reports] Отфильтровано отчетов по дате: {len(filtered_reports)}")
    
    if filtered_reports:
        # Группируем отчеты по типу (утренний/вечерний)
        morning_reports = []
        evening_reports = []
        
        for report in filtered_reports:
            if report.type == "morning":
                morning_reports.append(report)
            else:
                evening_reports.append(report)
        
        logger.info(f"[show_date_object_reports] Утренних отчетов: {len(morning_reports)}, вечерних: {len(evening_reports)}")
        
        # Формируем клавиатуру с типами отчетов
        keyboard = []
        
        # Добавляем кнопку для утренних отчетов, если они есть
        if morning_reports:
            button_text = f"🌅 Утренний ({len(morning_reports)} отчетов)"
            callback_data = f"date_object_type_reports_{date_str}_{object_id}_morning"
            logger.info(f"[show_date_object_reports] Создана кнопка: {button_text} с callback_data: {callback_data}")
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку для вечерних отчетов, если они есть
        if evening_reports:
            button_text = f"🌆 Вечерний ({len(evening_reports)} отчетов)"
            callback_data = f"date_object_type_reports_{date_str}_{object_id}_evening"
            logger.info(f"[show_date_object_reports] Создана кнопка: {button_text} с callback_data: {callback_data}")
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="filter_reports_date")])
        
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            f"Отчетов для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')} не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )

@admin_report_menu_router.callback_query(F.data.startswith("date_object_type_reports_"))
@error_handler
@with_session
async def show_date_object_type_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать отчеты определенного типа для объекта за определенную дату"""
    logger.info(f"[show_date_object_type_reports] Начало обработки callback_data: {callback.data}")
    
    # Получаем дату, ID объекта и тип отчета из callback_data
    parts = callback.data.split("_")
    date_str = parts[4]
    object_id = int(parts[5])
    report_type = parts[6]
    
    logger.info(f"[show_date_object_type_reports] Извлечены данные: date_str={date_str}, object_id={object_id}, report_type={report_type}")
    
    # Преобразуем строку даты в объект datetime
    date = datetime.strptime(date_str, '%Y-%m-%d')
    logger.info(f"[show_date_object_type_reports] Преобразована дата: {date}")
    
    # Получаем информацию об объекте
    object_info = await get_object_by_id(session, object_id)
    if not object_info:
        logger.error(f"[show_date_object_type_reports] Объект не найден: {object_id}")
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )
        return
    
    # Получаем отчеты для объекта
    reports = await get_reports_by_object(session, object_id)
    logger.info(f"[show_date_object_type_reports] Получено отчетов: {len(reports)}")
    
    # Логируем все отчеты для отладки
    for report in reports:
        logger.info(f"[show_date_object_type_reports] Отчет: id={report.id}, date={report.date}, type={report.type}, report_type={report.report_type}, status={report.status}")
    
    # Фильтруем отчеты по дате и типу (утренний/вечерний)
    filtered_reports = []
    for report in reports:
        if report.date.date() == date.date():
            logger.info(f"[show_date_object_type_reports] Отчет {report.id} совпадает по дате")
            if report.type == report_type:
                logger.info(f"[show_date_object_type_reports] Отчет {report.id} совпадает по типу отчета")
                filtered_reports.append(report)
            else:
                logger.info(f"[show_date_object_type_reports] Отчет {report.id} не совпадает по типу отчета: {report.type} != {report_type}")
        else:
            logger.info(f"[show_date_object_type_reports] Отчет {report.id} не совпадает по дате: {report.date.date()} != {date.date()}")
    
    logger.info(f"[show_date_object_type_reports] Отфильтровано отчетов по дате и типу: {len(filtered_reports)}")
    
    if filtered_reports:
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        # Формируем клавиатуру с отчетами
        keyboard = []
        for report in filtered_reports:
            # Добавляем эмодзи в зависимости от статуса
            status_emoji = "✅" if report.status == "sent" else "📝"
            
            # Формируем текст кнопки с типом работ
            work_type = report.report_type or "Общие работы"
            button_text = f"{status_emoji} {report.date.strftime('%H:%M')} - {work_type}"
            
            # Создаем строку с двумя кнопками: для просмотра и удаления
            keyboard.append([
                InlineKeyboardButton(text=button_text, callback_data=f"edit_report_{report.id}"),
                InlineKeyboardButton(text="🗑️", callback_data=f"delete_report_{report.id}")
            ])
            
            logger.info(f"[show_date_object_type_reports] Создана кнопка: {button_text}")
        
        # Добавляем кнопку экспорта в PDF
        # Преобразуем дату в формат YYYYMMDD для callback_data
        date_for_callback = date.strftime('%Y%m%d')
        keyboard.append([InlineKeyboardButton(text="📄 Экспорт в PDF", callback_data=f"export_pdf_{object_id}_{date_for_callback}_{report_type}")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"date_object_reports_{date_str}_{object_id}")])
        
        await callback.message.edit_text(
            f"{type_name} отчеты для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            f"{type_name} отчетов для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')} не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"date_object_reports_{date_str}_{object_id}")]
            ])
        )

@admin_report_menu_router.callback_query(F.data == "show_all_reports")
@error_handler
@with_session
async def show_all_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать все отчеты без фильтрации, сгруппированные по объектам"""
    # Получаем отчеты, сгруппированные по объектам
    grouped_reports = await get_reports_grouped_by_objects(session, callback.from_user.id)
    
    if grouped_reports:
        # Формируем клавиатуру с объектами
        keyboard = []
        for object_id, reports in grouped_reports.items():
            # Получаем информацию об объекте
            object_info = await get_object_by_id(session, object_id)
            if not object_info:
                continue
                
            # Подсчитываем количество отчетов для объекта
            report_count = len(reports)
            
            # Добавляем кнопку для объекта
            button_text = f"🏗️ {object_info.name} ({report_count} отчетов)"
            callback_data = f"object_reports_{object_id}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")])
        
        await callback.message.edit_text(
            "Выберите объект для просмотра отчетов:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            "У вас пока нет отчетов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_reports")]
            ])
        )

# Добавляем обработчик для просмотра отчетов по объекту
@admin_report_menu_router.callback_query(F.data.startswith("object_reports_"))
@error_handler
@with_session
async def show_object_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать отчеты для конкретного объекта"""
    logger.info(f"[show_object_reports] Начало обработки callback_data: {callback.data}")
    
    # Получаем ID объекта из callback_data
    object_id = int(callback.data.split("_")[2])
    logger.info(f"[show_object_reports] Извлечен object_id: {object_id}")
    
    # Получаем информацию об объекте
    object_info = await get_object_by_id(session, object_id)
    if not object_info:
        logger.error(f"[show_object_reports] Объект не найден: {object_id}")
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        )
        return
    
    # Получаем отчеты для объекта
    reports = await get_reports_by_object(session, object_id)
    logger.info(f"[show_object_reports] Получено отчетов: {len(reports)}")
    
    if reports:
        # Группируем отчеты по датам
        reports_by_date = {}
        for report in reports:
            date_str = report.date.strftime('%Y-%m-%d')
            if date_str not in reports_by_date:
                reports_by_date[date_str] = []
            reports_by_date[date_str].append(report)
        
        logger.info(f"[show_object_reports] Сгруппировано по датам: {list(reports_by_date.keys())}")
        
        # Формируем клавиатуру с датами
        keyboard = []
        for date_str, date_reports in sorted(reports_by_date.items(), reverse=True):
            # Преобразуем дату в более читаемый формат
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d.%m.%Y')
            
            # Подсчитываем количество отчетов за дату
            report_count = len(date_reports)
            
            # Добавляем кнопку для даты
            button_text = f"📅 {formatted_date} ({report_count} отчетов)"
            callback_data = f"date_object_reports_{date_str}_{object_id}"
            logger.info(f"[show_object_reports] Создана кнопка: {button_text} с callback_data: {callback_data}")
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")])
        
        await callback.message.edit_text(
            f"Выберите дату для просмотра отчетов объекта '{object_info.name}':",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            f"Отчетов для объекта '{object_info.name}' не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        )

@admin_report_menu_router.callback_query(F.data.startswith("object_date_reports_"))
@error_handler
@with_session
async def show_object_date_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать типы отчетов (утренний/вечерний) для выбранной даты"""
    # Получаем ID объекта и дату из callback_data
    parts = callback.data.split("_")
    object_id = int(parts[3])
    date_str = parts[4]
    
    # Преобразуем строку даты в объект datetime
    date = datetime.strptime(date_str, '%Y-%m-%d')
    
    # Получаем информацию об объекте
    object_info = await get_object_by_id(session, object_id)
    if not object_info:
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        )
        return
    
    # Получаем отчеты для объекта
    reports = await get_reports_by_object(session, object_id)
    
    # Фильтруем отчеты по дате
    filtered_reports = [r for r in reports if r.date.date() == date.date()]
    
    if filtered_reports:
        # Группируем отчеты по типу (утренний/вечерний)
        reports_by_type = {}
        for report in filtered_reports:
            report_type = report.type
            if report_type not in reports_by_type:
                reports_by_type[report_type] = []
            reports_by_type[report_type].append(report)
        
        # Формируем клавиатуру с типами отчетов
        keyboard = []
        for report_type, type_reports in reports_by_type.items():
            # Определяем эмодзи и название типа отчета
            type_emoji = "🌅" if report_type == "morning" else "🌆"
            type_name = "Утренний" if report_type == "morning" else "Вечерний"
            
            # Подсчитываем количество отчетов данного типа
            report_count = len(type_reports)
            
            # Добавляем кнопку для типа отчета
            button_text = f"{type_emoji} {type_name} ({report_count} отчетов)"
            callback_data = f"object_date_type_reports_{object_id}_{date_str}_{report_type}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"object_reports_{object_id}")])
        
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            f"Отчетов для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')} не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"object_reports_{object_id}")]
            ])
        )

@admin_report_menu_router.callback_query(F.data.startswith("object_date_type_reports_"))
@error_handler
@with_session
async def show_object_date_type_reports(callback: CallbackQuery, session: AsyncSession):
    """Показать отчеты определенного типа для объекта за выбранную дату"""
    # Получаем ID объекта, дату и тип отчета из callback_data
    parts = callback.data.split("_")
    object_id = int(parts[4])
    date_str = parts[5]
    report_type = parts[6]
    
    # Преобразуем строку даты в объект datetime
    date = datetime.strptime(date_str, '%Y-%m-%d')
    
    # Получаем информацию об объекте
    object_info = await get_object_by_id(session, object_id)
    if not object_info:
        await callback.message.edit_text(
            "Объект не найден.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        )
        return
    
    # Получаем отчеты для объекта
    reports = await get_reports_by_object(session, object_id)
    
    # Фильтруем отчеты по дате и типу
    filtered_reports = [r for r in reports if r.date.date() == date.date() and r.type == report_type]
    
    if filtered_reports:
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning_report" else "Вечерний"
        
        # Формируем клавиатуру с отчетами
        keyboard = []
        for report in filtered_reports:
            # Добавляем эмодзи в зависимости от статуса
            status_emoji = "✅" if report.status == "sent" else "📝"
            
            # Формируем текст кнопки с типом работ
            work_type = report.report_type or "Общие работы"
            button_text = f"{status_emoji} {report.date.strftime('%H:%M')} - {work_type}"
            callback_data = f"edit_report_{report.id}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        # Добавляем кнопку экспорта в PDF
        # Преобразуем дату в формат YYYYMMDD для callback_data
        date_for_callback = date.strftime('%Y%m%d')
        keyboard.append([InlineKeyboardButton(text="📄 Экспорт в PDF", callback_data=f"export_pdf_{object_id}_{date_for_callback}_{report_type}")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"object_date_reports_{object_id}_{date_str}")])
        
        await callback.message.edit_text(
            f"{type_name} отчеты для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    else:
        await callback.message.edit_text(
            f"{type_name} отчетов для объекта '{object_info.name}' за {date.strftime('%d.%m.%Y')} не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"object_date_reports_{object_id}_{date_str}")]
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

@admin_report_menu_router.callback_query(F.data == "delete_report_7")
@error_handler
@with_session
async def delete_report_7(callback: CallbackQuery, session: AsyncSession):
    """Удаление отчета #7"""
    try:
        # Удаляем отчет
        success = await delete_report(session, 7)
        
        if success:
            await callback.message.edit_text(
                "Отчет #7 успешно удален.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
                ])
            )
        else:
            await callback.message.edit_text(
                "Ошибка при удалении отчета #7.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
                ])
            )
    except Exception as e:
        logger.error(f"Ошибка при удалении отчета #7: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при удалении отчета.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="show_all_reports")]
            ])
        ) 
