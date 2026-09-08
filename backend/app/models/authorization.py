from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SharedAccountAuthorization(Base):
    __tablename__ = "shared_account_authorization"

    id = Column(Integer, primary_key=True, index=True)
    shared_account_id = Column(Integer, ForeignKey("shared_accounts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    authorized_from = Column(DateTime, nullable=False)
    authorized_until = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=False)
    approved_by = Column(String(100), nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, EXPIRED, REVOKED

    shared_account = relationship("SharedAccount", back_populates="authorizations")
    user = relationship("User", back_populates="authorizations")
