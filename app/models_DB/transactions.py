from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.sql import func
from app.db_manager import Base

class Transaction_db(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    amount = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
