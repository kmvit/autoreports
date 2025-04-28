import os
import sys
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Проверяем, что путь добавлен корректно
if project_root not in sys.path:
    sys.path.append(project_root)

from construction_report_bot.database.models import Base
from construction_report_bot.config.settings import Settings

# Создаем тестовые настройки, которые используют SQLite in-memory
class TestSettings(Settings):
    @property
    def DATABASE_URL(self) -> str:
        """Переопределяем URL для использования SQLite в памяти"""
        return "sqlite+aiosqlite:///:memory:"

# Создаем тестовый экземпляр настроек
test_settings = TestSettings()

# Создаем тестовый движок БД
test_engine = create_async_engine(
    test_settings.DATABASE_URL,
    echo=True,
    future=True,
    poolclass=NullPool,
)

# Создаем тестовую фабрику сессий
test_async_session = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@pytest.fixture(scope="session")
def event_loop():
    """Создаем event loop для pytest-asyncio"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def init_test_db():
    """Инициализируем тестовую базу данных"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def test_db_session(init_test_db):
    """Создаем тестовую сессию БД для каждого теста"""
    async with test_async_session() as session:
        # Начинаем транзакцию
        async with session.begin():
            # Используем вложенную транзакцию для тестов
            yield session
            # Откатываем все изменения после каждого теста
            await session.rollback()

@pytest.fixture
async def test_session():
    """Возвращает тестовую сессию БД без обертки в генератор"""
    async with test_async_session() as session:
        yield session

@pytest.fixture
async def patched_get_session(test_db_session, monkeypatch):
    """Патчим функцию get_session для использования тестовой сессии"""
    async def mock_get_session():
        yield test_db_session
        
    # Здесь патчим функцию в модуле, который используется в тестах
    from construction_report_bot.database.session import get_session
    monkeypatch.setattr("construction_report_bot.database.session.get_session", mock_get_session)
    monkeypatch.setattr("tests.client.test_today_report.get_session", mock_get_session)
    
    return test_db_session 