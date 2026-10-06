from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class AdjudicationRecord(Base):
    """
    Persistent compliance adjudication record for human-in-the-loop clinical review.
    Captures formal decisions, reviewer identity, evidentiary findings, and revision history.
    """
    __tablename__ = "human_adjudications"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(64), unique=True, index=True, nullable=False)
    event_id = Column(String(64), ForeignKey("system_logs.event_id"), index=True, nullable=False)
    decision = Column(String(50), nullable=False)  # CONFIRM_IDENTITY, MARK_UNATTRIBUTED, REQUEST_MORE_EVIDENCE, DISMISS, ESCALATE
    reviewer = Column(String(100), nullable=False)
    findings = Column(Text, nullable=False)
    status = Column(String(30), default="SUBMITTED", nullable=False)  # SUBMITTED, AMENDED, RESOLVED
    evidence_reference = Column(String(255), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship to SystemLog
    system_log = relationship("SystemLog", foreign_keys=[event_id])

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "event_id": self.event_id,
            "decision": self.decision,
            "reviewer": self.reviewer,
            "findings": self.findings,
            "status": self.status,
            "evidence_reference": self.evidence_reference,
            "version": self.version,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.updated_at, datetime) else str(self.updated_at)
        }
