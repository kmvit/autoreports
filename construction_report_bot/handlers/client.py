"""Модуль обработчиков для клиентского интерфейса бота.
Содержит обработчики для просмотра отчетов, их фильтрации и взаимодействия
с системой отчетности для клиентов строительной компании.
"""

from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import Optional, List
from datetime import datetime

from construction_report_bot.middlewares.role_check import client_required
from construction_report_bot.database.crud import (
    get_report_by_id, get_reports_by_object, get_today_reports,
    get_client_by_user_id
)
from construction_report_bot.database.session import get_session
from construction_report_bot.config.keyboards import get_report_filter_keyboard, get_back_keyboard
from construction_report_bot.config.settings import settings

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
async def cmd_report_history(message: Message):
    """Обработчик команды просмотра истории отчетов"""
    await message.answer(
        "История отчетов. Выберите фильтр:",
        reply_markup=get_report_filter_keyboard()
    )

# Обработчик просмотра отчета за сегодня
@client_router.message(F.text == "📑 Отчет за сегодня")
async def cmd_today_report(message: Message):
    """Обработчик команды просмотра отчета за сегодня"""
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем клиента по ID пользователя
        user = message.bot.get("user")
        client = await get_client_by_user_id(session, user.id)
        
        if not client:
            await message.answer("Ваш профиль не найден. Обратитесь к администратору.")
            return
        
        # Получаем доступные объекты клиента
        objects = client.objects
        
        if not objects:
            await message.answer("У вас нет доступных объектов. Обратитесь к администратору.")
            return
        
        # Для упрощения берем первый объект (можно добавить выбор объекта)
        object_id = objects[0].id
        
        # Получаем отчеты за сегодня
        reports = await get_today_reports(session, object_id)
        
        if reports:
            # Формируем сообщение с отчетами
            report_text = f"📑 Отчет за сегодня ({datetime.now().strftime('%d.%m.%Y')}):\n\n"
            
            for report in reports:
                report_text += f"Тип: {'Утренний' if report.type == 'morning' else 'Вечерний'}\n"
                report_text += f"Объект: {report.object.name}\n"
                report_text += f"Тип работ: {report.report_type}\n"
                
                if report.work_subtype:
                    report_text += f"Подтип работ: {report.work_subtype}\n"
                
                report_text += f"Статус: {'Отправлен' if report.status == 'sent' else 'Черновик'}\n"
                
                if report.comments:
                    report_text += f"Комментарии: {report.comments}\n"
                
                report_text += "\n"
            
            await message.answer(report_text)
        else:
            await message.answer(
                f"За сегодня ({datetime.now().strftime('%d.%m.%Y')}) "
                f"отчетов по вашим объектам не найдено."
            )
    finally:
        await session.close()

# Обработчик фильтрации по дате
@client_router.callback_query(F.data == "filter_date")
async def process_filter_date(callback: CallbackQuery, state: FSMContext):
    """Обработка фильтрации отчетов по дате"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Введите дату в формате ДД.ММ.ГГГГ:"
    )
    
    await state.set_state(ReportFilterStates.waiting_for_date)

# Обработчик ввода даты
@client_router.message(ReportFilterStates.waiting_for_date)
async def process_date_input(message: Message, state: FSMContext):
    """Обработка ввода даты для фильтрации"""
    date_str = message.text.strip()
    
    try:
        # Парсим дату
        filter_date = datetime.strptime(date_str, '%d.%m.%Y')
        
        # Сохраняем в состоянии
        await state.update_data(filter_date=filter_date)
        
        # TODO: Получение отчетов по дате
        await message.answer(
            f"Отчеты за {date_str}:\n\n"
            f"Функционал находится в разработке."
        )
        
        # Сбрасываем состояние
        await state.clear()
    except ValueError:
        await message.answer(
            "Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ."
        )

# Обработчик фильтрации по объекту
@client_router.callback_query(F.data == "filter_object")
async def process_filter_object(callback: CallbackQuery, state: FSMContext):
    """Обработка фильтрации отчетов по объекту"""
    await callback.answer()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем клиента
        user = callback.bot.get("user")
        client = await get_client_by_user_id(session, user.id)
        
        if not client or not client.objects:
            await callback.message.edit_text(
                "У вас нет доступных объектов. Обратитесь к администратору.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Формируем список объектов
        objects_text = "Выберите объект:\n\n"
        for i, obj in enumerate(client.objects, start=1):
            objects_text += f"{i}. {obj.name}\n"
        
        await callback.message.edit_text(objects_text)
        await state.set_state(ReportFilterStates.waiting_for_object)
        
        # Сохраняем список объектов в состоянии
        await state.update_data(objects={i: obj.id for i, obj in enumerate(client.objects, start=1)})
    finally:
        await session.close()

# Обработчик ввода номера объекта
@client_router.message(ReportFilterStates.waiting_for_object)
async def process_object_input(message: Message, state: FSMContext):
    """Обработка ввода номера объекта для фильтрации"""
    try:
        object_num = int(message.text.strip())
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        objects = state_data.get("objects", {})
        
        if object_num in objects:
            object_id = objects[object_num]
            
            # Получаем сессию БД
            session_gen = get_session()
            session = await session_gen.__anext__()
            
            try:
                # Получаем отчеты по объекту
                reports = await get_reports_by_object(session, object_id)
                
                if reports:
                    # Формируем текст с отчетами
                    reports_text = f"Отчеты по выбранному объекту:\n\n"
                    
                    for report in reports:
                        reports_text += f"Дата: {report.date.strftime('%d.%m.%Y')}\n"
                        reports_text += f"Тип: {'Утренний' if report.type == 'morning' else 'Вечерний'}\n"
                        reports_text += f"Тип работ: {report.report_type}\n"
                        
                        if report.work_subtype:
                            reports_text += f"Подтип работ: {report.work_subtype}\n"
                        
                        reports_text += f"Статус: {'Отправлен' if report.status == 'sent' else 'Черновик'}\n\n"
                    
                    await message.answer(reports_text)
                else:
                    await message.answer("По выбранному объекту отчетов не найдено.")
            finally:
                await session.close()
        else:
            await message.answer("Неверный номер объекта. Пожалуйста, выберите из списка.")
    except ValueError:
        await message.answer("Введите корректный номер объекта.")
    
    # Сбрасываем состояние
    await state.clear()

# Обработчик фильтрации по типу отчета
@client_router.callback_query(F.data == "filter_report_type")
async def process_filter_report_type(callback: CallbackQuery, state: FSMContext):
    """Обработка фильтрации отчетов по типу"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Выберите тип отчета:\n\n"
        "1. Утренний\n"
        "2. Вечерний"
    )
    
    await state.set_state(ReportFilterStates.waiting_for_report_type)

# Обработчик ввода типа отчета
@client_router.message(ReportFilterStates.waiting_for_report_type)
async def process_report_type_input(message: Message, state: FSMContext):
    """Обработка ввода типа отчета для фильтрации"""
    report_type = message.text.strip()
    
    if report_type == "1":
        report_type = "morning"
        type_name = "Утренний"
    elif report_type == "2":
        report_type = "evening"
        type_name = "Вечерний"
    else:
        await message.answer("Введите 1 (Утренний) или 2 (Вечерний).")
        return
    
    # TODO: Получение отчетов по типу
    await message.answer(
        f"Отчеты типа {type_name}:\n\n"
        f"Функционал находится в разработке."
    )
    
    # Сбрасываем состояние
    await state.clear()

# Обработчик сброса фильтров
@client_router.callback_query(F.data == "filter_reset")
async def process_filter_reset(callback: CallbackQuery):
    """Обработка сброса фильтров"""
    await callback.answer("Фильтры сброшены")
    
    await callback.message.edit_text(
        "Фильтры сброшены. Выберите новый фильтр:",
        reply_markup=get_report_filter_keyboard()
    )

def register_client_handlers(dp: Dispatcher) -> None:
    """
    Регистрирует все обработчики клиента.
    
    Args:
        dp: Объект диспетчера для регистрации обработчиков
    """
    dp.include_router(client_router) 