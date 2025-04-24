from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import os
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from sqlalchemy import select

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
    get_report_with_relations,
    get_all_itr,
    get_all_workers,
    get_all_equipment
)
from construction_report_bot.config.settings import settings

logger = logging.getLogger(__name__)

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

    @staticmethod
    async def export_report(session: AsyncSession, report: Report) -> Optional[str]:
        """
        Экспортирует отчет в PDF формат
        
        Args:
            session: Сессия базы данных
            report: Объект отчета
            
        Returns:
            str: Путь к созданному PDF файлу или None в случае ошибки
        """
        try:
            # Создаем директорию для экспорта если её нет
            export_dir = os.path.join(settings.BASE_DIR, "exports")
            os.makedirs(export_dir, exist_ok=True)
            
            # Формируем имя файла
            filename = f"report_{report.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = os.path.join(export_dir, filename)
            
            # Получаем связанные данные
            object_query = select(Object).where(Object.id == report.object_id)
            result = await session.execute(object_query)
            object = result.scalar_one_or_none()
            
            # Создаем документ
            doc = SimpleDocTemplate(
                filepath,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # Получаем стили
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=30
            )
            
            # Создаем элементы документа
            elements = []
            
            # Заголовок
            elements.append(Paragraph(f"Отчет №{report.id}", title_style))
            elements.append(Spacer(1, 12))
            
            # Основная информация
            data = [
                ["Дата:", report.date.strftime("%d.%m.%Y")],
                ["Тип отчета:", report.type],
                ["Объект:", object.name if object else "Не указан"],
                ["Статус:", report.status]
            ]
            
            # Создаем таблицу
            table = Table(data, colWidths=[2*inch, 4*inch])
            table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
                ('BOTTOMPADDING', (0,0), (-1,-1), 12),
                ('TOPPADDING', (0,0), (-1,-1), 12),
                ('GRID', (0,0), (-1,-1), 1, colors.black)
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 20))
            
            # Описание
            if report.comments:
                elements.append(Paragraph("Комментарии:", styles['Heading2']))
                elements.append(Paragraph(report.comments, styles['Normal']))
                elements.append(Spacer(1, 20))
            
            # Строим документ
            doc.build(elements)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Ошибка при экспорте отчета в PDF: {e}")
            return None
    
    @staticmethod
    async def export_reports(session: AsyncSession, reports: List[Report]) -> Optional[str]:
        """
        Экспортирует список отчетов в Excel файл
        
        Args:
            session: Сессия базы данных
            reports: Список объектов отчетов
            
        Returns:
            str: Путь к созданному файлу или None в случае ошибки
        """
        try:
            # Создаем директорию для экспорта, если её нет
            export_dir = os.path.join(settings.BASE_DIR, "exports")
            os.makedirs(export_dir, exist_ok=True)
            
            # Формируем имя файла
            filename = f"reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            filepath = os.path.join(export_dir, filename)
            
            # Создаем Excel writer
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Сводная информация по всем отчетам
                summary_data = []
                for report in reports:
                    summary_data.append({
                        'ID отчета': report.id,
                        'Дата создания': report.date.strftime('%d.%m.%Y %H:%M'),
                        'Статус': report.status,
                        'Комментарий': report.comments or 'Нет',
                        'Количество фотографий': len(report.photos),
                        'Количество ИТР': len(report.itr_personnel),
                        'Количество рабочих': len(report.workers),
                        'Количество техники': len(report.equipment)
                    })
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Сводка', index=False)
                
                # Детальная информация по каждому отчету
                for report in reports:
                    sheet_name = f'Отчет_{report.id}'
                    
                    # Основная информация
                    main_data = {
                        'Поле': [
                            'ID отчета',
                            'Дата создания',
                            'Статус',
                            'Комментарий',
                            'Количество фотографий',
                            'Количество ИТР',
                            'Количество рабочих',
                            'Количество техники'
                        ],
                        'Значение': [
                            report.id,
                            report.date.strftime('%d.%m.%Y %H:%M'),
                            report.status,
                            report.comments or 'Нет',
                            len(report.photos),
                            len(report.itr_personnel),
                            len(report.workers),
                            len(report.equipment)
                        ]
                    }
                    pd.DataFrame(main_data).to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    # Информация об ИТР
                    if report.itr_personnel:
                        itr_data = []
                        for itr in report.itr_personnel:
                            itr_data.append({
                                'ФИО': itr.full_name
                            })
                        pd.DataFrame(itr_data).to_excel(writer, sheet_name=f'{sheet_name}_ИТР', index=False)
                    
                    # Информация о рабочих
                    if report.workers:
                        worker_data = []
                        for worker in report.workers:
                            worker_data.append({
                                'ФИО': worker.full_name,
                                'Должность': worker.position
                            })
                        pd.DataFrame(worker_data).to_excel(writer, sheet_name=f'{sheet_name}_Рабочие', index=False)
                    
                    # Информация о технике
                    if report.equipment:
                        equipment_data = []
                        for equip in report.equipment:
                            equipment_data.append({
                                'Наименование': equip.name
                            })
                        pd.DataFrame(equipment_data).to_excel(writer, sheet_name=f'{sheet_name}_Техника', index=False)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Ошибка при экспорте отчетов: {str(e)}", exc_info=True)
            return None 