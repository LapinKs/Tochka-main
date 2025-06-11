from sqlalchemy import  String, Integer, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db_manager import Base

class Balance_db(Base):
    __tablename__ = "balances"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    amount = Column(Integer, nullable=False, default=0)
    ticker = Column(String(10), primary_key=True)

