from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    username = Column(String(50), index=True, nullable=False)
    session_id = Column(String(64), nullable=True, index=True)
    source_system = Column(String(100), nullable=False)
    source_ip = Column(String(45), nullable=False)
    device_id = Column(String(50), nullable=False)
    action = Column(String(100), index=True, nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(100), nullable=False)
    success = Column(Boolean, default=True, nullable=False)
    raw_event_hash = Column(String(64), index=True, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processing_status = Column(String(20), default="NEW", nullable=False)  # NEW, PROCESSED, DUPLICATE, INVALID

    attribution_result = relationship("AttributionResult", back_populates="system_log", uselist=False)
