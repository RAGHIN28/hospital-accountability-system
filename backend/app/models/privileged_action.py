from sqlalchemy import Column, Integer, String
from app.database import Base


class PrivilegedAction(Base):
    __tablename__ = "privileged_actions"

    id = Column(Integer, primary_key=True, index=True)
    action_name = Column(String(100), unique=True, index=True, nullable=False)
    sensitivity_level = Column(String(20), nullable=False)  # HIGH, CRITICAL, MEDIUM
    description = Column(String(255), nullable=False)
