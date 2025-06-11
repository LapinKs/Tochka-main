from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

engine = create_async_engine(
    "postgresql+asyncpg://user:12341234@rc1a-i25i7m8rrl055efp.mdb.yandexcloud.net:6432/tochka",
    echo=False, pool_size=50, max_overflow=20, pool_timeout=30, pool_recycle=3600,
)
AsyncSessionLocal = sessionmaker( engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
