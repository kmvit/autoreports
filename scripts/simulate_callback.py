#!/usr/bin/env python
"""
Скрипт для эмуляции нажатия кнопки в Telegram боте
без необходимости взаимодействия через Telegram.

Использование:
python simulate_callback.py <user_id> <callback_data>

Примеры:
python simulate_callback.py 1101434297 filter_reset
python simulate_callback.py 1101434297 back
"""

import sys
import asyncio
import logging
from aiogram.types import CallbackQuery, User, Chat, Message
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем необходимые модули из нашего проекта
sys.path.append('.')  # Добавляем текущую директорию в путь импорта
from construction_report_bot.bot import dp
from construction_report_bot.database.session import get_session

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def simulate_callback_query(user_id: int, callback_data: str):
    """Эмулирует нажатие кнопки с заданным callback_data от указанного пользователя."""
    logger.info(f"Эмуляция нажатия кнопки с callback_data '{callback_data}' от пользователя {user_id}")
    
    # Создаем объекты, необходимые для формирования CallbackQuery
    user = User(id=user_id, is_bot=False, first_name="Test", username="test_user")
    chat = Chat(id=user_id, type="private")
    message = Message(message_id=1, date=0, chat=chat)
    
    # Создаем объект CallbackQuery
    callback_query = CallbackQuery(
        id="test_callback_id",
        from_user=user,
        chat_instance="test_chat_instance",
        data=callback_data,
        message=message
    )
    
    # Перехватываем ответы бота для вывода в консоль
    original_answer = callback_query.answer
    original_message_edit_text = message.edit_text
    
    async def answer_interceptor(*args, **kwargs):
        logger.info(f"Bot ответил на callback: {args}, {kwargs}")
        return await original_answer(*args, **kwargs)
    
    async def edit_text_interceptor(*args, **kwargs):
        logger.info(f"Bot отредактировал сообщение: {args}, {kwargs}")
        return await original_message_edit_text(*args, **kwargs)
    
    callback_query.answer = answer_interceptor
    message.edit_text = edit_text_interceptor
    
    try:
        # Вызываем обработчик callback
        await dp.callback_query.trigger(callback_query)
        logger.info("Callback обработан успешно")
    except Exception as e:
        logger.error(f"Ошибка при обработке callback: {e}", exc_info=True)

async def main():
    if len(sys.argv) < 3:
        print(f"Использование: {sys.argv[0]} <user_id> <callback_data>")
        return
    
    user_id = int(sys.argv[1])
    callback_data = sys.argv[2]
    
    # Инициализируем бота и диспетчера
    try:
        logger.info("Начало эмуляции callback")
        await simulate_callback_query(user_id, callback_data)
        logger.info("Эмуляция callback завершена")
    except Exception as e:
        logger.error(f"Ошибка при эмуляции: {e}", exc_info=True)
    finally:
        # Закрываем сессию
        pass

if __name__ == "__main__":
    asyncio.run(main()) 