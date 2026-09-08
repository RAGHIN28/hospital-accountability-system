from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class SharedAccount(Base):
    __tablename__ = "shared_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    system_name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    account_type = Column(String(50), nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)
    risk_level = Column(String(20), default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    authorizations = relationship("SharedAccountAuthorization", back_populates="shared_account")
