import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from construction_report_bot.config.settings import settings
from construction_report_bot.handlers import register_all_handlers
from construction_report_bot.middlewares import setup_middlewares
from construction_report_bot.database.session import create_db_session

async def main():
    """Основная функция запуска бота"""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename="bot.log"
    )
    
    # Создаем экземпляр бота
    bot = Bot(token=settings.BOT_TOKEN)
    
    # Используем MemoryStorage для хранения состояний FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Инициализация базы данных
    await create_db_session()
    
    # Настройка middleware
    setup_middlewares(dp)
    
    # Регистрация обработчиков
    register_all_handlers(dp)
    
    # Запуск бота
    try:
        logging.info("Bot started")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by keyboard interrupt") 