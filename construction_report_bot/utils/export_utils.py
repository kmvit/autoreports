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

# Получаем путь к директории с шрифтами
FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')
ARIAL_FONT_PATH = os.path.join(FONTS_DIR, 'arialmt.ttf')

# Регистрируем шрифт для поддержки кириллицы
FONT_NAME = 'Arial'
try:
    pdfmetrics.registerFont(TTFont(FONT_NAME, ARIAL_FONT_PATH))
except Exception as e:
    print(f"Ошибка при загрузке шрифта Arial: {e}")
    # Используем Times-Roman как запасной вариант
    FONT_NAME = 'Times-Roman'

# Словарь с русскими названиями типов работ
WORK_TYPE_NAMES = {
    "report_engineering": "Инженерные коммуникации",
    "report_internal_networks": "Внутриплощадочные сети",
    "report_landscaping": "Благоустройство",
    "report_general_construction": "Общестроительные работы"
}

# Словарь с русскими названиями подтипов работ
WORK_SUBTYPE_NAMES = {
    # Инженерные коммуникации
    "subtype_heating": "Отопление",
    "subtype_water": "Водоснабжение и канализация",
    "subtype_fire": "Пожаротушение",
    "subtype_ventilation": "Вентиляция и кондиционирование",
    "subtype_electricity": "Электроснабжение",
    "subtype_low_current": "Слаботочные системы",
    "subtype_sandwich_panels": "Монтаж стеновых сэндвич-панелей",
    "subtype_metal_structures": "Устройство металлоконструкций",
    
    # Внутриплощадочные сети
    "subtype_nwc": "НВК",
    "subtype_gnb": "Работы с ГНБ",
    "subtype_es": "ЭС",
    "subtype_main_pipe_219": "Монтаж магистральной трубы ду 219",
    "subtype_aupt_day": "АУПТ день",
    "subtype_aupt_night": "АУПТ ночь",
    "subtype_lighting_cable_day": "Устройство кабельных трасс освещения день",
    "subtype_lighting_cable_night": "Устройство кабельных трасс освещения ночь",
    
    # Общестроительные работы
    "subtype_monolithic_concrete_floors": "Устройство монолитных ЖБ полов",
    "subtype_monolith": "Монолит",
    "subtype_excavation": "Устройство котлована",
    "subtype_dismantling": "Демонтажные работы",
    "subtype_masonry": "Кладочные работы",
    "subtype_facade": "Фасадные работы",
    "subtype_roofing": "Кровельные работы",
    "subtype_finishing": "Отделочные работы",
    "subtype_construction_site_support": "Обеспечение строительной площадки",
    
    # Благоустройство
    "subtype_territory_improvement": "Благоустройство территории",
    "subtype_landscaping": "Озеленение",
    "subtype_paths": "Устройство дорожек",
    "subtype_platforms": "Устройство площадок",
    "subtype_fencing": "Устройство ограждений",
    "subtype_maf": "Устройство малых архитектурных форм"
}

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
    
    # Получаем доступную ширину страницы (ширина A4 минус отступы)
    available_width = A4[0] - doc.leftMargin - doc.rightMargin
    
    # Создаем стили
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=FONT_NAME,
        fontSize=16,
        spaceAfter=30
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=FONT_NAME,
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
        elements.append(Paragraph(f"Дата: {report.date.strftime('%d.%m.%Y')}", normal_style))
        # Преобразуем тип отчета в русский
        report_type_display = "Утренний" if report.type == "morning" else "Вечерний"
        elements.append(Paragraph(f"Тип: {report_type_display}", normal_style))
        
        # Преобразуем тип работ в русский
        work_type_display = WORK_TYPE_NAMES.get(report.report_type, report.report_type)
        elements.append(Paragraph(f"Тип работ: {work_type_display}", normal_style))
        
        if report.work_subtype:
            # Преобразуем подтип в русский язык
            work_subtype_display = WORK_SUBTYPE_NAMES.get(f"subtype_{report.work_subtype}", report.work_subtype)
            elements.append(Paragraph(f"Подтип работ: {work_subtype_display}", normal_style))
        
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
                    # Создаем изображение с фиксированной шириной 300 пикселей
                    img = Image(photo.file_path)
                    # Устанавливаем фиксированную ширину 300 пикселей
                    img.drawWidth = 300
                    # Сохраняем пропорции изображения
                    img.drawHeight = img.imageHeight * (300 / img.imageWidth)
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
        # Преобразуем подтип в русский язык
        work_subtype_display = WORK_SUBTYPE_NAMES.get(f"subtype_{report.work_subtype}", report.work_subtype) if report.work_subtype else ''
        
        row = {
            'Дата': report.date.strftime('%d.%m.%Y %H:%M'),
            'Объект': report.object.name,
            'Тип': "Утренний" if report.type == "morning" else "Вечерний",
            'Тип работ': report.report_type,
            'Подтип работ': work_subtype_display,
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