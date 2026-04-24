import asyncio
from app.infra.db import async_engine
from app.domain.models.base import Base  # или где у вас Base
# если Base в app.domain.models import Base — поправь импорт под проект

async def main():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(main())
