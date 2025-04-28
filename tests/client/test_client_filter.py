#!/usr/bin/env python
"""
Тест функционала фильтрации отчетов по объекту для клиента.
Используется для автоматического тестирования клиентского функционала.

Скрипт симулирует callback запрос фильтрации по объекту и проверяет корректность обработки.
"""

import os
import sys
import asyncio
import logging
from aiogram.types import CallbackQuery, Message, Chat, User
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime


# Добавляем корневую директорию проекта в PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

# Проверяем, что путь добавлен корректно
if project_root not in sys.path:
    sys.path.append(project_root)

from construction_report_bot.handlers.client import process_filter_object
from construction_report_bot.database.models import Client, Object, User as DBUser, Report
from construction_report_bot.database.session import get_session
from construction_report_bot.states.client_states import ReportFilterStates

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MessageResponse:
    """Класс для перехвата ответов бота"""
    def __init__(self):
        self.responses = []
        self.edited_messages = []
    
    async def answer(self, text="", **kwargs):
        """Метод для перехвата ответов от бота"""
        self.responses.append({"text": text, "kwargs": kwargs})
        logger.info(f"Ответ бота: {text}")
        return True
    
    async def edit_text(self, text, **kwargs):
        """Метод для перехвата edit_text от бота"""
        self.edited_messages.append({"text": text, "kwargs": kwargs})
        logger.info(f"Отредактировано сообщение: {text}")
        return True

async def setup_test_data(session):
    """Создает тестовые данные для проверки"""
    try:
        # Создаем тестового пользователя
        db_user = DBUser(
            id=999,
            telegram_id=1101434297,
            username="test_user",
            role="client",
            access_code="test_code"
        )
        session.add(db_user)
        await session.flush()
        
        # Создаем тестового клиента
        client = Client(
            id=999,
            user_id=db_user.id,
            full_name="Тестовый Клиент",
            organization="Тестовая Организация",
            contact_info="test@example.com"
        )
        session.add(client)
        await session.flush()
        
        # Создаем два тестовых объекта
        test_object1 = Object(
            id=998,
            name="Тестовый Объект 1"
        )
        session.add(test_object1)
        
        test_object2 = Object(
            id=999,
            name="Тестовый Объект 2"
        )
        session.add(test_object2)
        await session.flush()
        
        # Связываем клиента с объектами
        client.objects = [test_object1, test_object2]
        
        # Создаем тестовый отчет для первого объекта
        today = datetime.utcnow()
        report1 = Report(
            object_id=test_object1.id,
            date=today,
            type="morning",
            report_type="general_construction",
            work_subtype="foundation",
            comments="Тестовый комментарий 1",
            status="sent"
        )
        session.add(report1)
        
        # Создаем тестовый отчет для второго объекта
        report2 = Report(
            object_id=test_object2.id,
            date=today,
            type="evening",
            report_type="finishing",
            work_subtype="painting",
            comments="Тестовый комментарий 2",
            status="sent"
        )
        session.add(report2)
        
        await session.commit()
        logger.info("Тестовые данные успешно созданы")
        return db_user, client, [test_object1, test_object2], [report1, report2]
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при создании тестовых данных: {e}")
        raise

async def cleanup_test_data(session):
    """Удаляет тестовые данные"""
    try:
        # Удаляем тестовые отчеты
        await session.execute("DELETE FROM reports WHERE object_id IN (998, 999)")
        
        # Удаляем связь клиента с объектами
        await session.execute("DELETE FROM client_objects WHERE client_id = 999")
        
        # Удаляем тестовые объекты
        await session.execute("DELETE FROM objects WHERE id IN (998, 999)")
        
        # Удаляем тестового клиента
        await session.execute("DELETE FROM clients WHERE id = 999")
        
        # Удаляем тестового пользователя
        await session.execute("DELETE FROM users WHERE id = 999")
        
        await session.commit()
        logger.info("Тестовые данные успешно удалены")
    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при удалении тестовых данных: {e}")

async def test_process_filter_object():
    """Тестирует обработчик фильтрации по объекту"""
    # Получаем сессию БД
    session_gen = get_session()
    session = await anext(session_gen)
    
    try:
        # Создаем тестовые данные
        db_user, client, objects, reports = await setup_test_data(session)
        
        # Создаем объекты для теста
        user = User(id=db_user.telegram_id, is_bot=False, first_name="Test", username="test_user")
        chat = Chat(id=user.id, type="private")
        message = Message(message_id=1, date=0, chat=chat, from_user=user)
        
        # Создаем callback query
        callback_query = CallbackQuery(
            id="test_callback_id",
            from_user=user,
            chat_instance="test_chat_instance",
            data="filter_object",
            message=message
        )
        
        # Перехватываем ответы бота
        message_response = MessageResponse()
        callback_query.answer = message_response.answer
        message.edit_text = message_response.edit_text
        
        # Создаем FSM контекст
        storage = MemoryStorage()
        state = FSMContext(storage, user.id, chat.id)
        
        # Вызываем обработчик
        logger.info("Вызываем обработчик process_filter_object")
        await process_filter_object(callback_query, state, session, user=db_user)
        
        # Проверяем, что получили ответ
        if not message_response.edited_messages:
            logger.error("Обработчик не отредактировал сообщение")
            return False
        
        # Проверяем содержимое ответа
        response_text = message_response.edited_messages[0]["text"]
        logger.info(f"Получен ответ: {response_text}")
        
        # Проверяем, что в ответе содержится информация о тестовых объектах
        expected_text = "Выберите объект"
        if expected_text not in response_text:
            logger.error(f"Ожидаемый текст '{expected_text}' не найден в ответе")
            return False
        
        # Проверяем, что в ответе есть оба тестовых объекта
        object1_name = "Тестовый Объект 1"
        if object1_name not in response_text:
            logger.error(f"Название объекта '{object1_name}' не найдено в ответе")
            return False
            
        object2_name = "Тестовый Объект 2"
        if object2_name not in response_text:
            logger.error(f"Название объекта '{object2_name}' не найдено в ответе")
            return False
        
        # Проверяем, что состояние установлено правильно
        state_data = await state.get_data()
        if not state_data.get("objects"):
            logger.error("Не установлены данные объектов в состоянии")
            return False
        
        current_state = await state.get_state()
        if current_state != ReportFilterStates.waiting_for_object:
            logger.error(f"Неправильное состояние: {current_state}, ожидалось: ReportFilterStates.waiting_for_object")
            return False
        
        logger.info("Тест успешно пройден!")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении теста: {e}", exc_info=True)
        return False
    finally:
        # Удаляем тестовые данные
        await cleanup_test_data(session)
        await session.close()

async def main():
    """Основная функция для запуска теста"""
    try:
        logger.info("Запуск теста process_filter_object")
        result = await test_process_filter_object()
        if result:
            logger.info("✅ Тест успешно пройден")
        else:
            logger.error("❌ Тест не пройден")
    except Exception as e:
        logger.error(f"Ошибка при выполнении теста: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 