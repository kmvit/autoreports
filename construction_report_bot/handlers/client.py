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
from typing import Optional, List, Union
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import os

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from construction_report_bot.middlewares.role_check import client_required
from construction_report_bot.database.crud import (
    get_report_by_id, get_report_with_relations, get_reports_by_object, get_today_reports,
    get_client_by_user_id, get_reports_by_type, get_reports_by_date
)
from construction_report_bot.database.session import get_session
from construction_report_bot.config.keyboards import get_report_filter_keyboard, get_back_keyboard
from construction_report_bot.config.settings import settings
from construction_report_bot.utils.decorators import with_session, error_handler
from construction_report_bot.database.models import Report, Client

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
@with_session
async def cmd_today_report(message: Message, session: AsyncSession, state: FSMContext, **data):
    """Обработчик команды просмотра отчета за сегодня"""
    try:
        # Получаем клиента по ID пользователя
        user = data["user"]
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
        
        # Логирование для отладки
        logging.info(f"Получаем отчеты за сегодня для объекта ID: {object_id}")
        
        # Получаем отчеты за сегодня
        reports = await get_today_reports(session, object_id)
        
        if reports:
            # Отображаем список отчетов
            await display_reports_list(message, reports, f"📑 Отчет за сегодня ({datetime.now().strftime('%d.%m.%Y')}):", state)
        else:
            logging.info(f"Отчетов за сегодня для объекта {object_id} не найдено")
            await message.answer(
                f"За сегодня ({datetime.now().strftime('%d.%m.%Y')}) "
                f"отчетов по вашим объектам не найдено."
            )
    except Exception as e:
        # Логирование ошибки
        logging.error(f"Ошибка при получении отчетов: {str(e)}", exc_info=True)
        await message.answer(f"Произошла ошибка при получении отчетов: {str(e)}")

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
            # Отображаем список отчетов
            await display_reports_list(
                message, 
                filtered_reports, 
                f"📊 Отчеты за {date_str}:", 
                state
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
        logging.error(f"Ошибка при получении отчетов по дате: {str(e)}", exc_info=True)
        await message.answer(
            f"Произошла ошибка при получении отчетов: {str(e)}",
            reply_markup=get_back_keyboard()
        )
        await state.clear()

# Обработчик фильтрации по объекту
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
        
        # Формируем список объектов
        objects_text = "Выберите объект:\n\n"
        for i, obj in enumerate(client.objects, start=1):
            objects_text += f"{i}. {obj.name}\n"
        
        # Создаем клавиатуру с кнопками для каждого объекта
        builder = InlineKeyboardBuilder()
        for i, obj in enumerate(client.objects, start=1):
            builder.row(InlineKeyboardButton(
                text=f"{i}. {obj.name}",
                callback_data=f"select_object_{obj.id}"
            ))
        
        # Добавляем кнопку "Назад"
        builder.row(InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_filters"
        ))
        
        await callback.message.edit_text(
            objects_text,
            reply_markup=builder.as_markup()
        )
        await state.set_state(ReportFilterStates.waiting_for_object)
        
        # Сохраняем список объектов в состоянии
        await state.update_data(objects={i: obj.id for i, obj in enumerate(client.objects, start=1)})
    except Exception as e:
        await callback.message.edit_text(f"Произошла ошибка при получении списка объектов: {str(e)}")

# Обработчик выбора объекта через кнопку
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
        
        if reports:
            # Отображаем список отчетов
            await display_reports_list(callback, reports, "Отчеты по выбранному объекту:", state, edit=True)
        else:
            # Если отчетов нет, показываем сообщение с кнопкой "Назад"
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text="🔙 Назад к фильтрам",
                callback_data="back_to_filters"
            ))
            
            await callback.message.edit_text(
                "По выбранному объекту отчетов не найдено.",
                reply_markup=builder.as_markup()
            )
    except Exception as e:
        await callback.message.edit_text(f"Произошла ошибка при получении отчетов: {str(e)}")
    
    # Сбрасываем состояние
    await state.clear()

# Обработчик фильтрации по типу отчета
@client_router.callback_query(F.data == "filter_report_type")
async def process_filter_report_type(callback: CallbackQuery, state: FSMContext):
    """Обработка фильтрации отчетов по типу"""
    await callback.answer()
    
    # Создаем клавиатуру с кнопками для выбора типа отчета
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="1. Утренний",
        callback_data="select_report_type_morning"
    ))
    builder.row(InlineKeyboardButton(
        text="2. Вечерний",
        callback_data="select_report_type_evening"
    ))
    builder.row(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_filters"
    ))
    
    await callback.message.edit_text(
        "Выберите тип отчета:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(ReportFilterStates.waiting_for_report_type)

# Общие функции для работы с отчетами

async def filter_reports_by_client_objects(reports: List[Report], client: Client) -> List[Report]:
    """Фильтрация отчетов по объектам клиента"""
    client_object_ids = [obj.id for obj in client.objects]
    return [report for report in reports if report.object_id in client_object_ids]

async def display_reports_list(message: Union[Message, CallbackQuery], reports: List[Report], 
                             title: str, state: FSMContext, edit: bool = False):
    """Отображение списка отчетов в виде кнопок"""
    if not reports:
        # Если отчетов нет, показываем сообщение с кнопкой "Назад"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="🔙 Назад к фильтрам",
            callback_data="back_to_filters"
        ))
        
        if edit and isinstance(message, CallbackQuery):
            await message.message.edit_text(
                f"Отчетов не найдено.",
                reply_markup=builder.as_markup()
            )
        else:
            await message.answer(
                f"Отчетов не найдено.",
                reply_markup=builder.as_markup()
            )
        return
    
    # Формируем текст с информацией о выбранных отчетах
    reports_text = f"{title}\n\n"
    reports_text += "Выберите отчет для просмотра:"
    
    # Создаем клавиатуру с кнопками для каждого отчета
    builder = InlineKeyboardBuilder()
    
    for i, report in enumerate(reports, start=1):
        # Формируем текст кнопки с основной информацией об отчете
        button_text = f"{i}. {report.date.strftime('%d.%m.%Y')} - {report.object.name}"
        builder.row(InlineKeyboardButton(
            text=button_text,
            callback_data=f"view_report_{report.id}"
        ))
    
    # Добавляем кнопку "Назад к фильтрам"
    builder.row(InlineKeyboardButton(
        text="🔙 Назад к фильтрам",
        callback_data="back_to_filters"
    ))
    
    if edit and isinstance(message, CallbackQuery):
        await message.message.edit_text(
            reports_text,
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            reports_text,
            reply_markup=builder.as_markup()
        )
    
    # Сохраняем список отчетов в состоянии для последующего использования
    await state.update_data(reports={i: report.id for i, report in enumerate(reports, start=1)})

async def display_report_details(message: Union[Message, CallbackQuery], report: Report, edit: bool = False):
    """Отображение детальной информации об отчете"""
    # Формируем текст с информацией об отчете
    report_text = f"📊 Отчет #{report.id}\n\n"
    report_text += f"Дата: {report.date.strftime('%d.%m.%Y')}\n"
    report_text += f"Тип: {'Утренний' if report.type == 'morning' else 'Вечерний'}\n"
    report_text += f"Объект: {report.object.name}\n"
    report_text += f"Тип работ: {report.report_type}\n"
    
    if report.work_subtype:
        report_text += f"Подтип работ: {report.work_subtype}\n"
    
    report_text += f"Статус: {'Отправлен' if report.status == 'sent' else 'Черновик'}\n\n"
    
    # Добавляем информацию о персонале
    if report.itr_personnel:
        report_text += "ИТР персонал:\n"
        for itr in report.itr_personnel:
            report_text += f"- {itr.full_name}\n"
        report_text += "\n"
    
    if report.workers:
        report_text += "Рабочие:\n"
        for worker in report.workers:
            report_text += f"- {worker.full_name}\n"
        report_text += "\n"
    
    # Добавляем информацию об оборудовании
    if report.equipment:
        report_text += "Оборудование:\n"
        for equip in report.equipment:
            report_text += f"- {equip.name}\n"
        report_text += "\n"
    
    # Добавляем комментарии
    if report.comments:
        report_text += f"Комментарии: {report.comments}\n\n"
    
    # Создаем клавиатуру с кнопками
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📄 Скачать PDF",
        callback_data=f"client_export_pdf_{report.id}"
    ))
    builder.row(InlineKeyboardButton(
        text="🔙 Назад к списку отчетов",
        callback_data="back_to_reports_list"
    ))
    
    if edit and isinstance(message, CallbackQuery):
        await message.message.edit_text(
            report_text,
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            report_text,
            reply_markup=builder.as_markup()
        )

# Обработчик выбора типа отчета через кнопку
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
        
        # Отображаем список отчетов
        await display_reports_list(callback, filtered_reports, f"Отчеты типа {type_name}:", state, edit=True)
        
    except Exception as e:
        logging.error(f"Ошибка при получении отчетов по типу: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            f"Произошла ошибка при получении отчетов: {str(e)}",
            reply_markup=get_back_keyboard()
        )
    
    # Сбрасываем состояние
    await state.clear()

# Обработчик ввода типа отчета (оставляем для обратной совместимости)
@client_router.message(ReportFilterStates.waiting_for_report_type)
@with_session
async def process_report_type_input(message: Message, state: FSMContext, session: AsyncSession, **data):
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
    
    try:
        # Получаем клиента
        user = data["user"]
        client = await get_client_by_user_id(session, user.id)
        
        if not client:
            await message.answer("Ваш профиль не найден. Обратитесь к администратору.")
            return
        
        # Получаем отчеты по типу
        reports = await get_reports_by_type(session, report_type)
        
        # Фильтруем отчеты по объектам клиента
        filtered_reports = await filter_reports_by_client_objects(reports, client)
        
        # Отображаем список отчетов
        await display_reports_list(message, filtered_reports, f"Отчеты типа {type_name}:", state)
        
    except Exception as e:
        logging.error(f"Ошибка при получении отчетов по типу: {str(e)}", exc_info=True)
        await message.answer(f"Произошла ошибка при получении отчетов: {str(e)}")
    
    # Сбрасываем состояние
    await state.clear()

# Обработчик просмотра отчета
@client_router.callback_query(F.data.startswith("view_report_"))
@with_session
async def process_view_report(callback: CallbackQuery, session: AsyncSession):
    """Обработка просмотра отчета"""
    await callback.answer()
    
    try:
        # Извлекаем ID отчета из callback_data
        report_id = int(callback.data.split("_")[2])
        
        # Получаем отчет с отношениями
        report = await get_report_with_relations(session, report_id)
        
        if report:
            # Отображаем детальную информацию об отчете
            await display_report_details(callback, report, edit=True)
        else:
            await callback.message.edit_text(
                "Отчет не найден.",
                reply_markup=get_back_keyboard()
            )
    except Exception as e:
        logging.error(f"Ошибка при просмотре отчета: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            f"Произошла ошибка при просмотре отчета: {str(e)}",
            reply_markup=get_back_keyboard()
        )

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

@client_router.callback_query(F.data.startswith("client_export_pdf_"))
@error_handler
@with_session
async def process_client_export_pdf(callback: CallbackQuery, session: AsyncSession, user: User):
    """Обработка экспорта отчета в PDF для клиентов"""
    await callback.answer()
    
    try:
        # Извлекаем ID отчета из callback_data
        report_id = int(callback.data.split("_")[3])  # Изменен индекс из-за нового префикса
        logging.info(f"[process_client_export_pdf] Начало экспорта отчета #{report_id}")
        
        # Получаем отчет из БД
        report = await get_report_with_relations(session, report_id)
        if not report:
            logging.warning(f"[process_client_export_pdf] Отчет #{report_id} не найден в базе данных")
            await callback.message.edit_text(
                "Отчет не найден.",
                reply_markup=get_back_keyboard()
            )
            return
            
        # Проверяем, имеет ли клиент доступ к этому отчету
        client = await get_client_by_user_id(session, user.id)
        if not client or report.object_id not in [obj.id for obj in client.objects]:
            logging.warning(f"[process_client_export_pdf] Клиент {user.id} не имеет доступа к отчету #{report_id}")
            await callback.message.edit_text(
                "У вас нет доступа к этому отчету.",
                reply_markup=get_back_keyboard()
            )
            return
        
        logging.info(f"[process_client_export_pdf] Отчет #{report_id} успешно получен из БД")
        
        # Создаем директорию для экспорта, если её нет
        export_dir = os.path.join(settings.BASE_DIR, settings.EXPORT_DIR)
        os.makedirs(export_dir, exist_ok=True)
        logging.info(f"[process_client_export_pdf] Директория для экспорта: {export_dir}")
        
        # Формируем имя файла
        filename = f"report_{report_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(export_dir, filename)
        logging.info(f"[process_client_export_pdf] Путь для сохранения PDF: {filepath}")
        
        # Экспортируем отчет в PDF
        from construction_report_bot.utils.export_utils import export_report_to_pdf
        logging.info("[process_client_export_pdf] Начало экспорта в PDF")
        try:
            export_report_to_pdf([report], filepath)
            logging.info("[process_client_export_pdf] PDF успешно создан")
        except Exception as e:
            logging.error(f"[process_client_export_pdf] Ошибка при создании PDF: {str(e)}", exc_info=True)
            await callback.message.edit_text(
                "❌ Ошибка при создании PDF файла",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Отправляем файл отчета
        from aiogram.types import FSInputFile
        document = FSInputFile(filepath)
        logging.info("[process_client_export_pdf] Отправка файла пользователю")
        try:
            await callback.message.answer_document(
                document=document,
                caption=f"📄 Отчет #{report_id} успешно экспортирован в PDF"
            )
            logging.info("[process_client_export_pdf] Файл успешно отправлен")
        except Exception as e:
            logging.error(f"[process_client_export_pdf] Ошибка при отправке файла: {str(e)}", exc_info=True)
            await callback.message.edit_text(
                "❌ Ошибка при отправке файла",
                reply_markup=get_back_keyboard()
            )
        finally:
            # Удаляем временный файл
            try:
                os.remove(filepath)
                logging.info("[process_client_export_pdf] Временный файл удален")
            except Exception as e:
                logging.error(f"[process_client_export_pdf] Ошибка при удалении временного файла: {str(e)}")
        
        # Возвращаемся к списку отчетов
        await callback.message.edit_text(
            "Отчеты по выбранному объекту:",
            reply_markup=get_back_keyboard()
        )
        logging.info("[process_client_export_pdf] Экспорт успешно завершен")
        
    except Exception as e:
        logging.error(f"[process_client_export_pdf] Ошибка при экспорте отчета в PDF: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при экспорте отчета в PDF",
            reply_markup=get_back_keyboard()
        )

def register_client_handlers(dp: Dispatcher) -> None:
    """
    Регистрирует все обработчики клиента.
    
    Args:
        dp: Объект диспетчера для регистрации обработчиков
    """
    dp.include_router(client_router) 