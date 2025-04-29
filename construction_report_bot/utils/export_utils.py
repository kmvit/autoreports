from typing import List, Optional
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pandas as pd

from construction_report_bot.database.models import Report
from construction_report_bot.config.settings import settings

# Регистрируем шрифт для поддержки кириллицы
pdfmetrics.registerFont(TTFont('Arial', 'Arial.ttf'))

def safe_parse_date(date_str: str) -> datetime:
    """Безопасное преобразование строки даты в объект datetime"""
    formats = [
        '%Y-%m-%d',
        '%d.%m.%Y',
        '%Y%m%d',
        '%d/%m/%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Если ни один формат не подошел, возвращаем текущую дату
    return datetime.now()

def export_report_to_pdf(reports: List[Report], output_path: str) -> str:
    """Экспорт отчетов в PDF"""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Создаем стили
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName='Arial',
        fontSize=16,
        spaceAfter=30
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Arial',
        fontSize=12,
        spaceAfter=12
    )
    
    # Формируем элементы документа
    elements = []
    
    # Добавляем заголовок с названием объекта и датой
    if reports and reports[0].object:
        report_date = reports[0].date
        title = Paragraph(f"Отчет по объекту '{reports[0].object.name}' за {report_date.strftime('%d.%m.%Y')}", title_style)
    else:
        title = Paragraph(f"Отчет по строительным работам от {datetime.now().strftime('%d.%m.%Y')}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    for report in reports:
        # Основная информация об отчете
        elements.append(Paragraph(f"Дата: {report.date.strftime('%d.%m.%Y %H:%M')}", normal_style))
        elements.append(Paragraph(f"Тип: {report.type}", normal_style))
        elements.append(Paragraph(f"Тип работ: {report.report_type}", normal_style))
        
        if report.work_subtype:
            elements.append(Paragraph(f"Подтип работ: {report.work_subtype}", normal_style))
        
        # ИТР
        if report.itr_personnel:
            itr_names = [itr.full_name for itr in report.itr_personnel]
            elements.append(Paragraph(f"ИТР: {', '.join(itr_names)}", normal_style))
        
        # Рабочие
        if report.workers:
            worker_names = [worker.full_name for worker in report.workers]
            elements.append(Paragraph(f"Рабочие: {', '.join(worker_names)}", normal_style))
        
        # Техника
        if report.equipment:
            equipment_names = [eq.name for eq in report.equipment]
            elements.append(Paragraph(f"Техника: {', '.join(equipment_names)}", normal_style))
        
        # Комментарии
        if report.comments:
            elements.append(Paragraph(f"Комментарии: {report.comments}", normal_style))
        
        # Фотографии
        if report.photos:
            elements.append(Paragraph("Фотографии:", normal_style))
            for photo in report.photos:
                if os.path.exists(photo.file_path):
                    img = Image(photo.file_path, width=400, height=300)
                    elements.append(img)
                    if photo.description:
                        elements.append(Paragraph(f"Описание: {photo.description}", normal_style))
                    elements.append(Spacer(1, 12))
        
        elements.append(Spacer(1, 20))
    
    # Создаем документ
    doc.build(elements)
    return output_path

def export_report_to_excel(reports: List[Report], output_path: str) -> str:
    """Экспорт отчетов в Excel"""
    # Подготавливаем данные для Excel
    data = []
    for report in reports:
        row = {
            'Дата': report.date.strftime('%d.%m.%Y %H:%M'),
            'Объект': report.object.name,
            'Тип': report.type,
            'Тип работ': report.report_type,
            'Подтип работ': report.work_subtype or '',
            'ИТР': ', '.join([itr.full_name for itr in report.itr_personnel]) if report.itr_personnel else '',
            'Рабочие': ', '.join([w.full_name for w in report.workers]) if report.workers else '',
            'Техника': ', '.join([eq.name for eq in report.equipment]) if report.equipment else '',
            'Комментарии': report.comments or '',
            'Количество фото': len(report.photos) if report.photos else 0,
            'Статус': report.status
        }
        data.append(row)
    
    # Создаем DataFrame
    df = pd.DataFrame(data)
    
    # Сохраняем в Excel
    writer = pd.ExcelWriter(output_path, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='Отчеты')
    
    # Автоматически регулируем ширину столбцов
    worksheet = writer.sheets['Отчеты']
    for idx, col in enumerate(df.columns):
        max_length = max(
            df[col].astype(str).apply(len).max(),
            len(col)
        )
        worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2
    
    writer.close()
    return output_path 