from sqlalchemy import Column, Integer, ForeignKey, String
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.db_manager import Base

class Deposit_db(Base):
    __tablename__ = "deposit"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())

    amount = Column(Integer, nullable=False)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
