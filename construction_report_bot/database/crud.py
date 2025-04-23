from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional, Union, Dict, Any
from datetime import datetime
import logging

from construction_report_bot.database.models import (
    User, Client, Object, ITR, Worker, Equipment, Report, ReportPhoto,
    report_equipment
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
    result = await session.execute(select(Client).where(Client.user_id == user_id))
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
    """Удаление клиента"""
    stmt = delete(Client).where(Client.id == client_id)
    await session.execute(stmt)
    await session.commit()
    return True

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
    """Удаление объекта"""
    stmt = delete(Object).where(Object.id == object_id)
    await session.execute(stmt)
    await session.commit()
    return True

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

async def get_reports_by_object(session: AsyncSession, object_id: int) -> List[Report]:
    """Получение отчетов по объекту"""
    result = await session.execute(select(Report).where(Report.object_id == object_id))
    return result.scalars().all()

async def get_today_reports(session: AsyncSession, object_id: Optional[int] = None) -> List[Report]:
    """Получение отчетов за сегодня, возможно с фильтром по объекту"""
    today = datetime.utcnow().date()
    query = select(Report).where(Report.date >= today)
    
    if object_id:
        query = query.where(Report.object_id == object_id)
    
    result = await session.execute(query)
    return result.scalars().all()

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
    """Удаление отчета"""
    stmt = delete(Report).where(Report.id == report_id)
    await session.execute(stmt)
    await session.commit()
    return True

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
    start_date = datetime(date.year, date.month, date.day, 0, 0, 0)
    end_date = datetime(date.year, date.month, date.day, 23, 59, 59)
    
    result = await session.execute(
        select(Report).where(
            Report.date >= start_date,
            Report.date <= end_date
        ).order_by(Report.date.desc())
    )
    return result.scalars().all()

async def get_reports_by_status(session: AsyncSession, status: str) -> List[Report]:
    """Получение отчетов по статусу"""
    result = await session.execute(
        select(Report).where(Report.status == status).order_by(Report.date.desc())
    )
    return result.scalars().all()

async def get_reports_by_type(session: AsyncSession, report_type: str) -> List[Report]:
    """Получение отчетов по типу"""
    result = await session.execute(
        select(Report).where(Report.type == report_type).order_by(Report.date.desc())
    )
    return result.scalars().all()

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
                selectinload(Report.equipment)
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
        logging.error(f"Ошибка при получении отчета #{report_id}: {str(e)}")
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