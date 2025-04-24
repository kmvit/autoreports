import os
import pandas as pd
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from typing import List, Union, Dict, Any

from construction_report_bot.models.report import Report

async def export_reports(session: AsyncSession, reports: List[Report], format: str) -> str:
    """
    Экспортирует отчеты в указанном формате
    
    Args:
        session: Сессия базы данных
        reports: Список отчетов для экспорта
        format: Формат экспорта ('excel' или 'pdf')
        
    Returns:
        str: Путь к созданному файлу
    """
    # Создаем директорию для экспорта, если её нет
    export_dir = "exports"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    # Генерируем имя файла
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reports_export_{timestamp}"
    
    if format.lower() == "excel":
        return await _export_to_excel(reports, export_dir, filename)
    elif format.lower() == "pdf":
        return await _export_to_pdf(reports, export_dir, filename)
    else:
        raise ValueError(f"Неподдерживаемый формат экспорта: {format}")

async def _export_to_excel(reports: List[Report], export_dir: str, filename: str) -> str:
    """Экспорт отчетов в Excel"""
    file_path = os.path.join(export_dir, f"{filename}.xlsx")
    
    # Создаем DataFrame из отчетов
    data = []
    for report in reports:
        data.append({
            'ID': report.id,
            'Дата': report.date.strftime("%Y-%m-%d %H:%M:%S"),
            'Статус': report.status,
            'Тип': report.type,
            'Описание': report.description,
            'Местоположение': report.location,
            'Ответственный': report.responsible_person
        })
    
    df = pd.DataFrame(data)
    
    # Сохраняем в Excel
    df.to_excel(file_path, index=False)
    
    return file_path

async def _export_to_pdf(reports: List[Report], export_dir: str, filename: str) -> str:
    """Экспорт отчетов в PDF"""
    file_path = os.path.join(export_dir, f"{filename}.pdf")
    
    # Создаем PDF документ
    doc = SimpleDocTemplate(file_path, pagesize=letter)
    elements = []
    
    # Подготавливаем данные для таблицы
    data = [['ID', 'Дата', 'Статус', 'Тип', 'Описание', 'Местоположение', 'Ответственный']]
    for report in reports:
        data.append([
            str(report.id),
            report.date.strftime("%Y-%m-%d %H:%M:%S"),
            report.status,
            report.type,
            report.description,
            report.location,
            report.responsible_person
        ])
    
    # Создаем таблицу
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    return file_path

def format_report_data(report: Report) -> Dict[str, Any]:
    """Форматирование данных отчета для экспорта"""
    return {
        'ID': report.id,
        'Объект': report.object.name,
        'Тип': report.type,
        'Тип работ': report.report_type,
        'Подтип работ': report.work_subtype or 'Не указан',
        'Статус': report.status,
        'Дата': report.date.strftime("%Y-%m-%d %H:%M:%S"),
        'Комментарии': report.comments or 'Нет',
        'ИТР': ', '.join([itr.full_name for itr in report.itr_personnel]) or 'Не указаны',
        'Рабочие': ', '.join([worker.full_name for worker in report.workers]) or 'Не указаны',
        'Техника': ', '.join([equipment.name for equipment in report.equipment]) or 'Не указана'
    }

def format_reports_data(reports: List[Report]) -> List[Dict[str, Any]]:
    """Форматирование данных списка отчетов для экспорта"""
    return [{
        'ID': report.id,
        'Объект': report.object.name,
        'Тип': report.type,
        'Тип работ': report.report_type,
        'Подтип работ': report.work_subtype or 'Не указан',
        'Статус': report.status,
        'Дата': report.date.strftime("%Y-%m-%d %H:%M:%S"),
        'Комментарии': report.comments or 'Нет',
        'ИТР': ', '.join([itr.full_name for itr in report.itr_personnel]) or 'Не указаны',
        'Рабочие': ', '.join([worker.full_name for worker in report.workers]) or 'Не указаны',
        'Техника': ', '.join([equipment.name for equipment in report.equipment]) or 'Не указана'
    } for report in reports] 