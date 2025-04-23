import logging
from aiogram import Router, F, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
import os
import uuid
from datetime import datetime
from typing import Optional
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from aiogram.types import BufferedInputFile

from construction_report_bot.database.crud import (
    get_user_by_telegram_id,
    get_object_by_id,
    get_all_objects,
    create_report,
    get_all_itr,
    get_all_workers,
    get_all_equipment,
    get_all_reports,
    create_base_report,
    get_itr_by_id,
    get_worker_by_id,
    get_equipment_by_id,
    get_report_by_id,
    get_report_with_relations,
    get_reports_by_status,
    get_all_clients,
    get_user_by_id,
    get_reports_for_export
)
from construction_report_bot.database.session import get_session, async_session
from construction_report_bot.database.models import (
    Report, Client, Object, ReportPhoto, ITR, Worker, Equipment,
    report_itr, report_workers, report_equipment, User
)
from construction_report_bot.config.settings import settings
from construction_report_bot.states.report_states import ReportStates
from construction_report_bot.services.report_service import ReportService
from construction_report_bot.config.keyboards import (
    get_admin_report_menu_keyboard,
    get_main_menu_keyboard,
    get_objects_keyboard,
    get_report_type_keyboard,
    get_work_subtype_keyboard,
    get_report_actions_keyboard,
    get_itr_keyboard,
    get_workers_keyboard,
    get_equipment_keyboard,
    get_photos_keyboard,
    get_comments_keyboard,
    get_back_keyboard,
    get_report_filter_keyboard,
    get_work_type_keyboard
)
from construction_report_bot.utils.exceptions import ValidationError, DatabaseError
from construction_report_bot.utils.logging.logger import log_admin_action, log_error
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.middlewares.role_check import AdminMiddleware, admin_required
from construction_report_bot.utils.report_utils import (
    validate_date_range,
    get_reports_by_date_range,
    generate_report_summary,
    format_report_message
)
from construction_report_bot.utils.export_utils import export_report_to_pdf, export_report_to_excel

logger = logging.getLogger(__name__)

# Создаем роутер для администратора
admin_report_router = Router()
# Добавляем middleware для проверки роли
admin_report_router.message.middleware(admin_required())
admin_report_router.callback_query.middleware(admin_required())

class ReportManagementStates(StatesGroup):
    """Состояния для управления отчетами"""
    waiting_for_type = State()
    waiting_for_filter = State()
    waiting_for_date_range = State()


async def validate_report_data(data: dict) -> None:
    """Валидация данных отчета"""
    logging.info(f"Начало валидации данных отчета. Полученные данные: {data}")
    
    required_fields = ['object_id', 'report_type', 'itr_list', 'workers_list', 'equipment_list']
    
    # Проверяем наличие всех полей
    for field in required_fields:
        if field not in data:
            error_msg = f"Отсутствует обязательное поле: {field}"
            logging.error(error_msg)
            raise ValidationError(error_msg)
        logging.info(f"Поле {field} найдено. Значение: {data[field]}")
    
    # Проверяем корректность значений
    if data['report_type'] not in ['engineering', 'internal_networks', 'landscaping', 'general_construction']:
        error_msg = "Некорректный тип отчета"
        logging.error(error_msg)
        raise ValidationError(error_msg)
    
    if data['type'] not in ['morning', 'evening']:
        error_msg = "Некорректное время суток"
        logging.error(error_msg)
        raise ValidationError(error_msg)
    
    logging.info("Валидация данных отчета успешно завершена")

# Обработчик для меню администратора
@admin_report_router.message(F.text == "📝 Управление отчетами")
async def show_admin_report_menu(message: Message):
    """Показать меню администратора для отчетов"""
    print("[show_admin_report_menu] Showing admin report menu")
    keyboard = await get_admin_report_menu_keyboard()
    print(f"[show_admin_report_menu] Created keyboard: {keyboard}")
    await message.answer(
        "Меню администратора для отчетов:",
        reply_markup=keyboard
    )

@admin_report_router.callback_query(F.data == "my_reports")
async def process_my_reports(callback: CallbackQuery):
    """Обработка просмотра своих отчетов"""
    try:
        # Получаем сессию БД
        async for session in get_session():
            # Получаем отчеты пользователя
            reports = await get_all_reports(session, callback.from_user.id)
            
            if reports:
                # Формируем клавиатуру с отчетами
                keyboard = []
                for report in reports:
                    # Добавляем эмодзи в зависимости от статуса
                    status_emoji = "✅" if report.status == "completed" else "📝"
                    button_text = f"{status_emoji} {report.type} от {report.date.strftime('%d.%m.%Y %H:%M')}"
                    callback_data = f"edit_report_{report.id}"
                    logging.info(f"Создана кнопка редактирования: {button_text} с callback_data: {callback_data}")
                    keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
                
                # Добавляем кнопку "Назад"
                keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")])
                
                await callback.message.edit_text(
                    "Выберите отчет для редактирования:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
                )
            else:
                await callback.message.edit_text(
                    "У вас пока нет отчетов.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")]
                    ])
                )
    except Exception as e:
        logging.error(f"Ошибка при получении отчетов: {str(e)}")
        await callback.message.edit_text(
            f"Произошла ошибка при получении отчетов: {str(e)}",
            reply_markup=await get_admin_report_menu_keyboard()
        )

@admin_report_router.callback_query(F.data.startswith("edit_report_"))
async def process_edit_report(callback: CallbackQuery, state: FSMContext):
    """Обработка редактирования отчета"""
    try:
        # Получаем ID отчета из callback_data
        report_id = int(callback.data.split("_")[2])
        logging.info(f"Попытка редактирования отчета #{report_id}")
        logging.info(f"Callback data: {callback.data}")
        
        # Получаем сессию БД
        async for session in get_session():
            try:
                # Получаем отчет из БД
                report = await get_report_by_id(session, report_id)
                if not report:
                    logging.warning(f"[process_edit_report] Отчет #{report_id} не найден в базе данных")
                    await callback.message.edit_text(
                        "Отчет не найден.",
                        reply_markup=await get_admin_report_menu_keyboard()
                    )
                    return
                
                # Получаем объект отдельным запросом
                object_query = select(Object).where(Object.id == report.object_id)
                result = await session.execute(object_query)
                object = result.scalar_one_or_none()
                
                # Сохраняем базовые данные в состоянии
                state_data = {
                    'report_id': report_id,
                    'object_id': report.object_id,
                    'report_type': report.report_type,
                    'type': report.type,
                    'work_type': report.report_type,
                    'work_subtype': report.work_subtype,
                    'comments': report.comments
                }
                
                # Получаем связанные данные через отдельные запросы
                # Получаем фотографии
                photos_query = select(ReportPhoto).where(ReportPhoto.report_id == report_id)
                result = await session.execute(photos_query)
                photos = result.scalars().all()
                
                # Получаем ИТР
                itr_query = (
                    select(ITR)
                    .join(report_itr, ITR.id == report_itr.c.itr_id)
                    .where(report_itr.c.report_id == report_id)
                )
                result = await session.execute(itr_query)
                itr_personnel = result.scalars().all()
                state_data['itr_list'] = [itr.id for itr in itr_personnel]
                
                # Получаем рабочих
                workers_query = (
                    select(Worker)
                    .join(report_workers, Worker.id == report_workers.c.worker_id)
                    .where(report_workers.c.report_id == report_id)
                )
                result = await session.execute(workers_query)
                workers = result.scalars().all()
                state_data['workers_list'] = [worker.id for worker in workers]
                
                # Получаем технику
                equipment_query = (
                    select(Equipment)
                    .join(report_equipment, Equipment.id == report_equipment.c.equipment_id)
                    .where(report_equipment.c.report_id == report_id)
                )
                result = await session.execute(equipment_query)
                equipment = result.scalars().all()
                state_data['equipment_list'] = [eq.id for eq in equipment]
                
                # Сохраняем все данные в состоянии
                await state.update_data(**state_data)
                logging.info(f"[process_edit_report] Сохранены данные в состоянии: {state_data}")
                
                # Формируем информацию об отчете
                report_info = (
                    f"📝 Редактирование отчета #{report.id}\n\n"
                    f"Тип: {report.type}\n"
                    f"Дата: {report.date.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Статус: {report.status}\n"
                    f"Объект: {object.name if object else 'Не указан'}\n"
                )
                
                # Добавляем тип работ, если есть
                if report.report_type:
                    report_info += f"Тип работ: {report.report_type}\n"
                
                # Добавляем подтип работ, если есть
                if report.work_subtype:
                    report_info += f"Подтип работ: {report.work_subtype}\n"
                
                # Добавляем ИТР, если есть
                if itr_personnel:
                    itr_names = [itr.full_name for itr in itr_personnel]
                    if itr_names:
                        report_info += f"ИТР: {', '.join(itr_names)}\n"
                
                # Добавляем рабочих, если есть
                if workers:
                    worker_names = [worker.full_name for worker in workers]
                    if worker_names:
                        report_info += f"Рабочие: {', '.join(worker_names)}\n"
                
                # Добавляем технику, если есть
                if equipment:
                    equipment_names = [eq.name for eq in equipment]
                    if equipment_names:
                        report_info += f"Техника: {', '.join(equipment_names)}\n"
                
                # Добавляем комментарии, если есть
                if report.comments:
                    report_info += f"Комментарий: {report.comments}\n"

                # Добавляем фотографии, если есть
                if photos:
                    photo_count = len(photos)
                    report_info += f"Фотографий: {photo_count}\n"
                # Показываем меню действий для редактирования
                await callback.message.edit_text(
                    report_info + "\nВыберите действие:",
                    reply_markup=await get_report_actions_keyboard()
                )
                
                # Устанавливаем состояние редактирования
                await state.set_state(ReportStates.edit_report)
                
            except Exception as e:
                logging.error(f"Ошибка при редактировании отчета: {str(e)}", exc_info=True)
                await callback.message.edit_text(
                    "❌ Произошла ошибка при редактировании отчета",
                    reply_markup=await get_admin_report_menu_keyboard()
                )
    except Exception as e:
        logging.error(f"Ошибка в process_edit_report: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при обработке запроса",
            reply_markup=await get_admin_report_menu_keyboard()
        )

@admin_report_router.message(Command("reports"))
@error_handler
async def cmd_reports(message: Message, state: FSMContext):
    """Обработчик команды /reports"""
    await state.set_state(ReportManagementStates.waiting_for_type)
    await message.answer(
        "Выберите тип отчета:",
        reply_markup=get_report_type_keyboard()
    )

# Обработчик для начала создания отчета
@admin_report_router.callback_query(F.data == "create_report")
async def create_report_start(callback: CallbackQuery, state: FSMContext):
    """Начать создание отчета"""
    try:
        await callback.answer()
        session = await get_session().__anext__()
        
        # Добавляем логирование
        log_admin_action("report_creation_attempt", callback.from_user.id, "Попытка создания отчета")
        
            
        # Получаем список объектов
        objects = await get_all_objects(session)
        if not objects:
            log_admin_action("report_creation_failed", callback.from_user.id, "Нет доступных объектов")
            await callback.message.edit_text(
                "Нет доступных объектов для создания отчета.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
            
        log_admin_action("report_creation_started", callback.from_user.id)
        keyboard = await get_objects_keyboard(session)
        await callback.message.edit_text(
            "Выберите объект для отчета:",
            reply_markup=keyboard
        )
        
        # Устанавливаем состояние
        await state.set_state(ReportStates.select_object)
    except Exception as e:
        log_error(e, callback.from_user.id, "Ошибка при начале создания отчета")
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")
    finally:
        await session.close()

# Обработчик выбора объекта
@admin_report_router.callback_query(F.data.startswith("object_"), ReportStates.select_object)
async def process_object_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора объекта"""
    try:
        await callback.answer()
        session = await get_session().__anext__()
        
        # Извлекаем ID объекта из callback_data
        object_id = int(callback.data.split("_")[1])
        logging.info(f"[process_object_selection] Получен object_id из callback_data: {object_id}")
        
        # Сохраняем выбранный объект в данных состояния
        await state.update_data(object_id=object_id)
        
        # Проверяем сохранение в состоянии
        state_data = await state.get_data()
        logging.info(f"[process_object_selection] Данные состояния после сохранения: {state_data}")
        
        # Показываем типы работ
        keyboard = get_work_type_keyboard()
        await callback.message.edit_text(
            "Выберите тип работ:",
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.select_work_type)
    except ValueError as e:
        logging.error(f"[process_object_selection] Ошибка при обработке ID объекта: {e}")
        await callback.message.edit_text("Некорректный ID объекта.")
    except Exception as e:
        logging.error(f"[process_object_selection] Общая ошибка: {e}")
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")
    finally:
        await session.close()

# Обработчик выбора типа работ
@admin_report_router.callback_query(F.data.startswith("work_"), ReportStates.select_work_type)
async def process_work_type_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа работ"""
    await callback.answer()
    
    # Сохраняем выбранный тип работ
    work_type = callback.data.replace("work_", "")
    await state.update_data(work_type=work_type)
    
    # Если выбрали "Благоустройство", то подтипа нет, пропускаем этот шаг
    if work_type == "landscaping":
        await state.update_data(work_subtype=None)
        
        # Показываем типы отчетов
        keyboard = get_report_type_keyboard()
        await callback.message.edit_text(
            "Выберите тип отчета:",
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.select_report_type)
    else:
        # В других случаях показываем подтипы работ
        keyboard = await get_work_subtype_keyboard(f"report_{work_type}")
        await callback.message.edit_text("Выберите подтип работ:", reply_markup=keyboard)
        
        # Обновляем состояние
        await state.set_state(ReportStates.select_work_subtype)

# Обработчик выбора подтипа работ
@admin_report_router.callback_query(F.data.startswith("subtype_"), ReportStates.select_work_subtype)
async def process_work_subtype_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора подтипа работ"""
    await callback.answer()
    
    # Сохраняем выбранный подтип работ
    work_subtype = callback.data.replace("subtype_", "")
    await state.update_data(work_subtype=work_subtype)
    
    # Показываем типы отчетов
    keyboard = get_report_type_keyboard()
    await callback.message.edit_text(
        "Выберите тип отчета:",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.select_report_type)

# Обработчик добавления ИТР
@admin_report_router.callback_query(F.data == "add_itr")
async def process_add_itr(callback: CallbackQuery, state: FSMContext):
    """Обработка добавления ИТР"""
    await callback.answer()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем список ИТР
        itr_list = await get_all_itr(session)
        
        if not itr_list:
            await callback.message.edit_text(
                "Список ИТР пуст. Добавьте ИТР в систему.",
                reply_markup=await get_report_actions_keyboard()
            )
            return
        
        # Формируем клавиатуру с ИТР
        keyboard = await get_itr_keyboard(itr_list, selected_ids=[])
        await callback.message.edit_text(
            "Выберите ИТР для отчета:",
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.add_itr)
    except Exception as e:
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")
    finally:
        await session.close()

# Обработчик выбора ИТР
@admin_report_router.callback_query(F.data.startswith("itr_"), ReportStates.add_itr)
async def process_itr_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора ИТР"""
    try:
        # Извлекаем ID ИТР из callback_data
        itr_id = int(callback.data.split("_")[1])
        
        # Получаем данные из состояния
        data = await state.get_data()
        report_id = data.get('report_id')
        
        if not report_id:
            await callback.answer("❌ Ошибка: не найден ID отчета", show_alert=True)
            return
        
        # Получаем сессию БД
        async with async_session() as session:
            # Получаем информацию об ИТР
            itr = await get_itr_by_id(session, itr_id)
            
            if not itr:
                await callback.answer("ИТР не найден")
                return
            
            # Добавляем ИТР в отчет
            report = await ReportService.add_itr_to_report(session, report_id, [itr_id])
            
            if not report:
                await callback.answer("❌ Ошибка при добавлении ИТР в отчет", show_alert=True)
                return
            
            # Отправляем ответ на callback
            await callback.answer(f"✅ Выбран ИТР: {itr.full_name}")
            
            # Отправляем новое сообщение с меню действий
            await callback.message.edit_text(
                f"✅ ИТР {itr.full_name} успешно добавлен в отчет.\n\n"
                f"Выберите действие для продолжения создания отчета:",
                reply_markup=await get_report_actions_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка при выборе ИТР: {str(e)}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при выборе ИТР", show_alert=True)

# Обработчик добавления рабочих
@admin_report_router.callback_query(F.data == "add_workers")
async def process_add_workers(callback: CallbackQuery, state: FSMContext):
    """Обработка добавления рабочих"""
    await callback.answer()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        report_id = data.get('report_id')
        
        if not report_id:
            await callback.message.edit_text(
                "❌ Не найден ID отчета.\n"
                "Пожалуйста, начните создание отчета заново.",
                reply_markup=await get_main_menu_keyboard()
            )
            return
        
        # Получаем отчет с текущими рабочими
        report = await get_report_with_relations(session, report_id)
        if not report:
            await callback.message.edit_text(
                "❌ Отчет не найден.\n"
                "Пожалуйста, начните создание отчета заново.",
                reply_markup=await get_main_menu_keyboard()
            )
            return
        
        # Получаем список всех рабочих
        all_workers = await get_all_workers(session)
        
        if not all_workers:
            await callback.message.edit_text(
                "Список рабочих пуст. Добавьте рабочих в систему.",
                reply_markup=await get_report_actions_keyboard()
            )
            return
        
        # Получаем список ID рабочих, которые уже добавлены в отчет
        existing_worker_ids = [worker.id for worker in report.workers] if report.workers else []
        
        # Фильтруем список рабочих, исключая тех, кто уже добавлен в отчет
        available_workers = [worker for worker in all_workers if worker.id not in existing_worker_ids]
        
        if not available_workers:
            await callback.message.edit_text(
                "❌ Все доступные рабочие уже добавлены в отчет.\n"
                "Выберите другое действие:",
                reply_markup=await get_report_actions_keyboard()
            )
            return
        
        # Формируем клавиатуру только с доступными рабочими
        keyboard = await get_workers_keyboard(available_workers)
        
        # Добавляем информацию о том, сколько рабочих уже в отчете
        existing_count = len(existing_worker_ids)
        message_text = f"Выберите рабочих для отчета:\n\n"
        if existing_count > 0:
            message_text += f"ℹ️ В отчете уже добавлено рабочих: {existing_count}\n\n"
        
        await callback.message.edit_text(
            message_text,
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.add_workers)
    except Exception as e:
        logger.error(f"Ошибка при добавлении рабочих: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при добавлении рабочих.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=await get_report_actions_keyboard()
        )
    finally:
        await session.close()

# Обработчик выбора рабочих
@admin_report_router.callback_query(F.data.startswith("worker_"), ReportStates.add_workers)
async def process_worker_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора рабочих"""
    # Извлекаем ID рабочего из callback_data
    worker_id = int(callback.data.split("_")[1])
    
    # Получаем текущие данные состояния
    data = await state.get_data()
    workers_list = data.get('workers_list', [])
    report_id = data.get('report_id')
    
    if not report_id:
        await callback.answer("❌ Ошибка: не найден ID отчета", show_alert=True)
        return
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем отчет с текущими рабочими
        report = await get_report_with_relations(session, report_id)
        if not report:
            await callback.answer("❌ Ошибка: отчет не найден", show_alert=True)
            return
        
        # Получаем список ID рабочих, которые уже добавлены в отчет
        existing_worker_ids = [worker.id for worker in report.workers] if report.workers else []
        
        # Проверяем, не добавлен ли уже этот рабочий в отчет
        if worker_id in existing_worker_ids:
            await callback.answer("❌ Этот рабочий уже добавлен в отчет", show_alert=True)
            return
        
        # Проверяем, есть ли изменения в текущем выборе
        was_selected = worker_id in workers_list
        
        # Добавляем или удаляем рабочего из списка
        if was_selected:
            workers_list.remove(worker_id)
        else:
            workers_list.append(worker_id)
        
        # Обновляем данные состояния
        await state.update_data(workers_list=workers_list)
        
        # Получаем обновленный список рабочих
        all_workers = await get_all_workers(session)
        
        # Фильтруем список рабочих, исключая тех, кто уже добавлен в отчет
        available_workers = [worker for worker in all_workers if worker.id not in existing_worker_ids]
        
        # Формируем клавиатуру с отмеченными рабочими
        keyboard = await get_workers_keyboard(available_workers, selected_ids=workers_list)
        
        # Отправляем ответ на callback
        await callback.answer(f"{'Удален' if was_selected else 'Добавлен'} рабочий")
        
        # Добавляем информацию о том, сколько рабочих уже в отчете
        existing_count = len(existing_worker_ids)
        message_text = f"Выберите рабочих для отчета:\n\n"
        if existing_count > 0:
            message_text += f"ℹ️ В отчете уже добавлено рабочих: {existing_count}\n\n"
        
        # Отправляем новое сообщение
        await callback.message.edit_text(
            message_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка при выборе рабочего: {str(e)}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при выборе рабочего", show_alert=True)
    finally:
        await session.close()

# Обработчик завершения выбора рабочих
@admin_report_router.callback_query(F.data == "workers_done", ReportStates.add_workers)
async def process_workers_done(callback: CallbackQuery, state: FSMContext):
    """Обработка завершения выбора рабочих"""
    try:
        await callback.answer()
        
        # Получаем данные из состояния
        data = await state.get_data()
        workers_list = data.get('workers_list', [])
        report_id = data.get('report_id')
        
        if not report_id:
            await callback.message.edit_text(
                "❌ Не найден ID отчета.\n"
                "Пожалуйста, начните создание отчета заново.",
                reply_markup=await get_main_menu_keyboard()
            )
            return
        
        # Получаем объекты рабочих из базы данных
        async with async_session() as session:
            # Получаем отчет с текущими рабочими
            report = await get_report_with_relations(session, report_id)
            if not report:
                await callback.message.edit_text(
                    "❌ Отчет не найден.\n"
                    "Пожалуйста, начните создание отчета заново.",
                    reply_markup=await get_main_menu_keyboard()
                )
                return
            
            # Получаем список ID рабочих, которые уже добавлены в отчет
            existing_worker_ids = [worker.id for worker in report.workers] if report.workers else []
            
            # Объединяем списки ID рабочих, исключая дубликаты
            all_worker_ids = list(set(existing_worker_ids + workers_list))
            
            # Получаем объекты всех рабочих
            selected_workers = []
            for worker_id in all_worker_ids:
                worker = await session.get(Worker, worker_id)
                if worker:
                    selected_workers.append(worker)
            
            if not selected_workers:
                await callback.message.edit_text(
                    "❌ Не удалось найти выбранных рабочих.\n"
                    "Пожалуйста, попробуйте еще раз.",
                    reply_markup=await get_workers_keyboard()
                )
                return
            
            # Обновляем отчет с новым списком рабочих
            report = await create_report(
                session=session,
                report_id=report_id,
                workers_list=all_worker_ids
            )
            
            if not report:
                await callback.message.edit_text(
                    "❌ Не удалось обновить отчет.\n"
                    "Пожалуйста, попробуйте еще раз.",
                    reply_markup=await get_main_menu_keyboard()
                )
                return
            
            # Формируем сообщение об успешном добавлении
            workers_info = [f"• {worker.full_name} ({worker.position})" for worker in selected_workers]
            
            if workers_info:
                names_text = ", ".join(workers_info)
                await callback.message.edit_text(
                    f"✅ Рабочие успешно добавлены в отчет:\n{names_text}\n\n"
                    f"Выберите следующее действие:",
                    reply_markup=await get_report_actions_keyboard()
                )
            else:
                await callback.message.edit_text(
                    "✅ Рабочие успешно добавлены в отчет.\n\n"
                    "Выберите следующее действие:",
                    reply_markup=await get_report_actions_keyboard()
                )
            
            # Обновляем состояние
            await state.update_data(workers_list=all_worker_ids)
            
    except Exception as e:
        logger.error(f"Ошибка при сохранении рабочих: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при сохранении рабочих.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=await get_main_menu_keyboard()
        )

# Обработчик добавления техники
@admin_report_router.callback_query(F.data == "add_equipment")
async def process_add_equipment(callback: CallbackQuery, state: FSMContext):
    """Обработка добавления техники"""
    await callback.answer()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем список техники
        equipment_list = await get_all_equipment(session)
        
        if not equipment_list:
            await callback.message.edit_text(
                "Список техники пуст. Добавьте технику в систему.",
                reply_markup=await get_report_actions_keyboard()
            )
            return
        
        # Формируем клавиатуру с техникой
        keyboard = await get_equipment_keyboard(equipment_list)
        await callback.message.edit_text(
            "Выберите технику для отчета:",
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.add_equipment)
    except Exception as e:
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")
    finally:
        await session.close()

# Обработчик выбора техники
@admin_report_router.callback_query(F.data.startswith("equipment_"), ReportStates.add_equipment)
async def process_equipment_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора техники"""
    # Проверяем, не является ли это callback'ом завершения
    if callback.data == "equipment_done":
        await process_equipment_done(callback, state)
        return
        
    # Извлекаем ID техники из callback_data
    equipment_id = int(callback.data.split("_")[1])
    
    # Получаем текущие данные состояния
    data = await state.get_data()
    equipment_list = data.get('equipment_list', [])
    
    # Проверяем, есть ли изменения
    was_selected = equipment_id in equipment_list
    
    # Добавляем или удаляем технику из списка
    if was_selected:
        equipment_list.remove(equipment_id)
    else:
        equipment_list.append(equipment_id)
    
    # Обновляем данные состояния
    await state.update_data(equipment_list=equipment_list)
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем обновленный список техники
        all_equipment = await get_all_equipment(session)
        
        # Формируем клавиатуру с отмеченной техникой
        keyboard = await get_equipment_keyboard(all_equipment, selected_ids=equipment_list)
        
        # Отправляем ответ на callback
        await callback.answer(f"{'Удалена' if was_selected else 'Добавлена'} техника")
        
        # Отправляем новое сообщение
        await callback.message.answer(
            "Выберите технику для отчета:",
            reply_markup=keyboard
        )
    except Exception as e:
        await callback.message.answer(f"Произошла ошибка: {str(e)}")
    finally:
        await session.close()

# Обработчик завершения выбора техники
@admin_report_router.callback_query(F.data == "equipment_done", ReportStates.add_equipment)
async def process_equipment_done(callback: CallbackQuery, state: FSMContext):
    """Обработка завершения выбора техники"""
    await callback.answer()
    
    # Получаем данные из состояния
    data = await state.get_data()
    report_id = data.get('report_id')
    equipment_list = data.get('equipment_list', [])
    
    if not report_id:
        logging.error("report_id не найден в состоянии")
        await callback.message.edit_text(
            "Произошла ошибка. Пожалуйста, начните создание отчета заново.",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        await state.clear()
        return
    
    # Получаем сессию БД
    session = async_session()
    try:
        # Проверяем существование отчета
        report = await get_report_by_id(session, report_id)
        if not report:
            logging.error(f"Отчет с ID {report_id} не найден")
            await callback.message.edit_text(
                "Отчет не найден. Пожалуйста, начните создание отчета заново.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            await state.clear()
            return
        
        if not equipment_list:
            # Получаем список всей техники
            all_equipment = await get_all_equipment(session)
            await callback.message.edit_text(
                "Вы не выбрали ни одной техники. Выберите технику или вернитесь назад.",
                reply_markup=await get_equipment_keyboard(all_equipment)
            )
            return
        
        # Получаем объекты техники и их имена
        equipment_names = []
        for eq_id in equipment_list:
            equipment = await get_equipment_by_id(session, eq_id)
            if equipment:
                equipment_names.append(equipment.name)
        
        if not equipment_names:
            await callback.message.edit_text(
                "Не удалось найти выбранную технику. Пожалуйста, попробуйте снова.",
                reply_markup=await get_report_actions_keyboard()
            )
            return
        
        # Обновляем отчет с новой техникой
        updated_report = await ReportService.create_or_update_report(
            session=session,
            object_id=report.object_id,
            report_type=report.report_type,
            equipment_list=equipment_list,  # Передаем список ID
            report_id=report_id
        )
        
        if not updated_report:
            logging.error(f"Не удалось обновить отчет {report_id}")
            await callback.message.edit_text(
                "Произошла ошибка при добавлении техники. Пожалуйста, попробуйте снова.",
                reply_markup=await get_report_actions_keyboard()
            )
            return
        
        success_message = (
            f"✅ Техника успешно добавлена в отчет:\n\n"
            f"{chr(10).join(f'• {name}' for name in equipment_names)}"
        )
        
        # Очищаем состояние и возвращаемся к действиям с отчетом
        await state.clear()
        await callback.message.edit_text(
            success_message,
            reply_markup=await get_report_actions_keyboard()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при добавлении техники в отчет: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при добавлении техники. Пожалуйста, попробуйте снова.",
            reply_markup=await get_report_actions_keyboard()
        )
    finally:
        await session.close()

# Обработчик возврата к действиям
@admin_report_router.callback_query(F.data == "back_to_actions")
async def process_back_to_actions(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к действиям"""
    await callback.answer()
    
    # Показываем меню действий для отчета
    await callback.message.edit_text(
        "Выберите действие для продолжения создания отчета:",
        reply_markup=await get_report_actions_keyboard()
    )

# Обработчик сохранения отчета
@admin_report_router.callback_query(F.data == "save_report")
async def process_save_report(callback: CallbackQuery, state: FSMContext):
    """Обработка сохранения отчета"""
    await callback.answer()
    
    # Получаем данные отчета из состояния
    data = await state.get_data()
    logging.info(f"[process_save_report] Данные отчета перед валидацией: {data}")
    
    try:
        # Валидируем данные отчета
        logging.info("[process_save_report] Начинаем валидацию данных")
        await validate_report_data(data)
        logging.info("[process_save_report] Валидация успешно пройдена")
        
        # Получаем сессию БД
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Создаем отчет
            logging.info("[process_save_report] Создаем отчет в БД")
            report = await create_report(session, data)
            logging.info(f"[process_save_report] Отчет успешно создан с ID: {report.id}")
            
            # Получаем объект отдельным запросом
            object_query = select(Object).where(Object.id == report.object_id)
            result = await session.execute(object_query)
            object = result.scalar_one_or_none()
            
            # Очищаем состояние
            await state.clear()
            
            # Отправляем сообщение об успешном создании отчета
            await callback.message.edit_text(
                f"✅ Отчет успешно создан!\n\n"
                f"ID отчета: {report.id}\n"
                f"Объект: {object.name if object else 'Не указан'}\n"
                f"Тип работ: {report.report_type}\n"
                f"Время: {report.type}",
                reply_markup=await get_admin_report_menu_keyboard()
            )
        except Exception as e:
            logging.error(f"[process_save_report] Ошибка при сохранении отчета: {e}")
            await callback.message.edit_text(f"Ошибка при сохранении отчета: {str(e)}")
        finally:
            await session.close()
    except ValidationError as e:
        logging.error(f"[process_save_report] Ошибка валидации: {e}")
        await callback.message.edit_text(f"Ошибка валидации: {str(e)}")
    except Exception as e:
        logging.error(f"[process_save_report] Общая ошибка: {e}")
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")

# Обработчик отмены создания отчета
@admin_report_router.callback_query(F.data == "cancel_report")
async def process_cancel_report(callback: CallbackQuery, state: FSMContext):
    """Обработка отмены создания отчета"""
    await callback.answer()
    
    # Очищаем состояние
    await state.clear()
    
    # Возвращаемся в меню администратора
    await callback.message.edit_text(
        "Создание отчета отменено.",
        reply_markup=await get_admin_report_menu_keyboard()
    )

# Обработчик добавления фотографий
@admin_report_router.callback_query(F.data == "add_photos")
async def process_add_photos(callback: CallbackQuery, state: FSMContext):
    """Обработка добавления фотографий"""
    try:
        await callback.answer()
        
        # Получаем данные из состояния
        data = await state.get_data()
        report_id = data.get('report_id')
        
        if not report_id:
            await callback.message.edit_text(
                "❌ Ошибка: не найден ID отчета",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Получаем сессию БД
        async for session in get_session():
            try:
                # Проверяем существование отчета
                report = await get_report_with_relations(session, report_id)
                if not report:
                    await callback.message.edit_text(
                        "❌ Отчет не найден",
                        reply_markup=await get_admin_report_menu_keyboard()
                    )
                    return
                
                # Получаем текущие фотографии через запрос
                photos_query = select(ReportPhoto).where(ReportPhoto.report_id == report_id)
                result = await session.execute(photos_query)
                photos = result.scalars().all()
                current_photos = [photo.file_path for photo in photos]
                
                # Формируем клавиатуру для фотографий
                keyboard = await get_photos_keyboard(current_photos)
                
                # Отправляем сообщение с инструкциями
                await callback.message.edit_text(
                    "📸 Отправьте фотографии для отчета.\n\n"
                    "ℹ️ Вы можете отправить несколько фотографий.\n"
                    "ℹ️ Когда закончите, нажмите 'Готово'.\n\n"
                    f"ℹ️ Текущее количество фото: {len(current_photos)}",
                    reply_markup=keyboard
                )
                
                # Обновляем состояние
                await state.set_state(ReportStates.add_photos)
                
            except Exception as e:
                logging.error(f"Ошибка при подготовке добавления фото: {str(e)}", exc_info=True)
                await callback.message.edit_text(
                    "❌ Произошла ошибка при подготовке добавления фото",
                    reply_markup=await get_report_actions_keyboard()
                )
            finally:
                await session.close()
    except Exception as e:
        logging.error(f"Ошибка в process_add_photos: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при обработке запроса",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик получения фотографий
@admin_report_router.message(ReportStates.add_photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработка полученных фотографий"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        report_id = data.get('report_id')
        
        if not report_id:
            await message.answer(
                "❌ Ошибка: не найден ID отчета",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Получаем сессию БД
        async for session in get_session():
            try:
                # Проверяем существование отчета
                report = await get_report_with_relations(session, report_id)
                if not report:
                    await message.answer(
                        "❌ Отчет не найден",
                        reply_markup=await get_admin_report_menu_keyboard()
                    )
                    return
                
                # Создаем директорию для фотографий, если она не существует
                photos_dir = os.path.join(settings.MEDIA_ROOT, 'reports', str(report_id), 'photos')
                os.makedirs(photos_dir, exist_ok=True)
                
                saved_photos = []
                # Сохраняем каждую фотографию
                for photo in message.photo:
                    try:
                        # Генерируем уникальное имя файла
                        file_name = f"{uuid.uuid4()}.jpg"
                        file_path = os.path.join(photos_dir, file_name)
                        
                        # Скачиваем файл
                        await message.bot.download(
                            photo,
                            destination=file_path
                        )
                        
                        # Сохраняем информацию о фото в БД
                        photo_record = ReportPhoto(
                            report_id=report_id,
                            file_path=file_path,
                            description=None  # Можно добавить описание позже
                        )
                        session.add(photo_record)
                        saved_photos.append(file_path)
                        
                    except Exception as e:
                        logging.error(f"Ошибка при сохранении фото: {str(e)}", exc_info=True)
                        continue
                
                # Сохраняем изменения в БД
                await session.commit()
                
                # Получаем обновленный список фотографий через запрос
                photos_query = select(ReportPhoto).where(ReportPhoto.report_id == report_id)
                result = await session.execute(photos_query)
                photos = result.scalars().all()
                current_photos = [photo.file_path for photo in photos]
                
                # Формируем клавиатуру для фотографий
                keyboard = await get_photos_keyboard(current_photos)
                
                # Отправляем сообщение с подтверждением
                await message.answer(
                    f"✅ Фотографии успешно добавлены!\n\n"
                    f"📸 Всего фотографий в отчете: {len(current_photos)}\n\n"
                    f"Вы можете отправить еще фотографии или нажать 'Готово'.",
                    reply_markup=keyboard
                )
                
            except Exception as e:
                logging.error(f"Ошибка при обработке фото: {str(e)}", exc_info=True)
                await message.answer(
                    "❌ Произошла ошибка при сохранении фотографий",
                    reply_markup=await get_report_actions_keyboard()
                )
    except Exception as e:
        logging.error(f"Ошибка в process_photo: {str(e)}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке фотографий",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик завершения добавления фотографий
@admin_report_router.callback_query(F.data == "photos_done", ReportStates.add_photos)
async def process_photos_done(callback: CallbackQuery, state: FSMContext):
    """Обработка завершения добавления фотографий"""
    try:
        await callback.answer()
        
        # Получаем данные из состояния
        data = await state.get_data()
        report_id = data.get('report_id')
        
        if not report_id:
            await callback.message.edit_text(
                "❌ Ошибка: не найден ID отчета",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Получаем сессию БД
        async for session in get_session():
            try:
                # Получаем отчет с фотографиями
                report = await get_report_with_relations(session, report_id)
                if not report:
                    await callback.message.edit_text(
                        "❌ Отчет не найден",
                        reply_markup=await get_admin_report_menu_keyboard()
                    )
                    return
                
                # Получаем список фотографий
                photos = [photo.file_path for photo in report.photos] if report.photos else []
                
                # Формируем сообщение с информацией о фотографиях
                message_text = (
                    f"✅ Добавление фотографий завершено!\n\n"
                    f"📸 Всего фотографий в отчете: {len(photos)}\n\n"
                    f"Выберите действие для продолжения:"
                )
                
                # Показываем меню действий для отчета
                await callback.message.edit_text(
                    message_text,
                    reply_markup=await get_report_actions_keyboard()
                )
                
                # Обновляем состояние
                await state.set_state(ReportStates.edit_report)
                
            except Exception as e:
                logging.error(f"Ошибка при завершении добавления фото: {str(e)}", exc_info=True)
                await callback.message.edit_text(
                    "❌ Произошла ошибка при завершении добавления фотографий",
                    reply_markup=await get_report_actions_keyboard()
                )
    except Exception as e:
        logging.error(f"Ошибка в process_photos_done: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при обработке запроса",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик добавления комментариев
@admin_report_router.callback_query(F.data == "add_comments")
async def process_add_comments(callback: CallbackQuery, state: FSMContext):
    """Обработка добавления комментариев"""
    await callback.answer()
    
    # Получаем текущие данные состояния
    data = await state.get_data()
    comments = data.get('comments', '')
    
    # Формируем клавиатуру для комментариев
    keyboard = await get_comments_keyboard()
    
    # Отправляем сообщение с инструкциями
    await callback.message.edit_text(
        "Введите комментарии к отчету.\n",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.add_comments)

# Обработчик получения комментариев
@admin_report_router.message(ReportStates.add_comments)
async def process_comments(message: Message, state: FSMContext):
    """Обработка полученных комментариев"""
    try:
        # Получаем ID отчета из состояния
        data = await state.get_data()
        report_id = data.get('report_id')
        
        if not report_id:
            await message.answer(
                "❌ Ошибка: не найден ID отчета",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return

        # Получаем сессию БД
        async for session in get_session():
            try:
                # Получаем отчет из БД
                report = await get_report_with_relations(session, report_id)
                
                if not report:
                    await message.answer(
                        "❌ Отчет не найден",
                        reply_markup=await get_admin_report_menu_keyboard()
                    )
                    return

                # Обновляем комментарии в отчете
                updated_report = await create_report(
                    session=session,
                    data={
                        'report_id': report_id,
                        'comments': message.text
                    }
                )

                if not updated_report:
                    await message.answer(
                        "❌ Ошибка при сохранении комментариев",
                        reply_markup=await get_report_actions_keyboard()
                    )
                    return

                # Сохраняем комментарии в состоянии
                await state.update_data(comments=message.text)
                
                # Формируем информацию об отчете
                report_info = (
                    f"📝 Редактирование отчета #{report.id}\n\n"
                    f"Тип: {report.type}\n"
                    f"Дата: {report.date.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Статус: {report.status}\n"
                    f"Объект: {report.object.name}\n"
                )
                
                # Добавляем тип работ, если есть
                if report.type:
                    report_info += f"Тип работ: {report.type}\n"
                
                # Добавляем подтип работ, если есть
                if report.work_subtype:
                    report_info += f"Подтип работ: {report.work_subtype}\n"
                
                # Добавляем ИТР, если есть
                if report.itr_personnel:
                    itr_names = [itr.full_name for itr in report.itr_personnel]
                    if itr_names:
                        report_info += f"ИТР: {', '.join(itr_names)}\n"
                
                # Добавляем рабочих, если есть
                if report.workers:
                    worker_names = [worker.full_name for worker in report.workers]
                    if worker_names:
                        report_info += f"Рабочие: {', '.join(worker_names)}\n"
                
                # Добавляем технику, если есть
                if report.equipment:
                    equipment_names = [eq.name for eq in report.equipment]
                    if equipment_names:
                        report_info += f"Техника: {', '.join(equipment_names)}\n"

                # Добавляем фотографии, если есть
                if report.photos:
                    photo_count = len(report.photos)
                    report_info += f"Фотографий: {photo_count}\n"
                
                # Добавляем комментарии
                report_info += f"Комментарий: {message.text}\n"
                
                # Показываем меню действий для редактирования
                await message.answer(
                    f"✅ Комментарии успешно сохранены!\n\n{report_info}\nВыберите действие:",
                    reply_markup=await get_report_actions_keyboard()
                )
                
                # Устанавливаем состояние редактирования
                await state.set_state(ReportStates.edit_report)
                
            except Exception as e:
                logging.error(f"Ошибка при сохранении комментариев: {str(e)}", exc_info=True)
                await message.answer(
                    f"❌ Произошла ошибка при сохранении комментариев: {str(e)}",
                    reply_markup=await get_report_actions_keyboard()
                )
    except Exception as e:
        logging.error(f"Ошибка в process_comments: {str(e)}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке комментариев",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик отправки отчета
@admin_report_router.callback_query(F.data == "send_report")
@error_handler
@with_session
async def process_select_report_for_sending(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора отчета для отправки"""
    await callback.answer()
    
    try:
        # Получаем список отчетов со статусом "draft"
        reports = await get_reports_by_status(session, "draft")
        
        if not reports:
            await callback.message.answer(
                "❌ Нет доступных отчетов для отправки",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Формируем клавиатуру с отчетами
        keyboard = []
        for report in reports:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📄 Отчет #{report.id} от {report.date.strftime('%d.%m.%Y')}",
                    callback_data=f"select_report_{report.id}"
                )
            ])
        
        # Добавляем кнопку "Назад"
        back_button = InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu")
        keyboard.append([back_button])
        
        await callback.message.answer(
            "Выберите отчет для отправки:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
        # Устанавливаем состояние выбора отчета
        await state.set_state(ReportStates.select_report_to_send)
        
    except Exception as e:
        logging.error(f"Ошибка в process_select_report_for_sending: {str(e)}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при получении списка отчетов",
            reply_markup=await get_admin_report_menu_keyboard()
        )

@admin_report_router.callback_query(F.data.startswith("select_report_"), ReportStates.select_report_to_send)
async def process_select_report_recipient_list(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора отчета для отправки"""
    await callback.answer()
    
    # Получаем ID отчета из callback_data
    report_id = int(callback.data.split("_")[2])
    
    try:
        # Получаем сессию БД
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Получаем отчет
            report = await get_report_with_relations(session, report_id)
            if not report:
                await callback.message.edit_text(
                    "❌ Отчет не найден",
                    reply_markup=await get_admin_report_menu_keyboard()
                )
                return
            
            # Получаем список клиентов
            clients = await get_all_clients(session)
            
            if not clients:
                await callback.message.edit_text(
                    "❌ Нет доступных получателей для отправки отчета",
                    reply_markup=await get_admin_report_menu_keyboard()
                )
                return
            
            # Формируем клавиатуру с получателями
            keyboard = []
            for client in clients:
                if client.user:  # Проверяем, что у клиента есть связанный пользователь
                    keyboard.append([
                        InlineKeyboardButton(
                            text=f"👤 {client.user.username or client.user.telegram_id}",
                            callback_data=f"select_recipient_{client.user.id}"
                        )
                    ])
            
            # Добавляем кнопку "Назад"
            keyboard.append([
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="send_report"
                )
            ])
            
            # Сохраняем ID отчета в состоянии
            await state.update_data(selected_report_id=report_id)
            
            # Отправляем сообщение с выбором получателя
            await callback.message.edit_text(
                "👤 Выберите получателя отчета:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            
            # Устанавливаем состояние выбора получателя
            await state.set_state(ReportStates.select_report_recipient)
            
        except Exception as e:
            logging.error(f"Ошибка при получении списка получателей: {str(e)}", exc_info=True)
            await callback.message.edit_text(
                f"❌ Произошла ошибка при получении списка получателей: {str(e)}",
                reply_markup=await get_admin_report_menu_keyboard()
            )
        finally:
            await session.close()
    except Exception as e:
        logging.error(f"Общая ошибка: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Произошла ошибка: {str(e)}",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик выбора получателя отчета
@admin_report_router.callback_query(F.data.startswith("select_recipient_"), ReportStates.select_report_recipient)
async def process_select_report_recipient(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора получателя отчета"""
    try:
        # Получаем ID получателя из callback_data
        recipient_id = int(callback.data.split('_')[2])
        
        # Получаем данные из состояния
        data = await state.get_data()
        report_id = data.get('selected_report_id')  # Используем правильный ключ
        
        if not report_id:
            await callback.message.answer("❌ Ошибка: отчет не найден")
            return
            
        async with async_session() as session:
            # Получаем отчет
            report = await get_report_with_relations(session, report_id)
            if not report:
                await callback.message.answer("❌ Ошибка: отчет не найден")
                return
                
            # Отправляем отчет
            success = await ReportService.send_report(session, report.id, recipient_id)
            
            if success:
                await callback.message.answer(
                    f"✅ Отчет успешно отправлен!\n\n"
                    f"📋 Тип: {report.type}\n"
                    f"📅 Дата: {report.date.strftime('%d.%m.%Y')}\n"
                    f"🏗 Объект: {report.object.name}"
                )
            else:
                await callback.message.answer("❌ Ошибка при отправке отчета")
                
    except Exception as e:
        logging.error(f"Ошибка в process_select_report_recipient: {str(e)}", exc_info=True)
        await callback.message.answer("❌ Произошла ошибка при отправке отчета")

@admin_report_router.callback_query(ReportManagementStates.waiting_for_type)
@error_handler
async def process_report_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа отчета"""
    report_type = callback.data.split(":")[1]
    await state.update_data(report_type=report_type)
    await state.set_state(ReportManagementStates.waiting_for_filter)
    
    await callback.message.edit_text(
        "Выберите фильтр:",
        reply_markup=get_report_filter_keyboard()
    )

@admin_report_router.callback_query(ReportManagementStates.waiting_for_filter)
@error_handler
async def process_report_filter(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра"""
    filter_type = callback.data.split(":")[1]
    await state.update_data(filter_type=filter_type)
    await state.set_state(ReportManagementStates.waiting_for_date_range)
    
    await callback.message.edit_text(
        "Введите период в формате ДД.ММ.ГГГГ-ДД.ММ.ГГГГ\n"
        "Например: 01.01.2024-31.01.2024",
        reply_markup=get_back_keyboard()
    )

@admin_report_router.message(ReportManagementStates.waiting_for_date_range)
@error_handler
@with_session
async def process_date_range(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """Обработка ввода диапазона дат"""
    try:
        # Парсим даты
        start_date, end_date = validate_date_range(message.text)
        
        # Получаем отчеты за указанный период
        reports = await get_reports_by_date_range(session, start_date, end_date)
        
        if not reports:
            await message.answer(
                "За указанный период отчетов не найдено.",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Формируем сводку по отчетам
        summary = await generate_report_summary(reports)
        
        # Отправляем сводку
        await message.answer(summary)
        
        # Сбрасываем состояние
        await state.clear()
    except ValueError as e:
        await message.answer(f"Ошибка в формате даты: {str(e)}")
    except Exception as e:
        await message.answer(f"Произошла ошибка: {str(e)}")

# Обработчик выбора типа отчета
@admin_report_router.callback_query(F.data.in_(["morning_report", "evening_report"]), ReportStates.select_report_type)
async def process_report_type_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа отчета"""
    await callback.answer()
    
    # Сохраняем выбранный тип отчета
    report_type = callback.data.replace("_report", "")
    logging.info(f"[process_report_type_selection] Выбран тип отчета: {report_type}")
    
    try:
        # Получаем сессию БД
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Получаем данные отчета из состояния
            data = await state.get_data()
            logging.info(f"[process_report_type_selection] Данные из состояния перед созданием отчета: {data}")
            
            # Создаем базовый отчет
            report = await create_base_report(session, {
                'object_id': data['object_id'],
                'report_type': report_type,
                'work_type': data.get('work_type', 'general_construction')
            })
            logging.info(f"[process_report_type_selection] Создан базовый отчет с ID: {report.id}")
            
            # Сохраняем ID отчета и инициализируем пустые списки в состоянии
            state_data = {
                'report_id': report.id,
                'object_id': data['object_id'],
                'report_type': report_type,
                'type': report_type,
                'work_type': report_type,
                'work_subtype': data.get('work_subtype'),
                'comments': data.get('comments', ''),
                'itr_list': [],
                'workers_list': [],
                'equipment_list': []
            }
            await state.update_data(**state_data)
            
            # Проверяем обновленное состояние
            updated_data = await state.get_data()
            logging.info(f"[process_report_type_selection] Обновленные данные состояния: {updated_data}")
            
            # Отправляем сообщение об успешном создании отчета
            await callback.message.answer(
                f"✅ Отчет создан!\n\n"
                f"Теперь выберите действие для продолжения:",
                reply_markup=await get_report_actions_keyboard()
            )
            
            # Обновляем состояние
            await state.set_state(ReportStates.select_actions)
            
        except Exception as e:
            logging.error(f"[process_report_type_selection] Ошибка при создании отчета: {str(e)}")
            await callback.message.answer(f"Произошла ошибка при создании отчета: {str(e)}")
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"[process_report_type_selection] Ошибка при получении сессии БД: {str(e)}")
        await callback.message.answer("Произошла ошибка при подключении к базе данных")

@admin_report_router.callback_query(F.data == "back_to_object", ReportStates.select_work_type)
async def process_back_to_object(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к выбору объекта"""
    await callback.answer()
    
    # Получаем сессию БД
    session_gen = get_session()
    session = await session_gen.__anext__()
    
    try:
        # Получаем список объектов
        objects = await get_all_objects(session)
        
        if not objects:
            await callback.message.edit_text(
                "Нет доступных объектов для создания отчета.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Показываем список объектов
        keyboard = await get_objects_keyboard(session)
        await callback.message.edit_text(
            "Выберите объект для отчета:",
            reply_markup=keyboard
        )
        
        # Обновляем состояние
        await state.set_state(ReportStates.select_object)
    except Exception as e:
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")
    finally:
        await session.close()

@admin_report_router.callback_query(F.data == "back_to_report_type", ReportStates.select_work_subtype)
async def process_back_to_work_type(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к выбору типа работ"""
    await callback.answer()
    
    # Показываем типы работ
    keyboard = get_work_type_keyboard()
    await callback.message.edit_text(
        "Выберите тип работ:",
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.select_work_type)

async def process_itr_done(callback: CallbackQuery, state: FSMContext):
    """Обработчик завершения выбора ИТР"""
    try:
        # Получаем данные из состояния
        state_data = await state.get_data()
        report_id = state_data.get('report_id')
        itr_list = state_data.get('selected_itrs', [])

        # Получаем сессию БД
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        try:
            # Получаем информацию об ИТР
            itr_names = []
            for itr_id in itr_list:
                itr = await get_itr_by_id(session, itr_id)
                if itr:
                    itr_names.append(itr.name)

            # Обновляем отчет в базе данных
            await create_report(session, {
                'report_id': report_id,
                'itr_list': itr_list
            })

            # Формируем сообщение об успешном добавлении
            if itr_names:
                names_text = ", ".join(itr_names)
                await callback.message.answer(
                    f"✅ ИТР успешно добавлены в отчет:\n{names_text}\n\n"
                    f"Выберите следующее действие:",
                    reply_markup=get_report_actions_keyboard()
                )
            else:
                await callback.message.answer(
                    "✅ ИТР успешно добавлены в отчет.\n\n"
                    "Выберите следующее действие:",
                    reply_markup=get_report_actions_keyboard()
                )
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Ошибка при сохранении ИТР: {str(e)}")
        await callback.message.answer("Произошла ошибка при сохранении ИТР") 

@admin_report_router.callback_query(F.data == "export_report")
@error_handler
@with_session
async def process_export_report_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Показать меню экспорта отчетов"""
    try:
        # Получаем все отчеты
        reports = await get_reports_for_export(session)
        
        if not reports:
            await callback.message.edit_text(
                "❌ Нет доступных отчетов для экспорта",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Формируем клавиатуру с отчетами
        keyboard = InlineKeyboardBuilder()
        for report in reports:
            # Форматируем дату отчета
            report_date = report.date.strftime('%d.%m.%Y')
            # Получаем название объекта
            object_name = report.object.name if report.object else "Неизвестный объект"
            
            keyboard.row(
                InlineKeyboardButton(
                    text=f"📄 {object_name} от {report_date}",
                    callback_data=f"select_report_for_export_{report.id}"
                )
            )
        
        # Добавляем кнопку "Назад"
        keyboard.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu"))
        
        await callback.message.edit_text(
            "Выберите отчет для экспорта:",
            reply_markup=keyboard.as_markup()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при получении списка отчетов: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Произошла ошибка при получении списка отчетов: {str(e)}",
            reply_markup=await get_admin_report_menu_keyboard()
        )

@admin_report_router.callback_query(F.data.startswith("select_report_for_export_"))
@error_handler
@with_session
async def process_select_report_for_export(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора отчета для экспорта"""
    try:
        # Получаем ID отчета из callback_data
        report_id = int(callback.data.split("_")[-1])
        
        # Получаем отчет
        report = await get_report_with_relations(session, report_id)
        if not report:
            await callback.message.edit_text(
                "❌ Отчет не найден",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Сохраняем ID отчета в состоянии
        await state.update_data(selected_report_id=report_id)
        
        # Показываем меню выбора формата экспорта
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(text="📄 Экспорт в PDF", callback_data="export_pdf"),
            InlineKeyboardButton(text="📊 Экспорт в Excel", callback_data="export_excel")
        )
        keyboard.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_report_menu"))
        
        # Форматируем дату отчета
        report_date = report.date.strftime('%d.%m.%Y')
        object_name = report.object.name if report.object else "Неизвестный объект"
        
        await callback.message.edit_text(
            f"Выбран отчет:\n"
            f"📅 Дата: {report_date}\n"
            f"🏗 Объект: {object_name}\n\n"
            f"Выберите формат экспорта:",
            reply_markup=keyboard.as_markup()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при выборе отчета: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Произошла ошибка при выборе отчета: {str(e)}",
            reply_markup=await get_admin_report_menu_keyboard()
        )

@admin_report_router.callback_query(F.data.in_(["export_pdf", "export_excel"]))
@error_handler
@with_session
async def process_export_reports(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка экспорта отчетов"""
    try:
        # Получаем ID выбранного отчета из состояния
        data = await state.get_data()
        report_id = data.get('selected_report_id')
        
        if not report_id:
            await callback.message.edit_text(
                "❌ Отчет не выбран",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Получаем отчет со всеми связями
        report = await get_report_with_relations(session, report_id)
        if not report:
            await callback.message.edit_text(
                "❌ Отчет не найден",
                reply_markup=await get_admin_report_menu_keyboard()
            )
            return
        
        # Загружаем все связанные данные
        await session.refresh(report, ['object', 'itr_personnel', 'workers', 'equipment', 'photos'])
        
        # Создаем директорию для экспорта, если её нет
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # Генерируем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        object_name = report.object.name if report.object else "unknown"
        
        if callback.data == "export_pdf":
            # Экспорт в PDF
            output_path = os.path.join(export_dir, f'report_{object_name}_{timestamp}.pdf')
            export_report_to_pdf([report], output_path)
            file_type = "PDF"
        else:
            # Экспорт в Excel
            output_path = os.path.join(export_dir, f'report_{object_name}_{timestamp}.xlsx')
            export_report_to_excel([report], output_path)
            file_type = "Excel"
        
        # Отправляем файл
        with open(output_path, 'rb') as file:
            file_content = file.read()
            input_file = BufferedInputFile(file_content, filename=os.path.basename(output_path))
            await callback.message.answer_document(
                document=input_file,
                caption=f"✅ Отчет успешно экспортирован в {file_type}"
            )
        
        # Удаляем временный файл
        os.remove(output_path)
        
        # Возвращаемся в меню администратора
        await callback.message.edit_text(
            "Выберите действие:",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при экспорте отчета: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Произошла ошибка при экспорте отчета: {str(e)}",
            reply_markup=await get_admin_report_menu_keyboard()
        )