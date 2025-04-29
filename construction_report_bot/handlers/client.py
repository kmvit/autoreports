"""Модуль обработчиков для клиентского интерфейса бота.
Содержит обработчики для просмотра отчетов, их фильтрации и взаимодействия
с системой отчетности для клиентов строительной компании.
"""

import logging
from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery, User
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import Optional, List, Union, Dict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import os

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from construction_report_bot.middlewares.role_check import client_required
from construction_report_bot.database.crud import (
    get_report_by_id, get_report_with_relations, get_reports_by_object, get_today_reports,
    get_client_by_user_id, get_reports_by_type, get_reports_by_date, get_object_by_id
)
from construction_report_bot.database.session import get_session
from construction_report_bot.config.keyboards import (
    get_report_filter_keyboard, get_back_keyboard, create_report_type_keyboard,
    create_object_keyboard, create_reports_list_keyboard
)
from construction_report_bot.config.settings import settings
from construction_report_bot.utils.decorators import with_session, error_handler
from construction_report_bot.utils.utils import (
    handle_error, get_object_info, format_datetime, check_reports_exist
)
from construction_report_bot.database.models import Report, Client, Object

# Создаем логгер
logger = logging.getLogger(__name__)

# Создаем роутер для клиента
client_router = Router()

# Добавляем middleware для проверки роли
client_router.message.middleware(client_required())
client_router.callback_query.middleware(client_required())

# Состояния FSM для фильтрации отчетов
class ReportFilterStates(StatesGroup):
    """Состояния FSM для фильтрации отчетов.
    
    Attributes:
        waiting_for_date: Ожидание ввода даты
        waiting_for_object: Ожидание выбора объекта
        waiting_for_report_type: Ожидание выбора типа отчета
    """
    waiting_for_date = State()
    waiting_for_object = State()
    waiting_for_report_type = State()

# Обработчик просмотра истории отчетов
@client_router.message(F.text == "📊 История отчетов")
@with_session
async def cmd_report_history(message: Message, session: AsyncSession, state: FSMContext, **data):
    """Обработчик команды просмотра истории отчетов"""
    try:
        user = data["user"]
        client = await get_client_by_user_id(session, user.id)
        
        if not client:
            await message.answer("Ваш профиль не найден. Обратитесь к администратору.")
            return
        
        objects = client.objects
        if not objects:
            await message.answer("У вас нет доступных объектов. Обратитесь к администратору.")
            return
        
        # Создаем список объектов для клавиатуры
        objects_list = [{"id": obj.id, "name": obj.name} for obj in objects]
        keyboard = create_object_keyboard(objects_list, "back_to_main")
        
        await message.answer(
            "Выберите объект для просмотра истории отчетов:",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await handle_error(message, e)

@client_router.callback_query(F.data.startswith("history_object_"))
@with_session
async def process_history_object(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Обработчик выбора объекта в истории отчетов"""
    try:
        object_id = int(callback.data.split('_')[-1])
        object_info, object_name = await get_object_info(session, object_id)
        
        if not object_info:
            await callback.message.edit_text("Объект не найден.")
            return
        
        reports = await get_reports_by_object(session, object_id)
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Группируем отчеты по датам
        dates = {}
        for report in reports:
            date_str = report.date.strftime('%Y-%m-%d')
            if date_str not in dates:
                dates[date_str] = []
            dates[date_str].append(report)
        
        # Создаем клавиатуру с датами
        keyboard = []
        for date_str in sorted(dates.keys(), reverse=True):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_str, _ = format_datetime(date_obj)
            report_count = len(dates[date_str])
            
            keyboard.append([InlineKeyboardButton(
                text=f"📅 {date_str} ({report_count} отчетов)",
                callback_data=f"history_date_{object_id}_{date_str}"
            )])
        
        keyboard.append([InlineKeyboardButton(
            text="🔙 Назад к списку объектов",
            callback_data="back_to_history"
        )])
        
        await callback.message.edit_text(
            f"Выберите дату для просмотра отчетов по объекту {object_name}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("history_date_"))
@with_session
async def process_history_date(callback: CallbackQuery, session: AsyncSession):
    """Обработчик выбора даты в истории отчетов"""
    try:
        _, _, object_id, date_str = callback.data.split('_')
        object_id = int(object_id)
        
        object_info, object_name = await get_object_info(session, object_id)
        if not object_info:
            await callback.message.edit_text("Объект не найден.")
            return
        
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        # Фильтруем отчеты по дате
        reports = [r for r in reports if r.date.date() == date_obj.date()]
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Создаем клавиатуру с типами отчетов
        keyboard = create_report_type_keyboard(reports, object_id, date_str)
        
        date_str, _ = format_datetime(date_obj)
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_name}' за {date_str}:",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("history_type_"))
@with_session
async def process_history_type(callback: CallbackQuery, session: AsyncSession):
    """Обработчик выбора типа отчета в истории"""
    try:
        _, _, object_id, date_str, report_type = callback.data.split('_')
        object_id = int(object_id)
        
        object_info, object_name = await get_object_info(session, object_id)
        if not object_info:
            await callback.message.edit_text("Объект не найден.")
            return
        
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        # Фильтруем отчеты по дате и типу
        reports = [r for r in reports if r.date.date() == date_obj.date() and r.type == report_type]
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        # Формируем текст с информацией о выбранных отчетах
        date_str, _ = format_datetime(date_obj)
        reports_text = f"{type_name} отчеты для объекта '{object_name}' за {date_str}:\n\n"
        
        # Добавляем информацию о каждом отчете
        for i, report in enumerate(reports, start=1):
            time_str = report.date.strftime("%H:%M")
            reports_text += f"{i}. {time_str} - {report.report_type or 'Общие работы'}\n"
        
        # Создаем клавиатуру с кнопкой экспорта в PDF
        keyboard = [
            [
                InlineKeyboardButton(
                    text="📥 Экспорт в PDF",
                    callback_data=f"client_export_pdf_{object_id}_{date_str}_{report_type}"
                )
            ],
            [InlineKeyboardButton(
                text="🔙 Назад к выбору типа отчета",
                callback_data=f"history_date_{object_id}_{date_str}"
            )]
        ]
        
        await callback.message.edit_text(
            reports_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data == "back_to_history")
async def process_back_to_history(callback: CallbackQuery):
    """Обработчик возврата к списку объектов в истории отчетов"""
    try:
        await cmd_report_history(callback.message, callback.message.bot.session, callback.message.bot.state)
    except Exception as e:
        await handle_error(callback, e)

# Обработчик просмотра отчета за сегодня
@client_router.message(F.text == "📑 Отчет за сегодня")
@with_session
async def cmd_today_report(message: Message, session: AsyncSession, state: FSMContext, **data):
    """Обработчик команды просмотра отчета за сегодня"""
    try:
        # Получаем клиента по ID пользователя
        user = data["user"]
        client = await get_client_by_user_id(session, user.id)
        
        if not client:
            await message.answer("❌ Ваш профиль не найден. Обратитесь к администратору.")
            return
        
        # Получаем доступные объекты клиента
        objects = client.objects
        
        if not objects:
            await message.answer("❌ У вас нет доступных объектов. Обратитесь к администратору.")
            return
        
        # Создаем список объектов для клавиатуры
        objects_list = [{"id": obj.id, "name": obj.name} for obj in objects]
        keyboard = create_object_keyboard(objects_list, "back_to_main", "today_report_object_")
        
        await message.answer(
            "📊 Выберите объект для просмотра отчетов за сегодня:",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await handle_error(message, e)

@client_router.callback_query(F.data.startswith("today_report_object_"))
@with_session
async def process_today_report_object(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Обработка выбора объекта для просмотра отчетов за сегодня"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта из callback_data
        object_id = int(callback.data.split("_")[-1])
        
        # Получаем отчеты за сегодня для выбранного объекта
        reports = await get_today_reports(session, object_id)
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        # Сохраняем ID объекта в состоянии
        await state.update_data(selected_object_id=object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Группируем отчеты по типу (утренний/вечерний)
        morning_reports = [r for r in reports if r.type == "morning"]
        evening_reports = [r for r in reports if r.type == "evening"]
        
        # Создаем клавиатуру с типами отчетов
        keyboard = []
        
        if morning_reports:
            keyboard.append([InlineKeyboardButton(
                text=f"🌅 Утренний ({len(morning_reports)} отчетов)",
                callback_data=f"today_report_type_{object_id}_morning"
            )])
        
        if evening_reports:
            keyboard.append([InlineKeyboardButton(
                text=f"🌆 Вечерний ({len(evening_reports)} отчетов)",
                callback_data=f"today_report_type_{object_id}_evening"
            )])
        
        
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_name}' за сегодня:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("today_report_type_"))
@with_session
async def process_today_report_type(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """Обработка выбора типа отчета для просмотра отчетов за сегодня"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта и тип отчета из callback_data
        parts = callback.data.split("_")
        object_id = int(parts[3])
        report_type = parts[4]
        
        # Получаем отчеты за сегодня для выбранного объекта и типа
        reports = await get_today_reports(session, object_id, report_type)
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Формируем текст с информацией о выбранных отчетах
        date_str, _ = format_datetime(datetime.now())
        reports_text = f"{type_name} отчеты для объекта '{object_name}' за сегодня ({date_str}):\n\n"
        
        # Добавляем информацию о каждом отчете
        for i, report in enumerate(reports, start=1):
            time_str = report.date.strftime("%H:%M")
            reports_text += f"{i}. {time_str} - {report.report_type or 'Общие работы'}\n"
        
        # Создаем клавиатуру с кнопкой экспорта в PDF
        keyboard = [
            [
                InlineKeyboardButton(
                    text="📥 Экспорт в PDF",
                    callback_data=f"client_export_pdf_{object_id}_{datetime.now().strftime('%d.%m.%Y')}_{report_type}"
                )
            ],
            [InlineKeyboardButton(
                text="🔙 Назад к выбору типа отчета",
                callback_data=f"today_report_object_{object_id}"
            )]
        ]
        
        await callback.message.edit_text(
            reports_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        await handle_error(callback, e)

# Обработчик фильтрации по дате
@client_router.callback_query(F.data == "filter_date")
async def process_filter_date(callback: CallbackQuery, state: FSMContext):
    """Обработка фильтрации отчетов по дате"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Введите дату в формате ДД.ММ.ГГГГ:"
    )
    
    await state.set_state(ReportFilterStates.waiting_for_date)

@client_router.message(ReportFilterStates.waiting_for_date)
@with_session
async def process_date_input(message: Message, state: FSMContext, session: AsyncSession, **data):
    """Обработка ввода даты для фильтрации"""
    date_str = message.text.strip()
    
    try:
        # Парсим дату
        filter_date = datetime.strptime(date_str, '%d.%m.%Y')
        
        # Получаем клиента
        user = data["user"]
        client = await get_client_by_user_id(session, user.id)
        
        if not client:
            await message.answer("Ваш профиль не найден. Обратитесь к администратору.")
            return
        
        # Получаем отчеты по дате
        reports = await get_reports_by_date(session, filter_date)
        
        # Фильтруем отчеты по объектам клиента
        filtered_reports = await filter_reports_by_client_objects(reports, client)
        
        if filtered_reports:
            # Группируем отчеты по объектам
            reports_by_object = {}
            for report in filtered_reports:
                if report.object_id not in reports_by_object:
                    reports_by_object[report.object_id] = []
                reports_by_object[report.object_id].append(report)
            
            # Создаем клавиатуру с объектами
            keyboard = []
            for object_id, object_reports in reports_by_object.items():
                object_info, object_name = await get_object_info(session, object_id)
                report_count = len(object_reports)
                
                keyboard.append([InlineKeyboardButton(
                    text=f"🏗️ {object_name} ({report_count} отчетов)",
                    callback_data=f"filter_date_object_{object_id}_{date_str}"
                )])
            
            # Добавляем кнопку "Назад"
            keyboard.append([InlineKeyboardButton(
                text="🔙 Назад к фильтрам",
                callback_data="back_to_filters"
            )])
            
            await message.answer(
                f"Выберите объект для просмотра отчетов за {date_str}:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
        else:
            await message.answer(
                f"За {date_str} отчетов по вашим объектам не найдено.",
                reply_markup=get_back_keyboard()
            )
        
        # Сбрасываем состояние
        await state.clear()
        
    except ValueError:
        await message.answer(
            "Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ."
        )
    except Exception as e:
        await handle_error(message, e)
        await state.clear()

@client_router.callback_query(F.data.startswith("filter_date_object_"))
@with_session
async def process_filter_date_object(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора объекта для фильтрации по дате"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта и дату из callback_data
        _, _, object_id, date_str = callback.data.split("_")
        object_id = int(object_id)
        date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по дате
        filtered_reports = [r for r in reports if r.date.date() == date.date()]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Создаем клавиатуру с типами отчетов
        keyboard = create_report_type_keyboard(filtered_reports, object_id, date_str)
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        date_str, _ = format_datetime(date)
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_name}' за {date_str}:",
            reply_markup=keyboard
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data == "filter_object")
@with_session
async def process_filter_object(callback: CallbackQuery, state: FSMContext, session: AsyncSession, **data):
    """Обработка фильтрации отчетов по объекту"""
    await callback.answer()
    
    try:
        # Получаем клиента
        user = data["user"]
        client = await get_client_by_user_id(session, user.id)
        
        if not client or not client.objects:
            await callback.message.edit_text(
                "У вас нет доступных объектов. Обратитесь к администратору.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Создаем список объектов для клавиатуры
        objects_list = [{"id": obj.id, "name": obj.name} for obj in client.objects]
        keyboard = create_object_keyboard(objects_list)
        
        await callback.message.edit_text(
            "Выберите объект:",
            reply_markup=keyboard
        )
        await state.set_state(ReportFilterStates.waiting_for_object)
        
        # Сохраняем список объектов в состоянии
        await state.update_data(objects={i: obj.id for i, obj in enumerate(client.objects, start=1)})
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("select_object_"))
@with_session
async def process_object_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора объекта через кнопку"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта из callback_data
        object_id = int(callback.data.split("_")[2])
        
        # Получаем отчеты по объекту
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Группируем отчеты по датам
        reports_by_date = {}
        for report in reports:
            date_str = report.date.strftime('%Y-%m-%d')
            if date_str not in reports_by_date:
                reports_by_date[date_str] = []
            reports_by_date[date_str].append(report)
        
        # Формируем клавиатуру с датами
        keyboard = []
        for date_str, date_reports in sorted(reports_by_date.items(), reverse=True):
            # Преобразуем дату в более читаемый формат
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_str, _ = format_datetime(date_obj)
            
            # Подсчитываем количество отчетов за дату
            report_count = len(date_reports)
            
            # Добавляем кнопку для даты
            keyboard.append([InlineKeyboardButton(
                text=f"📅 {date_str} ({report_count} отчетов)",
                callback_data=f"filter_object_date_{object_id}_{date_str}"
            )])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(
            text="🔙 Назад к фильтрам",
            callback_data="back_to_filters"
        )])
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        await callback.message.edit_text(
            f"Выберите дату для просмотра отчетов объекта '{object_name}':",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        await handle_error(callback, e)
    
    # Сбрасываем состояние
    await state.clear()

@client_router.callback_query(F.data.startswith("filter_object_date_"))
@with_session
async def process_filter_object_date(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора даты для фильтрации по объекту"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта и дату из callback_data
        parts = callback.data.split("_")
        object_id = int(parts[3])
        date_str = parts[4]
        
        # Преобразуем дату из формата ДД.ММ.ГГГГ в объект datetime
        try:
            date = datetime.strptime(date_str, '%d.%m.%Y')
        except ValueError:
            # Если не удалось, пробуем другой формат
            date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по дате
        filtered_reports = [r for r in reports if r.date.date() == date.date()]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Создаем клавиатуру с типами отчетов
        keyboard = create_report_type_keyboard(filtered_reports, object_id, date_str)
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        date_str, _ = format_datetime(date)
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_name}' за {date_str}:",
            reply_markup=keyboard
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data == "filter_report_type")
async def process_filter_report_type(callback: CallbackQuery, state: FSMContext):
    """Обработка фильтрации отчетов по типу"""
    await callback.answer()
    
    # Создаем клавиатуру с кнопками для выбора типа отчета
    keyboard = [
        [InlineKeyboardButton(text="1. Утренний", callback_data="select_report_type_morning")],
        [InlineKeyboardButton(text="2. Вечерний", callback_data="select_report_type_evening")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_filters")]
    ]
    
    await callback.message.edit_text(
        "Выберите тип отчета:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    
    await state.set_state(ReportFilterStates.waiting_for_report_type)

@client_router.callback_query(F.data.startswith("select_report_type_"))
@with_session
async def process_report_type_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession, **data):
    """Обработка выбора типа отчета через кнопку"""
    await callback.answer()
    
    try:
        # Извлекаем тип отчета из callback_data
        report_type = callback.data.split("_")[3]  # morning или evening
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        # Получаем клиента
        user = data["user"]
        client = await get_client_by_user_id(session, user.id)
        
        if not client:
            await callback.message.edit_text(
                "Ваш профиль не найден. Обратитесь к администратору.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Получаем отчеты по типу
        reports = await get_reports_by_type(session, report_type)
        
        # Фильтруем отчеты по объектам клиента
        filtered_reports = await filter_reports_by_client_objects(reports, client)
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Группируем отчеты по объектам
        reports_by_object = {}
        for report in filtered_reports:
            if report.object_id not in reports_by_object:
                reports_by_object[report.object_id] = []
            reports_by_object[report.object_id].append(report)
        
        # Создаем клавиатуру с объектами
        keyboard = []
        for object_id, object_reports in reports_by_object.items():
            object_info, object_name = await get_object_info(session, object_id)
            report_count = len(object_reports)
            
            keyboard.append([InlineKeyboardButton(
                text=f"🏗️ {object_name} ({report_count} отчетов)",
                callback_data=f"filter_type_object_{object_id}_{report_type}"
            )])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(
            text="🔙 Назад к фильтрам",
            callback_data="back_to_filters"
        )])
        
        await callback.message.edit_text(
            f"Выберите объект для просмотра {type_name.lower()} отчетов:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        await handle_error(callback, e)
    
    # Сбрасываем состояние
    await state.clear()

@client_router.callback_query(F.data.startswith("filter_type_object_"))
@with_session
async def process_filter_type_object(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора объекта для фильтрации по типу"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта и тип отчета из callback_data
        _, _, object_id, report_type = callback.data.split("_")
        object_id = int(object_id)
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по типу
        filtered_reports = [r for r in reports if r.type == report_type]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Группируем отчеты по датам
        reports_by_date = {}
        for report in filtered_reports:
            date_str = report.date.strftime('%Y-%m-%d')
            if date_str not in reports_by_date:
                reports_by_date[date_str] = []
            reports_by_date[date_str].append(report)
        
        # Формируем клавиатуру с датами
        keyboard = []
        for date_str, date_reports in sorted(reports_by_date.items(), reverse=True):
            # Преобразуем дату в более читаемый формат
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_str, _ = format_datetime(date_obj)
            
            # Подсчитываем количество отчетов за дату
            report_count = len(date_reports)
            
            # Добавляем кнопку для даты
            keyboard.append([InlineKeyboardButton(
                text=f"📅 {date_str} ({report_count} отчетов)",
                callback_data=f"filter_type_date_{object_id}_{date_str}_{report_type}"
            )])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(
            text="🔙 Назад к выбору объекта",
            callback_data=f"select_report_type_{report_type}"
        )])
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        await callback.message.edit_text(
            f"Выберите дату для просмотра {type_name.lower()} отчетов объекта '{object_name}':",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("filter_type_date_"))
@with_session
async def process_filter_type_date(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора даты для фильтрации по типу и объекту"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта, дату и тип отчета из callback_data
        _, _, object_id, date_str, report_type = callback.data.split("_")
        object_id = int(object_id)
        date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по дате и типу
        filtered_reports = [r for r in reports if r.date.date() == date.date() and r.type == report_type]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        # Формируем текст с информацией о выбранных отчетах
        date_str, _ = format_datetime(date)
        reports_text = f"{type_name} отчеты для объекта '{object_name}' за {date_str}:\n\n"
        
        # Добавляем информацию о каждом отчете
        for i, report in enumerate(filtered_reports, start=1):
            time_str = report.date.strftime("%H:%M")
            reports_text += f"{i}. {time_str} - {report.report_type or 'Общие работы'}\n"
        
        # Создаем клавиатуру с кнопкой экспорта в PDF
        keyboard = [
            [
                InlineKeyboardButton(
                    text="📄 Экспорт в PDF",
                    callback_data=f"client_export_pdf_{object_id}_{date_str}_{report_type}"
                )
            ],
            [InlineKeyboardButton(
                text="🔙 Назад к выбору даты",
                callback_data=f"filter_type_object_{object_id}_{report_type}"
            )]
        ]
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        await callback.message.edit_text(
            reports_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        await handle_error(callback, e)

# Обработчик просмотра конкретного отчета
@client_router.callback_query(F.data.startswith("view_report_"))
@error_handler
@with_session
async def process_view_report(callback: CallbackQuery, session: AsyncSession):
    """Обработчик просмотра конкретного отчета"""
    try:
        report_id = int(callback.data.split("_")[-1])
        report = await get_report_with_relations(session, report_id)
        
        if not report:
            await callback.message.edit_text(
                "Отчет не найден",
                reply_markup=get_back_keyboard("back_to_reports")
            )
            return
            
        object_info, object_name = await get_object_info(session, report.object_id)
        
        # Форматируем дату и время
        date_str, time_str = format_datetime(report.date)
        
        # Форматируем тип отчета
        report_type = "Утренний" if report.type == "morning" else "Вечерний"
        
        # Форматируем комментарии
        comments = report.comments if report.comments else "Нет комментариев"
        
        # Форматируем статус
        status = "Подтвержден" if report.status == "sent" else "На проверке"
        
        message_text = (
            f"📊 Отчет #{report.id}\n\n"
            f"📅 Дата: {date_str}\n"
            f"⏰ Время: {time_str}\n"
            f"🏗 Объект: {object_name}\n"
            f"📝 Тип отчета: {report_type}\n"
            f"💬 Комментарии: {comments}\n"
            f"✅ Статус: {status}\n"
        )
        
        # Создаем клавиатуру с кнопкой "Назад"
        keyboard = get_back_keyboard("back_to_reports")
        
        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
    except Exception as e:
        await handle_error(callback, e)

# Обработчик возврата к списку отчетов
@client_router.callback_query(F.data == "back_to_reports_list")
async def process_back_to_reports_list(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к списку отчетов"""
    await callback.answer()
    
    # Получаем данные из состояния
    state_data = await state.get_data()
    
    # Если есть сохраненные отчеты, возвращаемся к списку
    if "reports" in state_data:
        # Здесь можно реализовать возврат к списку отчетов
        # Но для простоты просто возвращаемся к фильтрам
        await callback.message.edit_text(
            "История отчетов. Выберите фильтр:",
            reply_markup=get_report_filter_keyboard()
        )
    else:
        # Если нет сохраненных отчетов, возвращаемся к фильтрам
        await callback.message.edit_text(
            "История отчетов. Выберите фильтр:",
            reply_markup=get_report_filter_keyboard()
        )

# Обработчик сброса фильтров
@client_router.callback_query(F.data == "filter_reset")
async def process_filter_reset(callback: CallbackQuery):
    """Обработка сброса фильтров"""
    await callback.answer("Фильтры сброшены")
    
    await callback.message.edit_text(
        "Фильтры сброшены. Выберите новый фильтр:",
        reply_markup=get_report_filter_keyboard()
    )

# Обработчик возврата к фильтрам
@client_router.callback_query(F.data == "back_to_filters")
async def process_back_to_filters(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к фильтрам"""
    await callback.answer()
    
    # Сбрасываем состояние
    await state.clear()
    
    # Показываем меню фильтров
    await callback.message.edit_text(
        "История отчетов. Выберите фильтр:",
        reply_markup=get_report_filter_keyboard()
    )

# Обработчик просмотра отчетов по объектам
@client_router.callback_query(F.data == "view_object_reports")
@error_handler
@with_session
async def process_view_object_reports(callback: CallbackQuery, session: AsyncSession):
    """Обработка просмотра отчетов по объектам"""
    try:
        # Получаем клиента
        client = await get_client_by_user_id(session, callback.from_user.id)
        
        if not client or not client.objects:
            await callback.message.edit_text(
                "У вас нет доступных объектов. Обратитесь к администратору.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Создаем список объектов для клавиатуры
        objects_list = []
        for obj in client.objects:
            # Получаем отчеты для объекта
            reports = await get_reports_by_object(session, obj.id)
            report_count = len(reports) if reports else 0
            
            objects_list.append({
                "id": obj.id,
                "name": f"🏗️ {obj.name} ({report_count} отчетов)"
            })
        
        keyboard = create_object_keyboard(objects_list, "back_to_filters")
        
        await callback.message.edit_text(
            "Выберите объект для просмотра отчетов:",
            reply_markup=keyboard
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("client_object_reports_"))
@error_handler
@with_session
async def process_client_object_reports(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора объекта для просмотра отчетов"""
    try:
        # Получаем ID объекта из callback_data
        object_id = int(callback.data.replace("client_object_reports_", ""))
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Группируем отчеты по датам
        reports_by_date = {}
        for report in reports:
            date_str = report.date.strftime('%Y-%m-%d')
            if date_str not in reports_by_date:
                reports_by_date[date_str] = []
            reports_by_date[date_str].append(report)
        
        # Формируем клавиатуру с датами
        keyboard = []
        for date_str, date_reports in sorted(reports_by_date.items(), reverse=True):
            # Преобразуем дату в более читаемый формат
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_str, _ = format_datetime(date_obj)
            
            # Подсчитываем количество отчетов за дату
            report_count = len(date_reports)
            
            # Добавляем кнопку для даты
            keyboard.append([InlineKeyboardButton(
                text=f"📅 {date_str} ({report_count} отчетов)",
                callback_data=f"client_date_object_reports_{date_str}_{object_id}"
            )])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="view_object_reports"
        )])
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        await callback.message.edit_text(
            f"Выберите дату для просмотра отчетов объекта '{object_name}':",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("client_date_object_reports_"))
@error_handler
@with_session
async def process_client_date_object_reports(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора даты для просмотра отчетов объекта"""
    try:
        # Получаем дату и ID объекта из callback_data
        _, date_str, object_id = callback.data.split("_", 2)
        date = datetime.strptime(date_str, '%Y-%m-%d')
        object_id = int(object_id)
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по дате
        filtered_reports = [r for r in reports if r.date.date() == date.date()]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Создаем клавиатуру с типами отчетов
        keyboard = create_report_type_keyboard(filtered_reports, object_id, date_str)
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        date_str, _ = format_datetime(date)
        await callback.message.edit_text(
            f"Выберите тип отчета для объекта '{object_name}' за {date_str}:",
            reply_markup=keyboard
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("client_date_object_type_reports_"))
@error_handler
@with_session
async def process_client_date_object_type_reports(callback: CallbackQuery, session: AsyncSession):
    """Обработка выбора типа отчета для просмотра"""
    await callback.answer()
    
    try:
        # Извлекаем дату, ID объекта и тип отчета из callback_data
        # Формат: client_date_object_type_reports_[date]_[object_id]_[type]
        parts = callback.data.split("_")
        date_str = parts[5]  # Получаем дату из callback_data
        object_id = int(parts[6])  # Получаем ID объекта из callback_data
        report_type = parts[7]  # Получаем тип отчета из callback_data
        
        # Преобразуем дату из формата ДД.ММ.ГГГГ в объект datetime
        try:
            date = datetime.strptime(date_str, '%d.%m.%Y')
        except ValueError:
            # Если не удалось, пробуем другой формат
            date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по дате и типу
        filtered_reports = [r for r in reports if r.date.date() == date.date() and r.type == report_type]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
        
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        # Формируем текст с информацией о выбранных отчетах
        date_str, _ = format_datetime(date)
        reports_text = f"{type_name} отчеты для объекта '{object_name}' за {date_str}:\n\n"
        
        # Добавляем информацию о каждом отчете
        for i, report in enumerate(filtered_reports, start=1):
            time_str = report.date.strftime("%H:%M")
            reports_text += f"{i}. {time_str} - {report.report_type or 'Общие работы'}\n"
        
        # Создаем клавиатуру с кнопкой экспорта в PDF
        keyboard = [
            [
                InlineKeyboardButton(
                    text="📥 Экспорт в PDF",
                    callback_data=f"client_export_pdf_{object_id}_{date_str}_{report_type}"
                )
            ],
            [InlineKeyboardButton(
                text="🔙 Назад к выбору типа отчета",
                callback_data=f"client_date_object_reports_{date_str}_{object_id}"
            )]
        ]
        
        await callback.message.edit_text(
            reports_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        await handle_error(callback, e)

@client_router.callback_query(F.data.startswith("client_export_pdf_"))
@error_handler
@with_session
async def process_client_export_pdf(callback: CallbackQuery, session: AsyncSession, user: User):
    """Обработка экспорта отчетов в PDF для клиентов"""
    await callback.answer()
    
    try:
        # Извлекаем ID объекта, дату и тип отчета из callback_data
        parts = callback.data.split("_")
        object_id = int(parts[3])
        date_str = parts[4]
        report_type = parts[5]
        
        # Преобразуем дату из формата ДД.ММ.ГГГГ в объект datetime
        try:
            date = datetime.strptime(date_str, '%d.%m.%Y')
        except ValueError:
            # Если не удалось, пробуем другой формат
            date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Получаем отчеты для объекта
        reports = await get_reports_by_object(session, object_id)
        
        if not await check_reports_exist(callback, reports, edit=True):
            return
        
        # Фильтруем отчеты по дате и типу
        filtered_reports = [r for r in reports if r.date.date() == date.date() and r.type == report_type]
        
        if not await check_reports_exist(callback, filtered_reports, edit=True):
            return
            
        # Проверяем, имеет ли клиент доступ к этому объекту
        client = await get_client_by_user_id(session, user.id)
        if not client or object_id not in [obj.id for obj in client.objects]:
            await callback.message.edit_text(
                "У вас нет доступа к этому объекту.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Получаем информацию об объекте
        object_info, object_name = await get_object_info(session, object_id)
        
        # Определяем название типа отчета
        type_name = "Утренний" if report_type == "morning" else "Вечерний"
        
        # Загружаем все связанные данные для отчетов
        reports_with_relations = []
        for report in filtered_reports:
            report_with_relations = await get_report_with_relations(session, report.id)
            if report_with_relations:
                reports_with_relations.append(report_with_relations)
        
        if not reports_with_relations:
            await callback.message.edit_text(
                "Не удалось загрузить данные отчетов.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Создаем директорию для экспорта, если её нет
        export_dir = os.path.join(settings.BASE_DIR, settings.EXPORT_DIR)
        os.makedirs(export_dir, exist_ok=True)
        
        # Формируем имя файла
        filename = f"report_{object_id}_{date.strftime('%Y%m%d')}_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(export_dir, filename)
        
        # Экспортируем отчеты в PDF используя существующую функцию
        from construction_report_bot.utils.export_utils import export_report_to_pdf
        try:
            export_report_to_pdf(reports_with_relations, filepath)
        except Exception as e:
            logger.error(f"Ошибка при создании PDF: {str(e)}", exc_info=True)
            await callback.message.edit_text(
                "❌ Ошибка при создании PDF файла",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Отправляем файл отчета
        from aiogram.types import FSInputFile
        document = FSInputFile(filepath)
        try:
            date_str, _ = format_datetime(date)
            await callback.message.answer_document(
                document=document,
                caption=f"📄 {type_name} отчеты для объекта '{object_name}' за {date_str} успешно экспортированы в PDF"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке файла: {str(e)}", exc_info=True)
            await callback.message.edit_text(
                "❌ Ошибка при отправке файла",
                reply_markup=get_back_keyboard()
            )
        finally:
            # Удаляем временный файл
            try:
                os.remove(filepath)
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {str(e)}")
        
        # Возвращаемся к списку отчетов
        date_str, _ = format_datetime(date)
        await callback.message.edit_text(
            f"{type_name} отчеты для объекта '{object_name}' за {date_str}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад к выбору типа отчета", callback_data=f"client_date_object_reports_{date_str}_{object_id}")
            ]])
        )
        
    except Exception as e:
        await handle_error(callback, e)

def register_client_handlers(dp: Dispatcher) -> None:
    """
    Регистрирует все обработчики клиента.
    
    Args:
        dp: Объект диспетчера для регистрации обработчиков
    """
    dp.include_router(client_router) 