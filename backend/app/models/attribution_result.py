from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class AttributionResult(Base):
    __tablename__ = "attribution_results"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), ForeignKey("system_logs.event_id"), unique=True, index=True, nullable=False)
    
    # Baseline Results
    baseline_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    baseline_confidence = Column(Float, default=0.0, nullable=False)
    baseline_status = Column(String(20), default="UNATTRIBUTED", nullable=False)  # ATTRIBUTED, AMBIGUOUS, UNATTRIBUTED
    baseline_explanation = Column(Text, nullable=True)

    # Prototype Multi-signal Results
    attributed_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    attribution_method = Column(String(50), default="UNRESOLVED", nullable=False)  # BASELINE, SESSION_MATCH, DELEGATION_MATCH, SESSION_AND_DELEGATION, UNRESOLVED
    confidence_score = Column(Float, default=0.0, nullable=False)  # 0 to 100
    confidence_level = Column(String(20), default="UNATTRIBUTED", nullable=False)  # HIGH, MEDIUM, LOW, UNATTRIBUTED, AMBIGUOUS
    attribution_status = Column(String(20), default="UNATTRIBUTED", nullable=False)  # ATTRIBUTED, UNATTRIBUTED, AMBIGUOUS
    explanation = Column(Text, nullable=False)
    candidate_scores_json = Column(Text, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    system_log = relationship("SystemLog", back_populates="attribution_result")
    baseline_user = relationship("User", foreign_keys=[baseline_user_id])
    attributed_user = relationship("User", foreign_keys=[attributed_user_id], back_populates="attributions")
