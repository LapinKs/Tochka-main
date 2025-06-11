from sqlalchemy import Column, Integer, DateTime, String, ForeignKey
from sqlalchemy.sql import func
from app.db_manager import Base
from sqlalchemy.dialects.postgresql import UUID
from app.models_DB.enums import order_status_enum, order_direction_enum

class LimitOrder_db(Base):
    __tablename__ = "limit_orders"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    status = Column(order_status_enum, nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    direction = Column(order_direction_enum, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)

    filled = Column(Integer, nullable=False, default=0)
