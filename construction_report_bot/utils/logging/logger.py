import logging
import os
from datetime import datetime
from pathlib import Path

# Создаем директорию для логов, если она не существует
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Настраиваем формат логирования
log_format = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Создаем файловый обработчик
file_handler = logging.FileHandler(
    filename=log_dir / f"admin_report_{datetime.now().strftime('%Y-%m-%d')}.log",
    encoding='utf-8'
)
file_handler.setFormatter(log_format)

# Создаем консольный обработчик
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_format)

# Создаем логгер
logger = logging.getLogger('admin_report')
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def log_admin_action(action: str, user_id: int, details: str = None):
    """
    Логирование действий администратора
    
    Args:
        action (str): Тип действия
        user_id (int): ID пользователя
        details (str, optional): Дополнительные детали
    """
    message = f"User {user_id} - {action}"
    if details:
        message += f" - {details}"
    logger.info(message)

def log_error(error: Exception, user_id: int = None, details: str = None):
    """
    Логирование ошибок
    
    Args:
        error (Exception): Объект исключения
        user_id (int, optional): ID пользователя
        details (str, optional): Дополнительные детали
    """
    message = f"Error: {str(error)}"
    if user_id:
        message = f"User {user_id} - {message}"
    if details:
        message += f" - {details}"
    logger.error(message, exc_info=True) 