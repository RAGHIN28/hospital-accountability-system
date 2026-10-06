"""
Persistent Human Adjudication Service (Review 3 — Work Package R3.3)
Hospital Shared-Account Elimination & Accountable Action Attribution PoC

Provides ACID-compliant persistence for human compliance officer reviews,
ensuring decisions survive Streamlit reruns, browser refreshes, dashboard
navigation, and application restarts.
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure backend and root directories are in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal, engine, Base
from app.models.adjudication import AdjudicationRecord
from app.models.system_log import SystemLog
from src.audit_chain import TamperEvidentAuditTrail

# Ensure human_adjudications table is initialized
Base.metadata.create_all(bind=engine)


class AdjudicationPersistenceService:
    """
    ACID-compliant persistence service for compliance officer adjudication decisions.
    Integrates with the SQLite database tier and the cryptographic audit chain.
    """

    VALID_DECISIONS = {
        "CONFIRM_IDENTITY",
        "MARK_UNATTRIBUTED",
        "REQUEST_MORE_EVIDENCE",
        "DISMISS",
        "ESCALATE",
    }

    VALID_STATUSES = {
        "SUBMITTED",
        "AMENDED",
        "RESOLVED",
        "REOPENED",
        "UNDER_REVIEW"
    }

    MAX_FINDINGS_LENGTH = 5000

    _shared_audit_trail: TamperEvidentAuditTrail = TamperEvidentAuditTrail()

    @classmethod
    def get_audit_trail(cls) -> TamperEvidentAuditTrail:
        """Access the shared cryptographic audit ledger for human review actions."""
        return cls._shared_audit_trail

    @classmethod
    def validate_decision(cls, decision: str) -> bool:
        """Check if an adjudication decision string is valid."""
        if not decision or not isinstance(decision, str):
            return False
        return decision.strip().upper() in cls.VALID_DECISIONS

    @classmethod
    def save_adjudication(
        cls,
        case_id: str,
        event_id: str,
        decision: str,
        reviewer: str,
        findings: str,
        status: str = "SUBMITTED",
        evidence_reference: Optional[str] = None,
        db=None,
        audit_trail: Optional[TamperEvidentAuditTrail] = None
    ) -> Dict[str, Any]:
        """
        Create or update a persistent compliance adjudication record.
        Validates inputs, executes safe atomic transaction, and records audit trail.
        """
        # 1. Input Validation
        if not case_id or not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Case ID cannot be empty.")
        clean_case_id = case_id.strip()

        if not event_id or not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Event ID cannot be empty.")
        clean_event_id = event_id.strip()

        if not decision or not isinstance(decision, str):
            raise ValueError("Adjudication decision cannot be empty.")
        clean_decision = decision.strip().upper()
        if clean_decision not in cls.VALID_DECISIONS:
            raise ValueError(
                f"Invalid adjudication decision '{decision}'. "
                f"Allowed decisions: {sorted(list(cls.VALID_DECISIONS))}"
            )

        if not reviewer or not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("Reviewer identity cannot be empty.")
        clean_reviewer = reviewer.strip()

        if findings is None or not isinstance(findings, str) or not findings.strip():
            raise ValueError("Findings / compliance notes cannot be empty.")
        clean_findings = findings.strip()
        if len(clean_findings) > cls.MAX_FINDINGS_LENGTH:
            raise ValueError(
                f"Findings notes exceed maximum length of {cls.MAX_FINDINGS_LENGTH} characters "
                f"(current length: {len(clean_findings)})."
            )

        clean_status = (status or "SUBMITTED").strip().upper()
        if clean_status not in cls.VALID_STATUSES:
            clean_status = "SUBMITTED"

        # 2. Database Session Management
        owns_session = db is None
        session = db or SessionLocal()

        try:
            # 3. Verify event exists in system_logs
            evt = session.query(SystemLog).filter(SystemLog.event_id == clean_event_id).first()
            if not evt:
                raise ValueError(
                    f"Referenced clinical event '{clean_event_id}' does not exist in system logs."
                )

            # 4. Check for existing adjudication by case_id
            existing = session.query(AdjudicationRecord).filter(
                AdjudicationRecord.case_id == clean_case_id
            ).first()

            now = datetime.utcnow()

            if existing:
                # Update existing record (amendment / re-review)
                existing.decision = clean_decision
                existing.reviewer = clean_reviewer
                existing.findings = clean_findings
                existing.status = "AMENDED" if clean_status == "SUBMITTED" else clean_status
                existing.evidence_reference = evidence_reference or existing.evidence_reference
                existing.version += 1
                existing.updated_at = now
                session.flush()
                result_dict = existing.to_dict()
                action_type = "AMEND_ADJUDICATION"
            else:
                # Insert new adjudication record
                new_rec = AdjudicationRecord(
                    case_id=clean_case_id,
                    event_id=clean_event_id,
                    decision=clean_decision,
                    reviewer=clean_reviewer,
                    findings=clean_findings,
                    status=clean_status,
                    evidence_reference=evidence_reference,
                    version=1,
                    created_at=now,
                    updated_at=now
                )
                session.add(new_rec)
                session.flush()
                result_dict = new_rec.to_dict()
                action_type = "CREATE_ADJUDICATION"

            session.commit()

            # 5. Record compliance action in cryptographic audit chain
            try:
                target_trail = audit_trail or cls._shared_audit_trail
                target_trail.append(
                    actor=clean_reviewer,
                    event_id=clean_event_id,
                    action=f"HUMAN_REVIEW_{action_type}",
                    details=(
                        f"Case: {clean_case_id} | Decision: {clean_decision} | "
                        f"Version: {result_dict['version']} | Status: {result_dict['status']}"
                    ),
                    timestamp=now
                )
            except Exception:
                pass  # Non-blocking for audit trail logger

            return result_dict

        except Exception as e:
            session.rollback()
            raise e
        finally:
            if owns_session:
                session.close()

    @classmethod
    def get_adjudication_by_case(cls, case_id: str, db=None) -> Optional[Dict[str, Any]]:
        """Retrieve authoritative saved adjudication by case_id."""
        if not case_id:
            return None
        clean_case_id = case_id.strip()

        owns_session = db is None
        session = db or SessionLocal()
        try:
            rec = session.query(AdjudicationRecord).filter(
                AdjudicationRecord.case_id == clean_case_id
            ).first()
            return rec.to_dict() if rec else None
        finally:
            if owns_session:
                session.close()

    @classmethod
    def get_adjudication_by_event(cls, event_id: str, db=None) -> Optional[Dict[str, Any]]:
        """Retrieve authoritative saved adjudication by event_id."""
        if not event_id:
            return None
        clean_event_id = event_id.strip()

        owns_session = db is None
        session = db or SessionLocal()
        try:
            rec = session.query(AdjudicationRecord).filter(
                AdjudicationRecord.event_id == clean_event_id
            ).order_by(AdjudicationRecord.updated_at.desc()).first()
            return rec.to_dict() if rec else None
        finally:
            if owns_session:
                session.close()

    @classmethod
    def list_adjudications(cls, db=None) -> List[Dict[str, Any]]:
        """List all historical human adjudication records ordered by update timestamp."""
        owns_session = db is None
        session = db or SessionLocal()
        try:
            records = session.query(AdjudicationRecord).order_by(
                AdjudicationRecord.updated_at.desc()
            ).all()
            return [r.to_dict() for r in records]
        finally:
            if owns_session:
                session.close()

    @classmethod
    def delete_adjudication(cls, case_id: str, db=None) -> bool:
        """Administrative removal of an adjudication record (e.g. testing cleanup)."""
        if not case_id:
            return False
        clean_case_id = case_id.strip()

        owns_session = db is None
        session = db or SessionLocal()
        try:
            rec = session.query(AdjudicationRecord).filter(
                AdjudicationRecord.case_id == clean_case_id
            ).first()
            if rec:
                session.delete(rec)
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            return False
        finally:
            if owns_session:
                session.close()
