from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)
    workforce_type = Column(String(50), nullable=False)  # Permanent Staff, Visiting Consultant, Intern, Outsourced Technician
    department = Column(String(100), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    authorizations = relationship("SharedAccountAuthorization", back_populates="user")
    attributions = relationship(
        "AttributionResult",
        foreign_keys="AttributionResult.attributed_user_id",
        back_populates="attributed_user"
    )
