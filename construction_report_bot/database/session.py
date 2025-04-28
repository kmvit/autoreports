from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from construction_report_bot.config.settings import settings
from .models import Base

# Создаем асинхронный движок БД
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=5,
    max_overflow=10
)

# Создаем фабрику асинхронных сессий
async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def create_db_session():
    """Создание всех таблиц и подготовка базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    """Получение сессии для работы с базой данных"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_async_session() -> AsyncSession:
    """Получить асинхронную сессию"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close() 