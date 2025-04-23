from construction_report_bot.database.session import async_session
from construction_report_bot.database.models import User
from sqlalchemy import select
import asyncio

async def check_clients():
    async with async_session() as session:
        result = await session.execute(select(User).where(User.role == 'client'))
        clients = result.scalars().all()
        print(f'Всего заказчиков в БД: {len(clients)}')
        print('\nСписок заказчиков:')
        for client in clients:
            print(f'- {client.username or client.telegram_id}')

if __name__ == '__main__':
    asyncio.run(check_clients()) 