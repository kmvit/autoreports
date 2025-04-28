import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, text, func
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional, Union, Dict, Any
from datetime import datetime

from construction_report_bot.database.models import (
    User, Client, Object, ITR, Worker, Equipment, 
    Report, ReportPhoto, report_equipment, report_itr, report_workers
)
from construction_report_bot.utils.exceptions import DatabaseError

# Операции с пользователями
async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """Получение пользователя по Telegram ID"""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalars().first()

async def get_user_by_access_code(session: AsyncSession, access_code: str) -> Optional[User]:
    """Получение пользователя по коду доступа"""
    result = await session.execute(select(User).where(User.access_code == access_code))
    return result.scalars().first()

async def create_user(session: AsyncSession, user_data: Dict[str, Any]) -> User:
    """Создание нового пользователя"""
    user = User(**user_data)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def update_user(session: AsyncSession, user_id: int, user_data: Dict[str, Any]) -> bool:
    """Обновление данных пользователя"""
    stmt = update(User).where(User.id == user_id).values(**user_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """Получение пользователя по ID"""
    try:
        query = select(User).where(User.id == user_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя по ID {user_id}: {str(e)}")
        return None

# Операции с клиентами
async def get_all_clients(session: AsyncSession) -> List[Client]:
    """Получение списка всех заказчиков с их пользовательскими данными"""
    query = (
        select(Client)
        .join(User)
        .options(joinedload(Client.user))
    )
    result = await session.execute(query)
    return result.scalars().all()

async def get_client_by_id(session: AsyncSession, client_id: int) -> Optional[Client]:
    """Получение клиента по ID"""
    result = await session.execute(select(Client).where(Client.id == client_id).options(joinedload(Client.user)))
    return result.scalars().first()

async def get_client_by_user_id(session: AsyncSession, user_id: int) -> Optional[Client]:
    """Получение клиента по ID пользователя"""
    result = await session.execute(
        select(Client)
        .where(Client.user_id == user_id)
        .options(
            joinedload(Client.objects),
            joinedload(Client.user)
        )
    )
    return result.scalars().first()

async def create_client(session: AsyncSession, client_data: Dict[str, Any]) -> Client:
    """Создание нового клиента"""
    client = Client(**client_data)
    session.add(client)
    await session.commit()
    await session.refresh(client)
    return client

async def update_client(session: AsyncSession, client_id: int, client_data: Dict[str, Any]) -> bool:
    """Обновление данных клиента"""
    stmt = update(Client).where(Client.id == client_id).values(**client_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_client(session: AsyncSession, client_id: int) -> bool:
    """Удаление клиента со всеми связанными данными"""
    try:
        # 1. Получаем клиента со связанными объектами
        client = await get_client_by_id(session, client_id)
        if not client:
            logging.error(f"Клиент с ID {client_id} не найден")
            return False
        
        user_id = client.user_id
        logging.info(f"Начало удаления клиента {client.full_name} (ID: {client_id})")
        
        # 2. Получаем список объектов клиента
        result = await session.execute(
            text("SELECT object_id FROM client_objects WHERE client_id = :client_id"),
            {"client_id": client_id}
        )
        object_ids = [row[0] for row in result.fetchall()]
        logging.info(f"Найдено {len(object_ids)} объектов, связанных с клиентом")
        
        # 3. Для каждого объекта находим и удаляем связанные отчеты
        for object_id in object_ids:
            # Находим отчеты для объекта
            reports_result = await session.execute(
                select(Report).where(Report.object_id == object_id)
            )
            reports = reports_result.scalars().all()
            logging.info(f"Найдено {len(reports)} отчетов для объекта {object_id}")
            
            # Удаляем каждый отчет и его связи
            for report in reports:
                # Сначала удаляем связи отчета
                await delete_report_relations(session, report.id)
                
                # Затем удаляем сам отчет
                await session.execute(
                    delete(Report).where(Report.id == report.id)
                )
                logging.info(f"Удален отчет {report.id}")
        
        # 4. Удаляем связи клиента с объектами
        await session.execute(
            text("DELETE FROM client_objects WHERE client_id = :client_id"),
            {"client_id": client_id}
        )
        logging.info(f"Удалены связи клиента с объектами")
        
        # 5. Удаляем самого клиента
        stmt = delete(Client).where(Client.id == client_id)
        await session.execute(stmt)
        logging.info(f"Удален клиент {client_id}")
        
        # 6. Удаляем связанного пользователя
        if user_id:
            user_stmt = delete(User).where(User.id == user_id)
            await session.execute(user_stmt)
            logging.info(f"Удален пользователь {user_id}, связанный с клиентом")
        
        # 7. Фиксируем транзакцию
        await session.commit()
        logging.info(f"Успешно удален клиент {client_id} со всеми связями")
        return True
    except Exception as e:
        # Откатываем транзакцию в случае ошибки
        await session.rollback()
        logging.error(f"Ошибка при удалении клиента #{client_id}: {str(e)}")
        raise

# Операции с объектами
async def get_all_objects(session: AsyncSession) -> List[Object]:
    """Получение всех объектов"""
    result = await session.execute(select(Object))
    return result.scalars().all()

async def get_object_by_id(session: AsyncSession, object_id: int) -> Optional[Object]:
    """Получение объекта по ID"""
    result = await session.execute(select(Object).where(Object.id == object_id))
    return result.scalars().first()

async def create_object(session: AsyncSession, object_data: Dict[str, Any]) -> Object:
    """Создание нового объекта"""
    object = Object(**object_data)
    session.add(object)
    await session.commit()
    await session.refresh(object)
    return object

async def update_object(session: AsyncSession, object_id: int, object_data: Dict[str, Any]) -> bool:
    """Обновление данных объекта"""
    stmt = update(Object).where(Object.id == object_id).values(**object_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_object(session: AsyncSession, object_id: int) -> bool:
    """Удаление объекта со всеми связанными данными"""
    try:
        # 1. Получаем объект
        object_info = await get_object_by_id(session, object_id)
        if not object_info:
            logging.error(f"Объект с ID {object_id} не найден")
            return False
        
        logging.info(f"Начало удаления объекта {object_info.name} (ID: {object_id})")
        
        # 2. Получаем все отчеты объекта
        reports_result = await session.execute(
            select(Report).where(Report.object_id == object_id)
        )
        reports = reports_result.scalars().all()
        logging.info(f"Найдено {len(reports)} отчетов для объекта {object_id}")
        
        # 3. Удаляем каждый отчет и его связи
        for report in reports:
            # Сначала удаляем связи отчета
            await delete_report_relations(session, report.id)
            
            # Затем удаляем сам отчет
            await session.execute(
                delete(Report).where(Report.id == report.id)
            )
            logging.info(f"Удален отчет {report.id}")
        
        # 4. Удаляем связи объекта с клиентами
        await session.execute(
            text("DELETE FROM client_objects WHERE object_id = :object_id"),
            {"object_id": object_id}
        )
        logging.info(f"Удалены связи объекта с клиентами")
        
        # 5. Удаляем сам объект
        stmt = delete(Object).where(Object.id == object_id)
        await session.execute(stmt)
        logging.info(f"Удален объект {object_id}")
        
        # 6. Фиксируем транзакцию
        await session.commit()
        logging.info(f"Успешно удален объект {object_id} со всеми связями")
        return True
    except Exception as e:
        # Откатываем транзакцию в случае ошибки
        await session.rollback()
        logging.error(f"Ошибка при удалении объекта #{object_id}: {str(e)}")
        raise

# Операции с ИТР
async def get_all_itr(session: AsyncSession) -> List[ITR]:
    """Получение всех ИТР"""
    result = await session.execute(select(ITR))
    return result.scalars().all()

async def get_itr_by_id(session: AsyncSession, itr_id: int) -> Optional[ITR]:
    """Получение ИТР по ID"""
    result = await session.execute(select(ITR).where(ITR.id == itr_id))
    return result.scalars().first()

async def create_itr(session: AsyncSession, itr_data: Dict[str, Any]) -> ITR:
    """Создание нового ИТР"""
    itr = ITR(**itr_data)
    session.add(itr)
    await session.commit()
    await session.refresh(itr)
    return itr

async def update_itr(session: AsyncSession, itr_id: int, itr_data: Dict[str, Any]) -> bool:
    """Обновление данных ИТР"""
    stmt = update(ITR).where(ITR.id == itr_id).values(**itr_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_itr(session: AsyncSession, itr_id: int) -> bool:
    """Удаление ИТР"""
    stmt = delete(ITR).where(ITR.id == itr_id)
    await session.execute(stmt)
    await session.commit()
    return True

# Операции с рабочими
async def get_all_workers(session: AsyncSession) -> List[Worker]:
    """Получение всех рабочих"""
    result = await session.execute(select(Worker))
    return result.scalars().all()

async def get_worker_by_id(session: AsyncSession, worker_id: int) -> Optional[Worker]:
    """Получение рабочего по ID"""
    result = await session.execute(select(Worker).where(Worker.id == worker_id))
    return result.scalars().first()

async def create_worker(session: AsyncSession, worker_data: Dict[str, Any]) -> Worker:
    """Создание нового рабочего"""
    worker = Worker(**worker_data)
    session.add(worker)
    await session.commit()
    await session.refresh(worker)
    return worker

async def update_worker(session: AsyncSession, worker_id: int, worker_data: Dict[str, Any]) -> bool:
    """Обновление данных рабочего"""
    stmt = update(Worker).where(Worker.id == worker_id).values(**worker_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_worker(session: AsyncSession, worker_id: int) -> bool:
    """Удаление рабочего"""
    stmt = delete(Worker).where(Worker.id == worker_id)
    await session.execute(stmt)
    await session.commit()
    return True

# Операции с техникой
async def get_all_equipment(session: AsyncSession) -> List[Equipment]:
    """Получение всей техники"""
    result = await session.execute(select(Equipment))
    return result.scalars().all()

async def get_equipment_by_id(session: AsyncSession, equipment_id: int) -> Optional[Equipment]:
    """Получение техники по ID"""
    result = await session.execute(select(Equipment).where(Equipment.id == equipment_id))
    return result.scalars().first()

async def create_equipment(session: AsyncSession, equipment_data: Dict[str, Any]) -> Equipment:
    """Создание новой техники"""
    equipment = Equipment(**equipment_data)
    session.add(equipment)
    await session.commit()
    await session.refresh(equipment)
    return equipment

async def update_equipment(session: AsyncSession, equipment_id: int, equipment_data: Dict[str, Any]) -> bool:
    """Обновление данных техники"""
    stmt = update(Equipment).where(Equipment.id == equipment_id).values(**equipment_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_equipment(session: AsyncSession, equipment_id: int) -> bool:
    """Удаление техники"""
    stmt = delete(Equipment).where(Equipment.id == equipment_id)
    await session.execute(stmt)
    await session.commit()
    return True

# Операции с отчетами
async def get_report_by_id(session: AsyncSession, report_id: int) -> Optional[Report]:
    """Получение отчета по ID"""
    result = await session.execute(select(Report).where(Report.id == report_id))
    return result.scalars().first()

async def get_reports_by_object(session: AsyncSession, object_id: int, user_id: Optional[int] = None) -> List[Report]:
    """Получение отчетов по объекту"""
    query = select(Report).where(
        Report.object_id == object_id
    ).order_by(Report.date.desc())
    
    # Включаем связанные данные
    query = query.options(
        joinedload(Report.object),
        joinedload(Report.itr_personnel),
        joinedload(Report.workers),
        joinedload(Report.equipment)
    )
    
    result = await session.execute(query)
    return result.unique().scalars().all()

async def get_today_reports(session: AsyncSession, object_id: Optional[int] = None) -> List[Report]:
    """Получение отчетов за сегодня, возможно с фильтром по объекту"""
    # Получаем начало и конец сегодняшнего дня
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Строим запрос с фильтрацией по текущей дате
    query = select(Report).where(Report.date.between(today, end_of_day))
    
    if object_id:
        query = query.where(Report.object_id == object_id)
    
    # Включаем связанные данные
    query = query.options(
        joinedload(Report.object),
        joinedload(Report.itr_personnel),
        joinedload(Report.workers),
        joinedload(Report.equipment)
    )
    
    result = await session.execute(query)
    return result.unique().scalars().all()

async def create_report(session: AsyncSession, data: dict) -> Report:
    """Создание или обновление отчета"""
    try:
        # Если передан ID отчета, пытаемся найти существующий отчет
        if 'report_id' in data:
            report = await get_report_by_id(session, data['report_id'])
            if report:
                # Обновляем существующий отчет
                for key, value in data.items():
                    if key != 'report_id' and hasattr(report, key):
                        setattr(report, key, value)
                
                # Обновляем связи с ИТР
                if 'itr_id' in data:
                    # Получаем ИТР
                    itr = await get_itr_by_id(session, data['itr_id'])
                    if itr:
                        # Очищаем существующие связи с ИТР
                        report.itr_personnel = []
                        # Добавляем нового ИТР
                        report.itr_personnel.append(itr)
                        await session.flush()
                
                # Обновляем связи с техникой
                if 'equipment_list' in data:
                    # Удаляем все существующие связи с техникой
                    await session.execute(
                        delete(report_equipment).where(report_equipment.c.report_id == report.id)
                    )
                    
                    # Добавляем новые связи с техникой
                    for equipment_id in data['equipment_list']:
                        await session.execute(
                            report_equipment.insert().values(
                                report_id=report.id,
                                equipment_id=equipment_id
                            )
                        )
                    
                    await session.flush()
                
                await session.commit()
                await session.refresh(report)
                return report
        
        # Создаем новый отчет
        report = Report()
        
        # Устанавливаем базовые поля
        for key, value in data.items():
            if key not in ['report_id', 'itr_id', 'workers_list', 'equipment_list'] and hasattr(report, key):
                setattr(report, key, value)
        
        # Добавляем ИТР
        if 'itr_id' in data:
            itr = await get_itr_by_id(session, data['itr_id'])
            if itr:
                report.itr_personnel = [itr]
        
        # Добавляем рабочих
        if 'workers_list' in data:
            logging.info(f"Добавление рабочих к новому отчету")
            workers = []
            for worker_id in data['workers_list']:
                worker = await get_worker_by_id(session, worker_id)
                if worker:
                    workers.append(worker)
            report.workers = workers
        
        session.add(report)
        await session.flush()
        
        # Добавляем технику после создания отчета
        if 'equipment_list' in data:
            for equipment_id in data['equipment_list']:
                await session.execute(
                    report_equipment.insert().values(
                        report_id=report.id,
                        equipment_id=equipment_id
                    )
                )
            await session.flush()
        
        await session.commit()
        await session.refresh(report)
        logging.info(f"Создан/обновлен отчет #{report.id}")
        return report
        
    except Exception as e:
        logging.error(f"Ошибка при создании/обновлении отчета: {str(e)}", exc_info=True)
        await session.rollback()
        raise

async def update_report(session: AsyncSession, report_id: int, report_data: Dict[str, Any]) -> bool:
    """Обновление данных отчета"""
    stmt = update(Report).where(Report.id == report_id).values(**report_data)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_report(session: AsyncSession, report_id: int) -> bool:
    """Удаление отчета со всеми связями"""
    try:
        # 1. Получаем отчет для логирования
        report = await get_report_by_id(session, report_id)
        if not report:
            logging.error(f"Отчет с ID {report_id} не найден")
            return False
            
        logging.info(f"Начало удаления отчета {report_id}")
        
        # 2. Удаляем все связи отчета
        await delete_report_relations(session, report_id)
        logging.info(f"Удалены все связи отчета {report_id}")
        
        # 3. Удаляем сам отчет
        stmt = delete(Report).where(Report.id == report_id)
        await session.execute(stmt)
        logging.info(f"Удален отчет {report_id}")
        
        # 4. Фиксируем транзакцию
        await session.commit()
        logging.info(f"Успешно удален отчет {report_id} со всеми связями")
        return True
    except Exception as e:
        # Откатываем транзакцию в случае ошибки
        await session.rollback()
        logging.error(f"Ошибка при удалении отчета #{report_id}: {str(e)}")
        raise

async def delete_report_relations(session: AsyncSession, report_id: int) -> bool:
    """Удаление всех связей отчета с другими таблицами"""
    try:
        # Удаляем связи с техникой
        await session.execute(
            delete(report_equipment).where(report_equipment.c.report_id == report_id)
        )
        
        # Удаляем связи с ИТР
        await session.execute(
            delete(report_itr).where(report_itr.c.report_id == report_id)
        )
        
        # Удаляем связи с рабочими
        await session.execute(
            delete(report_workers).where(report_workers.c.report_id == report_id)
        )
        
        # Удаляем фотографии отчета
        await session.execute(
            delete(ReportPhoto).where(ReportPhoto.report_id == report_id)
        )
        
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при удалении связей отчета #{report_id}: {str(e)}")
        raise

# Операции с фотографиями отчетов
async def add_report_photo(session: AsyncSession, report_id: int, file_path: str, description: Optional[str] = None) -> ReportPhoto:
    """Добавление фотографии к отчету"""
    photo = ReportPhoto(report_id=report_id, file_path=file_path, description=description)
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return photo

async def delete_report_photo(session: AsyncSession, photo_id: int) -> bool:
    """Удаление фотографии отчета"""
    stmt = delete(ReportPhoto).where(ReportPhoto.id == photo_id)
    await session.execute(stmt)
    await session.commit()
    return True

# Дополнительные операции с отчетами
async def get_all_reports(session: AsyncSession, user_id: Optional[int] = None) -> List[Report]:
    """Получение всех отчетов"""
    query = select(Report)
    
    query = query.order_by(Report.date.desc())
    result = await session.execute(query)
    return result.scalars().all()

async def get_reports_by_date(session: AsyncSession, date: datetime) -> List[Report]:
    """Получение отчетов по дате"""
    query = (
        select(Report)
        .options(
            joinedload(Report.object),
            joinedload(Report.itr_personnel),
            joinedload(Report.workers),
            joinedload(Report.equipment)
        )
        .where(func.date(Report.date) == func.date(date))
        .order_by(Report.date.desc())
    )
    
    result = await session.execute(query)
    return list(result.scalars().unique())

async def get_reports_by_status(session: AsyncSession, status: str) -> List[Report]:
    """Получение отчетов по статусу"""
    result = await session.execute(
        select(Report).where(Report.status == status).order_by(Report.date.desc())
    )
    return result.scalars().all()

async def get_reports_by_type(session: AsyncSession, report_type: str, user_id: Optional[int] = None) -> List[Report]:
    """Получение отчетов по типу (Утро/Вечер)"""
    query = select(Report).where(
        Report.type == report_type
    ).order_by(Report.date.desc())
    
    # Включаем связанные данные
    query = query.options(
        joinedload(Report.object),
        joinedload(Report.itr_personnel),
        joinedload(Report.workers),
        joinedload(Report.equipment)
    )
    
    result = await session.execute(query)
    return result.unique().scalars().all()

async def get_reports_by_work_type(session: AsyncSession, report_type: str, work_subtype: Optional[str] = None) -> List[Report]:
    """Получение отчетов по типу работ и подтипу"""
    query = select(Report).where(Report.report_type == report_type)
    
    if work_subtype:
        query = query.where(Report.work_subtype == work_subtype)
    
    query = query.order_by(Report.date.desc())
    result = await session.execute(query)
    return result.scalars().all()

async def create_base_report(session: AsyncSession, data: dict) -> Report:
    """Создание базового отчета с минимальными данными"""
    try:
        # Создаем новый отчет
        report = Report(
            object_id=data['object_id'],
            date=datetime.now(),
            type=data['report_type'],  # тип отчета (утренний/вечерний)
            report_type=data.get('work_type', 'general_construction'),  # тип работ
            status='draft'  # Статус черновика
        )
        
        # Добавляем отчет в сессию
        session.add(report)
        await session.commit()
        await session.refresh(report)
        
        return report
    except Exception as e:
        await session.rollback()
        raise DatabaseError(f"Ошибка при создании базового отчета: {str(e)}")

async def get_report_with_relations(session: AsyncSession, report_id: int) -> Optional[Report]:
    """Получить отчет со всеми связанными данными"""
    try:
        logging.info(f"Попытка получить отчет #{report_id} со связанными данными")
        
        # Создаем запрос с загрузкой всех связанных данных
        query = (
            select(Report)
            .options(
                selectinload(Report.object),
                selectinload(Report.itr_personnel),
                selectinload(Report.workers),
                selectinload(Report.equipment),
                selectinload(Report.photos)
            )
            .where(Report.id == report_id)
        )
        
        # Выполняем запрос
        result = await session.execute(query)
        report = result.scalar_one_or_none()
        
        if report:
            logging.info(f"Отчет #{report_id} успешно получен")
        else:
            logging.warning(f"Отчет #{report_id} не найден")
        
        return report
    except Exception as e:
        logging.error(f"Ошибка при получении отчета #{report_id}: {str(e)}", exc_info=True)
        return None

async def get_reports_for_export(session: AsyncSession) -> List[Report]:
    """Получение отчетов со всеми необходимыми связями для экспорта"""
    query = (
        select(Report)
        .options(
            joinedload(Report.object),
            joinedload(Report.itr_personnel),
            joinedload(Report.workers),
            joinedload(Report.equipment),
            joinedload(Report.photos)
        )
        .order_by(Report.date.desc())
    )
    result = await session.execute(query)
    return result.scalars().unique().all()

async def get_reports_by_date_range(session: AsyncSession, start_date: datetime, end_date: datetime) -> List[Report]:
    """
    Получение отчетов за период
    
    Args:
        session: Сессия базы данных
        start_date: Начальная дата периода
        end_date: Конечная дата периода
        
    Returns:
        List[Report]: Список отчетов за период
    """
    try:
        query = (
            select(Report)
            .where(Report.date >= start_date)
            .where(Report.date <= end_date)
            .order_by(Report.date.desc())
        )
        result = await session.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Ошибка при получении отчетов за период {start_date} - {end_date}: {str(e)}")
        return []

async def get_reports_by_itr(session: AsyncSession, itr_id: int, user_id: Optional[int] = None) -> List[Report]:
    """Получение отчетов по ИТР"""
    query = select(Report).join(
        Report.itr_personnel
    ).where(
        Report.itr_personnel.any(id=itr_id)
    ).order_by(Report.date.desc())
    
    # Включаем связанные данные
    query = query.options(
        joinedload(Report.object),
        joinedload(Report.itr_personnel),
        joinedload(Report.workers),
        joinedload(Report.equipment)
    )
    
    result = await session.execute(query)
    return result.unique().scalars().all() 