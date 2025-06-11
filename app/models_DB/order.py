from sqlalchemy.sql import func
from sqlalchemy import Column,Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db_manager import Base

class OrderReq_db(Base):
    __tablename__ = "order_req"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    success = Column(Boolean, nullable=False, default=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("limit_orders.id"), nullable=False)
