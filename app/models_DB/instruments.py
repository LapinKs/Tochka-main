from sqlalchemy import Column, String, CheckConstraint
from app.db_manager import Base

class Instrument_db(Base):
    __tablename__ = "instruments"
    name = Column(String(255), nullable=False)
    ticker = Column(String(10), primary_key=True)

    # Под схему подгоняем ограничения
    __table_args__ = (
        CheckConstraint("ticker ~ '^[A-Z]{2,10}$'", name="instrument_ticker_check"),
    )