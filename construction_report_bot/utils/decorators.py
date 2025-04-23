import logging
import functools
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from typing import Callable, Any, Union, Dict

def error_handler(func: Callable) -> Callable:
    """
    Декоратор для обработки ошибок в обработчиках.
    Логирует ошибку и возвращает сообщение пользователю.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Ошибка в {func.__name__}: {e}")
            
            # Определяем первый аргумент (может быть Message или CallbackQuery)
            event = args[0] if args else None
            
            error_text = "Произошла ошибка при выполнении операции. Попробуйте позже."
            
            # Создаем клавиатуру для возврата назад
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
            
            if isinstance(event, CallbackQuery):
                try:
                    await event.message.edit_text(error_text, reply_markup=builder.as_markup())
                except Exception:
                    await event.answer("Произошла ошибка. Попробуйте позже.")
            elif isinstance(event, Message):
                await event.answer(error_text, reply_markup=builder.as_markup())
    
    return wrapper

def extract_id_from_callback(callback_data: str, prefix: str) -> int:
    """
    Извлекает ID из строки обратного вызова.
    Например, из "edit_client_123" с префиксом "edit_client_" извлечет 123.
    
    Args:
        callback_data: Строка обратного вызова
        prefix: Префикс, после которого следует ID
        
    Returns:
        int: Извлеченный ID
        
    Raises:
        ValueError: Если ID не может быть извлечен
    """
    if not callback_data.startswith(prefix):
        raise ValueError(f"Неверный формат callback_data: {callback_data}, ожидался префикс {prefix}")
    
    id_str = callback_data[len(prefix):]
    try:
        return int(id_str)
    except ValueError:
        raise ValueError(f"ID не является числом: {id_str} в {callback_data}")

def with_session(func: Callable) -> Callable:
    """
    Декоратор для автоматического управления сессией базы данных.
    Создает сессию, передает ее в функцию и закрывает после выполнения.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        from construction_report_bot.database.session import get_session
        
        # Получаем генератор сессии
        session_gen = get_session()
        
        try:
            # Получаем сессию
            session = await session_gen.__anext__()
            
            # Добавляем сессию в аргументы функции
            result = await func(*args, session=session, **kwargs)
            
            return result
        except Exception as e:
            logging.error(f"Ошибка в {func.__name__} с сессией БД: {e}")
            raise
        finally:
            try:
                await session.close()
            except Exception as e:
                logging.error(f"Ошибка при закрытии сессии: {e}")
    
    return wrapper 