"""Настройки приложения."""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Настройки бота
    BOT_TOKEN: str = Field(..., env='BOT_TOKEN')
    ADMIN_USER_IDS: str = Field('', env='ADMIN_USER_IDS')
    
    # Настройки базы данных
    DB_HOST: str = Field(default='localhost', env='DB_HOST')
    DB_PORT: int = Field(default=5432, env='DB_PORT')
    DB_NAME: str = Field(..., env='DB_NAME')
    DB_USER: str = Field(..., env='DB_USER')
    DB_PASSWORD: str = Field(..., env='DB_PASSWORD')
    
    # Настройки Redis
    REDIS_HOST: str = Field(default='localhost', env='REDIS_HOST')
    REDIS_PORT: int = Field(default=6379, env='REDIS_PORT')
    REDIS_DB: int = Field(default=0, env='REDIS_DB')
    
    # Настройки логирования
    LOG_LEVEL: str = Field(default='INFO', env='LOG_LEVEL')
    LOG_FILE: str = Field(default='logs/bot.log', env='LOG_FILE')
    
    # Настройки медиафайлов
    MEDIA_DIR: str = Field(default='media', env='MEDIA_DIR')
    MAX_PHOTO_SIZE: int = Field(default=5242880, env='MAX_PHOTO_SIZE')
    ALLOWED_PHOTO_TYPES: str = Field(default='jpg,jpeg,png', env='ALLOWED_PHOTO_TYPES')
    
    @property
    def MEDIA_ROOT(self) -> str:
        """Полный путь к директории медиафайлов."""
        return os.path.abspath(self.MEDIA_DIR)
    
    # Настройки уведомлений
    NOTIFICATION_CHAT_ID: int = Field(..., env='NOTIFICATION_CHAT_ID')
    ENABLE_NOTIFICATIONS: bool = Field(default=True, env='ENABLE_NOTIFICATIONS')
    
    # Настройки безопасности
    SECRET_KEY: str = Field(..., env='SECRET_KEY')
    JWT_EXPIRATION_DELTA: int = Field(default=86400, env='JWT_EXPIRATION_DELTA')
    
    # Настройки API
    API_VERSION: str = Field(default='v1', env='API_VERSION')
    API_PREFIX: str = Field(default='/api', env='API_PREFIX')
    DEBUG: bool = Field(default=False, env='DEBUG')
    
    # Роли пользователей
    ADMIN_ROLE: str = "admin"
    CLIENT_ROLE: str = "client"
    
    # Настройки для экспорта отчетов
    EXPORT_DIR: str = "exports"
    
    @field_validator('MAX_PHOTO_SIZE', 'DB_PORT', 'REDIS_PORT', 'REDIS_DB', 'NOTIFICATION_CHAT_ID', 'JWT_EXPIRATION_DELTA')
    @classmethod
    def validate_int_fields(cls, v: str | int) -> int:
        """Валидация целочисленных полей."""
        if isinstance(v, str):
            # Удаляем все нечисловые символы, кроме минуса
            v = ''.join(c for c in v if c.isdigit() or c == '-')
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError(f"Значение должно быть целым числом, получено: {v}")
    
    @field_validator('ENABLE_NOTIFICATIONS', 'DEBUG')
    @classmethod
    def validate_bool_fields(cls, v: str | bool) -> bool:
        """Валидация булевых полей."""
        if isinstance(v, str):
            v = v.lower().strip()
            if v in ('true', '1', 'yes', 'y'):
                return True
            if v in ('false', '0', 'no', 'n'):
                return False
            raise ValueError(f"Значение должно быть булевым, получено: {v}")
        return bool(v)
    
    @property
    def ALLOWED_PHOTO_TYPES_LIST(self) -> List[str]:
        """Получить список разрешенных типов фото."""
        if not self.ALLOWED_PHOTO_TYPES:
            return []
        return [t.strip() for t in self.ALLOWED_PHOTO_TYPES.split(',') if t.strip()]
    
    @property
    def DATABASE_URL(self) -> str:
        """Получить URL для подключения к базе данных."""
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._create_required_directories()
    
    def _create_required_directories(self):
        """Создание необходимых директорий."""
        # Создаем директорию для медиафайлов
        os.makedirs(self.MEDIA_ROOT, exist_ok=True)
        
        # Создаем директорию для логов
        log_dir = os.path.dirname(self.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        # Создаем директорию для экспорта
        os.makedirs(self.EXPORT_DIR, exist_ok=True)

# Создание экземпляра настроек
settings = Settings() 