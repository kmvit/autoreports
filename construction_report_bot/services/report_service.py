from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from construction_report_bot.database.models import Report, ReportPhoto, ITR, Worker, Equipment, Object
from construction_report_bot.database.crud import (
    create_report, 
    get_report_by_id, 
    update_report, 
    get_all_reports,
    get_reports_by_object,
    get_reports_by_date,
    get_reports_by_status,
    get_itr_by_id,
    get_worker_by_id,
    get_equipment_by_id,
    get_object_by_id,
    add_report_photo,
    get_report_with_relations
)

class ReportService:
    """Сервис для работы с отчетами"""
    
    @staticmethod
    async def create_new_report(
        session: AsyncSession,
        object_id: int,
        report_type: str,
        work_subtype: Optional[str],
        time_of_day: str,
        comments: Optional[str] = None
    ) -> Report:
        """Создает новый отчет"""
        # Создаем базовый отчет
        report_data = {
            "object_id": object_id,
            "report_type": report_type,
            "work_subtype": work_subtype,
            "type": time_of_day,  # morning / evening
            "comments": comments,
            "status": "draft",
            "date": datetime.utcnow()
        }
        
        # Создаем отчет в БД
        report = await create_report(session, report_data)
        
        return report
    
    @staticmethod
    async def add_itr_to_report(
        session: AsyncSession,
        report_id: int,
        itr_ids: List[int]
    ) -> Report:
        """Добавляет ИТР в отчет"""
        try:
            # Получаем отчет со всеми связанными данными
            report = await get_report_with_relations(session, report_id)
            if not report:
                return None
            
            # Получаем объекты ИТР
            itrs = []
            for itr_id in itr_ids:
                itr = await get_itr_by_id(session, itr_id)
                if itr:
                    itrs.append(itr)
            
            # Добавляем ИТР в отчет
            report.itr_personnel = itrs
            await session.commit()
            await session.refresh(report)
            
            return report
        except Exception as e:
            logging.error(f"Ошибка при добавлении ИТР в отчет: {str(e)}", exc_info=True)
            await session.rollback()
            return None
    
    @staticmethod
    async def add_workers_to_report(
        session: AsyncSession,
        report_id: int,
        worker_ids: List[int]
    ) -> Report:
        """Добавляет рабочих в отчет"""
        # Получаем отчет
        report = await get_report_by_id(session, report_id)
        
        # Получаем объекты рабочих
        workers = []
        for worker_id in worker_ids:
            worker = await session.get(Worker, worker_id)
            if worker:
                workers.append(worker)
        
        # Добавляем рабочих в отчет
        report.workers.extend(workers)
        await session.commit()
        
        return report
    
    @staticmethod
    async def add_equipment_to_report(
        session: AsyncSession,
        report_id: int,
        equipment_data: List[Dict[str, Any]]
    ) -> Report:
        """Добавляет технику в отчет"""
        # Получаем отчет
        report = await get_report_by_id(session, report_id)
        
        # Получаем объекты техники
        equipment_list = []
        for item in equipment_data:
            equipment_id = item.get("equipment_id")
            equipment = await get_equipment_by_id(session, equipment_id)
            if equipment:
                equipment_list.append(equipment)
        
        # Добавляем технику в отчет
        report.equipment = equipment_list
        await session.commit()
        
        return report
    
    @staticmethod
    async def add_photos_to_report(
        session: AsyncSession,
        report_id: int,
        photos_data: List[Dict[str, str]]
    ) -> Report:
        """Добавляет фотографии в отчет"""
        # Получаем отчет
        report = await get_report_by_id(session, report_id)
        
        # Добавляем фотографии в отчет
        for photo in photos_data:
            file_path = photo.get("file_path")
            description = photo.get("description")
            
            report_photo = ReportPhoto(
                report_id=report.id,
                file_path=file_path,
                description=description
            )
            session.add(report_photo)
        
        await session.commit()
        
        return report
    
    @staticmethod
    async def update_report_comments(
        session: AsyncSession,
        report_id: int,
        comments: str
    ) -> Report:
        """Обновляет комментарии к отчету"""
        # Обновляем комментарии
        report = await update_report(session, report_id, {"comments": comments})
        
        return report
    
    @staticmethod
    async def send_report(
        session: AsyncSession,
        report_id: int,
        recipient_id: int
    ) -> bool:
        """Отправляет отчет (меняет статус на sent)"""
        try:
            # Обновляем статус и время отправки
            report = await update_report(
                session, 
                report_id, 
                {
                    "status": "sent",
                    "sent_at": datetime.utcnow(),
                    "recipient_id": recipient_id
                }
            )
            
            return True if report else False
        except Exception as e:
            logging.error(f"Ошибка при отправке отчета: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    async def get_reports_by_filters(
        session: AsyncSession,
        object_id: Optional[int] = None,
        date: Optional[datetime] = None,
        status: Optional[str] = None
    ) -> List[Report]:
        """Получает отчеты по фильтрам"""
        reports = []
        
        if object_id:
            # Получаем отчеты по объекту
            reports = await get_reports_by_object(session, object_id)
        elif date:
            # Получаем отчеты по дате
            reports = await get_reports_by_date(session, date)
        elif status:
            # Получаем отчеты по статусу
            reports = await get_reports_by_status(session, status)
        else:
            # Получаем все отчеты
            reports = await get_all_reports(session)
        
        return reports

    @staticmethod
    async def create_or_update_report(
        session: AsyncSession,
        object_id: int,
        report_type: str,
        itr_id: Optional[int] = None,
        workers_list: Optional[List[int]] = None,
        equipment_list: Optional[List[int]] = None,
        report_id: Optional[int] = None
    ) -> Report:
        """
        Создание или обновление отчета
        """
        try:
            # Подготавливаем данные для отчета
            report_data = {
                'object_id': object_id,
                'report_type': report_type
            }
            
            if report_id:
                report_data['report_id'] = report_id
            
            # Если передан ИТР, добавляем его
            if itr_id:
                report_data['itr_id'] = itr_id
            
            # Если переданы рабочие, добавляем их
            if workers_list:
                report_data['workers_list'] = workers_list
            
            # Если передана техника, добавляем её
            if equipment_list:
                report_data['equipment_list'] = equipment_list
            
            # Создаем или обновляем отчет
            report = await create_report(session, report_data)
            return report
            
        except Exception as e:
            # Логируем ошибку и пробрасываем дальше
            logging.error(f"Ошибка при создании/обновлении отчета: {str(e)}", exc_info=True)
            raise 