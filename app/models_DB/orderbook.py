from sqlalchemy import Column, Integer, JSON, String,ForeignKey
from app.db_manager import Base

class OrderBook_db(Base):
    __tablename__ = "orderbook"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False, unique=True)
    bid_levels = Column(JSON, nullable=False)
    ask_levels = Column(JSON, nullable=False)
