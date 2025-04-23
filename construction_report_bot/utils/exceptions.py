"""Исключения для приложения."""

class ValidationError(Exception):
    """Исключение для ошибок валидации данных."""
    pass

class DatabaseError(Exception):
    """Исключение для ошибок базы данных."""
    pass 