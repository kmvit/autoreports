import re
import string
import random
from typing import Dict, Any, Optional, Callable, TypeVar, List

T = TypeVar('T')

def validate_full_name(name: str) -> bool:
    """
    Проверка формата ФИО.
    
    Args:
        name: Строка с ФИО
        
    Returns:
        bool: True если формат корректный, иначе False
    """
    return bool(re.match(r'^[А-Яа-яЁё\s-]{2,100}$', name))

def validate_organization(org: str) -> bool:
    """
    Проверка названия организации.
    
    Args:
        org: Строка с названием организации
        
    Returns:
        bool: True если формат корректный, иначе False
    """
    return bool(re.match(r'^[А-Яа-яЁё0-9\s\-"\']{2,200}$', org))

def validate_contact_info(contact: str) -> bool:
    """
    Проверка контактной информации.
    Проверяет наличие телефона или email.
    
    Args:
        contact: Строка с контактной информацией
        
    Returns:
        bool: True если формат корректный, иначе False
    """
    phone_pattern = r'(\+7|8)[- _]?\(?[- _]?\d{3}[- _]?\)?[- _]?\d{3}[- _]?\d{2}[- _]?\d{2}'
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return bool(re.search(phone_pattern, contact) or re.search(email_pattern, contact))

def generate_access_code(length: int = 8) -> str:
    """
    Генерирует случайный код доступа.
    
    Args:
        length: Длина кода доступа (по умолчанию 8)
        
    Returns:
        str: Сгенерированный код доступа
    """
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

class Validator:
    """
    Класс для валидации данных с предоставлением информации об ошибках.
    """
    
    def __init__(self):
        self.validators: Dict[str, Callable[[Any], bool]] = {}
        self.error_messages: Dict[str, str] = {}
        
    def add_rule(self, field: str, validator: Callable[[Any], bool], error_message: str) -> None:
        """
        Добавляет правило валидации.
        
        Args:
            field: Название поля
            validator: Функция-валидатор, которая принимает значение и возвращает bool
            error_message: Сообщение об ошибке при неудачной валидации
        """
        self.validators[field] = validator
        self.error_messages[field] = error_message
        
    def validate(self, data: Dict[str, Any]) -> List[str]:
        """
        Проверяет данные на соответствие правилам.
        
        Args:
            data: Словарь с данными для проверки
            
        Returns:
            List[str]: Список сообщений об ошибках или пустой список, если ошибок нет
        """
        errors = []
        
        for field, validator in self.validators.items():
            if field in data and not validator(data[field]):
                errors.append(self.error_messages[field])
        
        return errors 