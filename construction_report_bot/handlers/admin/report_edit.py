import logging
import os
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types.input_file import FSInputFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Union
from datetime import datetime

from construction_report_bot.database.crud import (
    get_report_by_id,
    get_report_with_relations,
    get_all_itr,
    get_all_workers,
    get_all_equipment,
    get_itr_by_id,
    get_worker_by_id,
    get_equipment_by_id,
    create_report
)
from construction_report_bot.database.models import (
    Report, ReportPhoto, ITR, Worker, Equipment,
    report_itr, report_workers, report_equipment, Object
)
from construction_report_bot.config.settings import settings
from construction_report_bot.config.keyboards import (
    get_main_menu_keyboard,
    get_report_actions_keyboard,
    get_itr_keyboard,
    get_workers_keyboard,
    get_equipment_keyboard,
    get_photos_keyboard,
    get_comments_keyboard,
    get_back_keyboard,
    get_admin_report_menu_keyboard
)
from construction_report_bot.utils.decorators import error_handler, with_session
from construction_report_bot.middlewares.role_check import admin_required
from construction_report_bot.utils.logging.logger import log_admin_action, log_error
from construction_report_bot.states.report_states import ReportStates
from construction_report_bot.services.report_service import ReportService
from construction_report_bot.database.session import async_session

logger = logging.getLogger(__name__)

# Создаем роутер для редактирования отчетов
admin_report_edit_router = Router()
# Добавляем middleware для проверки роли
admin_report_edit_router.message.middleware(admin_required())
admin_report_edit_router.callback_query.middleware(admin_required())

# Обработчик для редактирования отчета
@admin_report_edit_router.callback_query(F.data.startswith("edit_report_"))
@error_handler
@with_session
async def process_edit_report(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка редактирования отчета"""
    # Получаем ID отчета из callback_data
    report_id = int(callback.data.split("_")[2])
    logging.info(f"Попытка редактирования отчета #{report_id}")
    logging.info(f"Callback data: {callback.data}")
    
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
        if report.status == "sent":
            report_info = (
                f"✅ Отчет #{report.id} отправлен заказчику\n\n"
                f"Тип: {report.type}\n"
                f"Дата: {report.date.strftime('%d.%m.%Y %H:%M')}\n"
                f"Статус: {report.status}\n"
                f"Объект: {object.name if object else 'Не указан'}\n"
            )
        else:   
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
            reply_markup=await get_report_actions_keyboard(report_id)
        )
        
        # Устанавливаем состояние редактирования
        await state.set_state(ReportStates.edit_report)
        
    except Exception as e:
        logging.error(f"Ошибка при редактировании отчета: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при редактировании отчета",
            reply_markup=await get_admin_report_menu_keyboard()
        )

# Обработчик добавления ИТР
@admin_report_edit_router.callback_query(F.data == "add_itr")
@error_handler
@with_session
async def process_add_itr(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка добавления ИТР"""
    await callback.answer()
    
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

# Обработчик выбора ИТР
@admin_report_edit_router.callback_query(F.data.startswith("itr_"), ReportStates.add_itr)
@error_handler
@with_session
async def process_itr_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора ИТР"""
    # Извлекаем ID ИТР из callback_data
    itr_id = int(callback.data.split("_")[1])
    
    # Получаем данные из состояния
    data = await state.get_data()
    report_id = data.get('report_id')
    
    if not report_id:
        await callback.answer("❌ Ошибка: не найден ID отчета", show_alert=True)
        return
    
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
    
    # Возвращаем к редактированию отчета
    await state.set_state(ReportStates.edit_report)

    
    # Отправляем новое сообщение с меню действий
    await callback.message.edit_text(
        f"✅ ИТР {itr.full_name} успешно добавлен в отчет.\n\n{await format_report_info(report, callback.message.text)}\nВыберите действие:",
        reply_markup=await get_report_actions_keyboard(report_id)
    )

# Обработчик добавления рабочих
@admin_report_edit_router.callback_query(F.data == "add_workers")
@error_handler
@with_session
async def process_add_workers(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка добавления рабочих"""
    await callback.answer()
    
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
    
    # Инициализируем список выбранных рабочих в состоянии
    await state.update_data(workers_list=existing_worker_ids)
    
    # Формируем клавиатуру со всеми рабочими, отмечая тех, кто уже добавлен в отчет
    keyboard = await get_workers_keyboard(all_workers, selected_ids=existing_worker_ids)
    
    # Добавляем информацию о том, сколько рабочих уже в отчете
    existing_count = len(existing_worker_ids)
    message_text = f"Выберите рабочих для отчета:\n\n"
    if existing_count > 0:
        message_text += f"ℹ️ В отчете уже добавлено рабочих: {existing_count}\n\n"
    message_text += "✅ - рабочие уже добавлены в отчет\n"
    message_text += "Вы можете снять галочки, чтобы удалить рабочих из отчета, или отметить новых рабочих для добавления."
    
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard
    )
    
    # Обновляем состояние
    await state.set_state(ReportStates.add_workers)

# Обработчик выбора рабочих
@admin_report_edit_router.callback_query(F.data.startswith("worker_"), ReportStates.add_workers)
@error_handler
@with_session
async def process_worker_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
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
    
    # Получаем отчет с текущими рабочими
    report = await get_report_with_relations(session, report_id)
    if not report:
        await callback.answer("❌ Ошибка: отчет не найден", show_alert=True)
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
    
    # Получаем обновленный список всех рабочих
    all_workers = await get_all_workers(session)
    
    # Формируем клавиатуру с отмеченными рабочими
    keyboard = await get_workers_keyboard(all_workers, selected_ids=workers_list)
    
    # Отправляем ответ на callback
    await callback.answer(f"{'Удален' if was_selected else 'Добавлен'} рабочий")
    
    # Добавляем информацию о том, сколько рабочих выбрано
    selected_count = len(workers_list)
    message_text = f"Выберите рабочих для отчета:\n\n"
    message_text += f"ℹ️ Выбрано рабочих: {selected_count}\n\n"
    message_text += "✅ - рабочие уже добавлены в отчет\n"
    message_text += "Вы можете снять галочки, чтобы удалить рабочих из отчета, или отметить новых рабочих для добавления."
    
    # Отправляем новое сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard
    )

# Обработчик завершения выбора рабочих
@admin_report_edit_router.callback_query(F.data == "workers_done", ReportStates.add_workers)
@error_handler
@with_session
async def process_workers_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка завершения выбора рабочих"""
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
    
    # Получаем отчет с текущими рабочими
    report = await get_report_with_relations(session, report_id)
    if not report:
        await callback.message.edit_text(
            "❌ Отчет не найден.\n"
            "Пожалуйста, начните создание отчета заново.",
            reply_markup=await get_main_menu_keyboard()
        )
        return
    
    # Получаем объекты всех выбранных рабочих
    selected_workers = []
    for worker_id in workers_list:
        worker = await get_worker_by_id(session, worker_id)
        if worker:
            selected_workers.append(worker)
    
    if not selected_workers:
        await callback.message.edit_text(
            "❌ Не удалось найти выбранных рабочих.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=await get_workers_keyboard()
        )
        return
    
    # Обновляем отчет с новым списком рабочих через ReportService
    updated_report = await ReportService.add_workers_to_report(
        session=session,
        report_id=report_id,
        worker_ids=workers_list
    )
    
    if not updated_report:
        await callback.message.edit_text(
            "❌ Не удалось обновить отчет.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=await get_main_menu_keyboard()
        )
        return
    # Убираем состояние выбора рабочих, но сохраняем основные данные отчета
    await state.set_state(ReportStates.edit_report)

    await callback.message.edit_text(
        f"✅ Рабочие успешно обновлены в отчете.\n\n{await format_report_info(report, callback.message.text)}\nВыберите действие:",
        reply_markup=await get_report_actions_keyboard(report_id)
    )

# Обработчик добавления техники
@admin_report_edit_router.callback_query(F.data == "add_equipment")
@error_handler
@with_session
async def process_add_equipment(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка добавления техники"""
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
    
    # Получаем отчет с текущей техникой
    report = await get_report_with_relations(session, report_id)
    if not report:
        await callback.message.edit_text(
            "❌ Отчет не найден",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return
    
    # Получаем список техники
    all_equipment = await get_all_equipment(session)
    
    if not all_equipment:
        await callback.message.edit_text(
            "Список техники пуст. Добавьте технику в систему.",
            reply_markup=await get_report_actions_keyboard()
        )
        return
    
    # Получаем список ID текущей техники из отчета
    current_equipment_ids = [eq.id for eq in report.equipment] if report.equipment else []
    
    # Инициализируем список выбранной техники в состоянии текущими значениями
    await state.update_data(equipment_list=current_equipment_ids)
    
    # Устанавливаем состояние выбора техники
    await state.set_state(ReportStates.add_equipment)
    
    # Формируем клавиатуру с техникой, отмечая уже выбранную
    keyboard = await get_equipment_keyboard(all_equipment, selected_ids=current_equipment_ids)
    
    # Добавляем информацию о том, сколько техники уже в отчете
    existing_count = len(current_equipment_ids)
    message_text = f"Выберите технику для отчета:\n\n"
    if existing_count > 0:
        message_text += f"ℹ️ В отчете уже добавлено единиц техники: {existing_count}\n\n"
    message_text += "✅ - техника уже добавлена в отчет\n"
    message_text += "Вы можете снять галочки, чтобы удалить технику из отчета, или отметить новую технику для добавления."
    
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard
    )

# Обработчик завершения выбора техники
@admin_report_edit_router.callback_query(F.data == "equipment_done", ReportStates.add_equipment)
@error_handler
@with_session
async def process_equipment_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
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
            equipment = await session.get(Equipment, eq_id)
            if equipment:
                equipment_names.append(equipment.name)
        
        if not equipment_names:
            await callback.message.edit_text(
                "Не удалось найти выбранную технику. Пожалуйста, попробуйте снова.",
                reply_markup=await get_report_actions_keyboard(report_id)
            )
            return
        
        # Обновляем отчет с новой техникой
        updated_report = await ReportService.add_equipment_to_report(
            session=session,
            report_id=report_id,
            equipment_data=[{"equipment_id": eq_id} for eq_id in equipment_list]
        )
        
        logging.info(f"Отправка техники для отчета #{report_id}. Список техники: {equipment_list}, Количество: {len(equipment_list)}")
        
        if not updated_report:
            logging.error(f"Не удалось обновить отчет {report_id}")
            await callback.message.edit_text(
                "Произошла ошибка при добавлении техники. Пожалуйста, попробуйте снова.",
                reply_markup=await get_report_actions_keyboard(report_id)
            )
            return
        
        # Формируем сообщение об успешном обновлении
        equipment_info = [f"• {name}" for name in equipment_names]
        
        if equipment_info:
            names_text = "\n".join(equipment_info)
            await callback.message.edit_text(
                f"✅ Техника успешно обновлена в отчете:\n{names_text}\n\n {await format_report_info(report, callback.message.text)}\nВыберите действие:",
                reply_markup=await get_report_actions_keyboard(report_id)
            )
        else:
            await callback.message.edit_text(
                "✅ Техника успешно обновлена в отчете.\n\n {await format_report_info(report, callback.message.text)}\nВыберите действие:",
                reply_markup=await get_report_actions_keyboard(report_id)
            )
        
        # Убираем состояние выбора техники, но сохраняем основные данные отчета
        await state.set_state(ReportStates.edit_report)

        
    except Exception as e:
        logging.error(f"Ошибка при добавлении техники в отчет: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при добавлении техники. Пожалуйста, попробуйте снова.",
            reply_markup=await get_report_actions_keyboard(report_id)
        )

# Обработчик выбора техники
@admin_report_edit_router.callback_query(F.data.startswith("equipment_"), ReportStates.add_equipment)
@error_handler
@with_session
async def process_equipment_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка выбора техники"""
    # Извлекаем ID техники из callback_data
    equipment_id = int(callback.data.split("_")[1])
    
    # Получаем текущие данные состояния
    data = await state.get_data()
    equipment_list = data.get('equipment_list', [])
    report_id = data.get('report_id')
    
    if not report_id:
        await callback.answer("❌ Ошибка: не найден ID отчета", show_alert=True)
        return
    
    # Получаем отчет с текущей техникой
    report = await get_report_with_relations(session, report_id)
    if not report:
        await callback.answer("❌ Ошибка: отчет не найден", show_alert=True)
        return
    
    # Проверяем, есть ли изменения
    was_selected = equipment_id in equipment_list
    
    # Добавляем или удаляем технику из списка
    if was_selected:
        equipment_list.remove(equipment_id)
    else:
        equipment_list.append(equipment_id)
    
    # Обновляем данные состояния
    await state.update_data(equipment_list=equipment_list)
    
    # Добавляем логирование для отслеживания списка техники
    logging.info(f"Обновлен список техники: {equipment_list}")
    
    # Получаем обновленный список техники
    all_equipment = await get_all_equipment(session)
    
    # Формируем клавиатуру с отмеченной техникой
    keyboard = await get_equipment_keyboard(all_equipment, selected_ids=equipment_list)
    
    # Отправляем ответ на callback
    await callback.answer(f"{'Удалена' if was_selected else 'Добавлена'} техника")
    
    # Добавляем информацию о том, сколько техники выбрано
    selected_count = len(equipment_list)
    message_text = f"Выберите технику для отчета:\n\n"
    message_text += f"ℹ️ Выбрано единиц техники: {selected_count}\n\n"
    message_text += "✅ - техника уже добавлена в отчет\n"
    message_text += "Вы можете снять галочки, чтобы удалить технику из отчета, или отметить новую технику для добавления."
    
    # Редактируем существующее сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard
    )
    
    # Сохраняем состояние
    await state.set_state(ReportStates.add_equipment)

# Обработчик добавления фотографий
@admin_report_edit_router.callback_query(F.data == "add_photos")
@error_handler
@with_session
async def process_add_photos(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка добавления фотографий"""
    # Получаем данные из состояния
    data = await state.get_data()
    report_id = data.get('report_id')
    
    if not report_id:
        await callback.message.edit_text(
            "❌ Ошибка: не найден ID отчета",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return
    
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

# Обработчик получения фотографий
@admin_report_edit_router.message(ReportStates.add_photos, F.photo)
@error_handler
@with_session
async def process_photo(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка полученных фотографий"""
    # Получаем данные из состояния
    data = await state.get_data()
    report_id = data.get('report_id')
    
    if not report_id:
        await message.answer(
            "❌ Ошибка: не найден ID отчета",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return
    
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
    # Логируем информацию о полученных фотографиях
    logging.info(f"Получено фотографий: {len(message.photo)}")
    
    # Находим самую большую версию фотографии
    largest_photo = max(message.photo, key=lambda x: x.file_size)
    logging.info(f"Выбрана самая большая версия: {largest_photo.width}x{largest_photo.height}, размер: {largest_photo.file_size} байт")
    
    try:
        # Генерируем уникальное имя файла
        file_name = f"{uuid.uuid4()}.jpg"
        file_path = os.path.join(photos_dir, file_name)
        
        # Скачиваем файл
        await message.bot.download(
            largest_photo,
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
    photos_count = len(saved_photos)
    await message.answer(
        f"✅ Успешно добавлено фотографий: {photos_count}\n\n"
        f"📸 Всего фотографий в отчете: {len(current_photos)}\n\n"
        f"Вы можете отправить еще фотографии или нажать 'Готово'.",
        reply_markup=keyboard
    )

# Обработчик завершения добавления фотографий
@admin_report_edit_router.callback_query(F.data == "photos_done", ReportStates.add_photos)
@error_handler
@with_session
async def process_photos_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка завершения добавления фотографий"""
    # Получаем данные из состояния
    data = await state.get_data()
    report_id = data.get('report_id')
    
    if not report_id:
        await callback.message.edit_text(
            "❌ Ошибка: не найден ID отчета",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return
    
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

    
    await show_report_edit_page(callback, report_id, session)
    
    # Обновляем состояние
    await state.set_state(ReportStates.edit_report)

# Обработчик добавления комментариев
@admin_report_edit_router.callback_query(F.data == "add_comments")
@error_handler
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
@admin_report_edit_router.message(ReportStates.add_comments)
@error_handler
@with_session
async def process_comments(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка полученных комментариев"""
    # Получаем ID отчета из состояния
    data = await state.get_data()
    report_id = data.get('report_id')
    
    if not report_id:
        await message.answer(
            "❌ Ошибка: не найден ID отчета",
            reply_markup=await get_admin_report_menu_keyboard()
        )
        return

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
    
    
    # Показываем меню действий для редактирования
    await message.answer(
        f"✅ Комментарии успешно сохранены!\n\n{await format_report_info(report, message.text)}\nВыберите действие:",
        reply_markup=await get_report_actions_keyboard(report_id)
    )
    
    # Устанавливаем состояние редактирования
    await state.set_state(ReportStates.edit_report)

# Обработчик возврата к действиям
@admin_report_edit_router.callback_query(F.data == "back_to_actions")
@error_handler
async def process_back_to_actions(callback: CallbackQuery, state: FSMContext):
    """Обработка возврата к действиям"""
    await callback.answer()
    
    # Показываем меню действий для отчета
    await callback.message.edit_text(
        "Выберите действие для продолжения создания отчета:",
        reply_markup=await get_report_actions_keyboard()
    )

# Обработчик сохранения отчета
@admin_report_edit_router.callback_query(F.data == "save_report")
@error_handler
@with_session
async def process_save_report(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
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
        
        # Обновляем статус отчета на "sent" и время отправки
        report_id = data.get('report_id')
        data['status'] = "sent"
        data['sent_at'] = datetime.utcnow()
        
        # Создаем отчет
        logging.info("[process_save_report] Создаем отчет в БД")
        report = await create_report(session, data)
        logging.info(f"[process_save_report] Отчет успешно создан с ID: {report.id}")
        
        # Получаем объект отдельным запросом
        object_query = select(Object).where(Object.id == report.object_id)
        result = await session.execute(object_query)
        object = result.scalar_one_or_none()
        
        # Логируем действие отправки отчета
        log_admin_action("report_sent", callback.from_user.id, f"Отправлен отчет #{report.id} по объекту '{object.name if object else 'Не указан'}'")
        
        # Очищаем состояние
        await state.clear()
        
        # Отправляем сообщение об успешном создании отчета
        await callback.message.edit_text(
            f"✅ Отчет успешно создан и отправлен заказчику!\n\n"
            f"ID отчета: {report.id}\n"
            f"Объект: {object.name if object else 'Не указан'}\n"
            f"Тип работ: {report.report_type}\n"
            f"Время: {report.type}\n"
            f"Статус: отправлен",
            reply_markup=await get_admin_report_menu_keyboard()
        )
    except ValidationError as e:
        logging.error(f"[process_save_report] Ошибка валидации: {e}")
        await callback.message.edit_text(f"Ошибка валидации: {str(e)}")
    except Exception as e:
        logging.error(f"[process_save_report] Общая ошибка: {e}")
        await callback.message.edit_text(f"Произошла ошибка: {str(e)}")

# Обработчик отмены создания отчета
@admin_report_edit_router.callback_query(F.data == "cancel_report")
@error_handler
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

# Функция для валидации данных отчета
async def validate_report_data(data: dict) -> None:
    """Валидация данных отчета"""
    logging.info(f"Начало валидации данных отчета. Полученные данные: {data}")
    
    required_fields = ['object_id', 'report_type', 'itr_list', 'workers_list', 'equipment_list']
    
    # Проверяем наличие всех полей
    for field in required_fields:
        if field not in data:
            error_msg = f"Отсутствует обязательное поле: {field}"
            logging.error(error_msg)
            raise ValueError(error_msg)
        logging.info(f"Поле {field} найдено. Значение: {data[field]}")
    
    # Проверяем корректность значений
    valid_report_types = ['Инженерные коммуникации', 'Внутриплощадочные сети', 'Благоустройство', 'Общестроительные работы']
    if data['report_type'] not in valid_report_types:
        error_msg = "Некорректный тип отчета"
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    if data['type'] not in ['morning', 'evening']:
        error_msg = "Некорректное время суток"
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    logging.info("Валидация данных отчета успешно завершена")


async def show_report_edit_page(message: Union[Message, CallbackQuery], report_id: int, session: AsyncSession) -> None:
    """
    Показывает страницу редактирования отчета
    
    Args:
        message: Сообщение или callback query для редактирования
        report_id: ID отчета
        session: Сессия базы данных
    """
    try:
        # Получаем отчет со всеми связями через get_report_with_relations
        report = await get_report_with_relations(session, report_id)
        if not report:
            if isinstance(message, CallbackQuery):
                await message.message.edit_text(
                    "Отчет не найден",
                    reply_markup=await get_admin_report_menu_keyboard()
                )
            else:
                await message.answer(
                    "Отчет не найден",
                    reply_markup=await get_admin_report_menu_keyboard()
                )
            return
        
        # Получаем объект
        object = report.object
        
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
        
        # Добавляем комментарии, если есть
        if report.comments:
            report_info += f"Комментарий: {report.comments}\n"
        
        # Отправляем сообщение с информацией об отчете
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(
                f"{report_info}\nВыберите действие:",
                reply_markup=await get_report_actions_keyboard(report_id)
            )
        else:
            await message.answer(
                f"{report_info}\nВыберите действие:",
                reply_markup=await get_report_actions_keyboard(report_id)
            )
    except Exception as e:
        logging.error(f"Ошибка при отображении страницы редактирования отчета: {str(e)}", exc_info=True)
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(
                "Произошла ошибка при отображении страницы редактирования.",
                reply_markup=await get_admin_report_menu_keyboard()
            )
        else:
            await message.answer(
                "Произошла ошибка при отображении страницы редактирования.",
                reply_markup=await get_admin_report_menu_keyboard()
            )


async def format_report_info(report: Report, message: str) -> str:
    """Форматирование информации об отчете"""
    # Формируем информацию об отчете

    if report.status == "sent":
        report_info = (
            f"✅ Отчет #{report.id} отправлен заказчику\n\n"
            f"Тип: {report.type}\n"
            f"Дата: {report.date.strftime('%d.%m.%Y %H:%M')}\n"
            f"Статус: {report.status}\n"
            f"Объект: {report.object.name}\n"
        )
    else:
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
    report_info += f"Комментарий: {message}\n"

    return report_info