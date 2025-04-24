from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from construction_report_bot.database.models import Report, Client, Object
from construction_report_bot.utils.exceptions import ValidationError

def validate_date_range(date_str: str) -> tuple[datetime, datetime]:
    """Валидация диапазона дат"""
    try:
        start_date_str, end_date_str = date_str.split("-")
        start_date = datetime.strptime(start_date_str.strip(), "%d.%m.%Y")
        end_date = datetime.strptime(end_date_str.strip(), "%d.%m.%Y")
        
        if start_date > end_date:
            raise ValidationError("Начальная дата не может быть позже конечной")
            
        return start_date, end_date
    except ValueError:
        raise ValidationError("Неверный формат даты. Используйте формат ДД.ММ.ГГГГ-ДД.ММ.ГГГГ")

async def get_reports_by_date_range(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    client_id: Optional[int] = None,
    object_id: Optional[int] = None
) -> List[Report]:
    """Получение отчетов за период с опциональной фильтрацией"""
    query = select(Report).where(
        Report.date.between(start_date, end_date)
    )
    
    if client_id:
        query = query.where(Report.client_id == client_id)
    if object_id:
        query = query.where(Report.object_id == object_id)
        
    result = await session.execute(query)
    return result.scalars().all()

async def generate_report_summary(
    session: AsyncSession,
    reports: List[Report]
) -> Dict[str, Any]:
    """Генерация сводки по отчетам"""
    total_reports = len(reports)
    clients = set()
    objects = set()
    
    for report in reports:
        clients.add(report.client_id)
        objects.add(report.object_id)
    
    return {
        "total_reports": total_reports,
        "unique_clients": len(clients),
        "unique_objects": len(objects),
        "period_start": min(r.date for r in reports),
        "period_end": max(r.date for r in reports)
    }

async def format_report_message(
    session: AsyncSession,
    report_type: str,
    filter_type: str,
    summary: Dict[str, Any]
) -> str:
    """Форматирование сообщения с отчетом"""
    message = f"📊 Отчет по типу: {report_type}\n"
    message += f"Фильтр: {filter_type}\n\n"
    
    message += f"Всего отчетов: {summary['total_reports']}\n"
    message += f"Уникальных клиентов: {summary['unique_clients']}\n"
    message += f"Уникальных объектов: {summary['unique_objects']}\n"
    message += f"Период: {summary['period_start'].strftime('%d.%m.%Y')} - {summary['period_end'].strftime('%d.%m.%Y')}\n"
    
    return message 