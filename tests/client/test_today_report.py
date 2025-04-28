#!/usr/bin/env python
"""
Тест функционала просмотра отчета за сегодня для клиента.
Используется для автоматического тестирования клиентского функционала.

Скрипт симулирует запрос отчетов за сегодня и проверяет корректность обработки.
"""

import os
import sys
import asyncio
import logging
import pytest
from aiogram.types import Message, Chat, User
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, MagicMock, AsyncMock


# Добавляем корневую директорию проекта в PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

# Проверяем, что путь добавлен корректно
if project_root not in sys.path:
    sys.path.append(project_root)
    

from construction_report_bot.database.models import ITR, Equipment, Worker, ReportPhoto, Report
from construction_report_bot.handlers.client import cmd_today_report
from construction_report_bot.database.models import Client, Object, User as DBUser, Report
from construction_report_bot.database.crud import get_today_reports, get_client_by_user_id

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MessageResponse:
    """Класс для хранения ответов бота"""
    def __init__(self):
        self.responses = []
    
    async def answer(self, text, **kwargs):
        """Метод для перехвата ответов от бота"""
        self.responses.append({"text": text, "kwargs": kwargs})
        logger.info(f"Ответ бота: {text}")
        return True

@pytest.mark.asyncio
async def test_cmd_today_report():
    """Тестирует обработчик команды просмотра отчета за сегодня"""
    # Создаем тестовые данные
    # Создаем тестового пользователя
    db_user = DBUser(
        id=999,
        telegram_id=1101434297,
        username="test_user",
        role="client",
        access_code="test_code"
    )
    
    # Создаем тестового клиента
    client = Client(
        id=999,
        user_id=db_user.id,
        full_name="Тестовый Клиент",
        organization="Тестовая Организация",
        contact_info="test@example.com"
    )
    
    # Создаем тестовый объект
    test_object = Object(
        id=999,
        name="Тестовый Объект"
    )
    
    # Связываем клиента с объектом
    client.objects = [test_object]

    # Создаем тестовый отчет на сегодня
    today = datetime.utcnow()
    test_itr_personnel = ITR(id=999, full_name="Тестовый ITR персонал")
    test_worker = Worker(id=999, full_name="Тестовый персонал")
    test_equipment = Equipment(id=999, name="Тестовое оборудование")
    test_photos = ReportPhoto(id=999, file_path="https://example.com/test_photo.jpg")
    
    report = Report(
        object_id=test_object.id,
        date=today,
        type="morning",
        report_type="general_construction",
        work_subtype="foundation",
        comments="Тестовый комментарий",
        itr_personnel=[test_itr_personnel],
        workers=[test_worker],
        equipment=[test_equipment], 
        photos=[test_photos],
        status="sent"
    )
    # Устанавливаем связь с объектом вручную
    report.object = test_object
    
    # Создаем объекты для теста
    user = User(id=db_user.telegram_id, is_bot=False, first_name="Test", username="test_user")
    chat = Chat(id=user.id, type="private")
    message = Message(message_id=1, date=0, chat=chat, from_user=user, text="📑 Отчет за сегодня")
    
    # Перехватываем ответы бота
    message_response = MessageResponse()
    message.answer = message_response.answer
    
    # Создаем моки для функций базы данных
    mock_session = AsyncMock()
    
    # Патчим функции базы данных
    with patch('construction_report_bot.database.crud.get_client_by_user_id', return_value=client), \
         patch('construction_report_bot.database.crud.get_today_reports', return_value=[report]):
        
        # Вызываем обработчик
        logger.info("Вызываем обработчик cmd_today_report")
        await cmd_today_report(message, mock_session, user=db_user)
        
        # Проверяем, что получили ответ
        assert message_response.responses, "Обработчик не вернул ответа"
        
        # Проверяем содержимое ответа
        response_text = message_response.responses[0]["text"]
        logger.info(f"Получен ответ: {response_text}")
        
        # Проверяем, что в ответе содержится информация о тестовом отчете
        assert "Отчет за сегодня" in response_text, "Заголовок отчета отсутствует в ответе"
        assert "Тип: Утренний" in response_text, "Тип отчета отсутствует в ответе"
        assert "Тестовый Объект" in response_text, "Название объекта отсутствует в ответе"
        assert "Комментарии: Тестовый комментарий" in response_text, "Комментарий отсутствует в ответе"
        
        logger.info("Тест успешно пройден!")

if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 