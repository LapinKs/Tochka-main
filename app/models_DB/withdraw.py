from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db_manager import Base

class Withdraw_db(Base):
    __tablename__ = "withdraw"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    amount = Column(Integer, nullable=False)
