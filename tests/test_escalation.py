import os
import sys
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.database import Base
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.system_log import SystemLog
from app.models.privileged_action import PrivilegedAction
from app.models.attribution_result import AttributionResult
from src.escalation import EscalationManager


@pytest.fixture
def escalation_db():
    """Create in-memory SQLite database populated with escalation test cases."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Roster
    u1 = User(id=1, employee_id="EMP001", full_name="Dr. Arun Kumar", role="Consultant", workforce_type="Visiting", department="Radiology", active=True)
    u2 = User(id=2, employee_id="EMP002", full_name="Dr. Priya Menon", role="Radiologist", workforce_type="Visiting", department="Radiology", active=True)
    session.add_all([u1, u2])

    sa = SharedAccount(id=1, username="radiology_shared", system_name="PACS", department="Radiology", account_type="DEPARTMENTAL", status="ACTIVE", risk_level="HIGH")
    session.add(sa)

    pa = PrivilegedAction(id=1, action_name="EXPORT_PATIENT_RECORD", sensitivity_level="CRITICAL", description="Export health data")
    session.add(pa)
    session.commit()

    yield session
    session.close()


def test_conflicting_delegation_creates_escalation(escalation_db):
    """Test requirement: Conflicting delegation (ambiguous tie) creates escalation queue record."""
    log = SystemLog(
        id=201,
        event_id="EVT-ESC-CONF-001",
        timestamp=datetime(2026, 9, 1, 14, 0, 0),
        username="radiology_shared",
        session_id="SESS-AMBIGUOUS-01",
        source_system="PACS",
        source_ip="192.168.10.21",
        device_id="RAD-WS-01",
        action="EXPORT_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-201",
        success=True,
        raw_event_hash="hash_esc_conf_001"
    )
    attr = AttributionResult(
        event_id="EVT-ESC-CONF-001",
        attribution_status="AMBIGUOUS",
        confidence_level="AMBIGUOUS",
        confidence_score=45.0,
        attribution_method="UNRESOLVED",
        explanation="Ambiguous attribution: Multiple candidates have competing evidence within 5.0 pts."
    )
    escalation_db.add_all([log, attr])
    escalation_db.commit()

    manager = EscalationManager(escalation_db)
    queue = manager.build_escalation_queue(simulate_reviews=False)
    assert len(queue) == 1
    case = queue[0]
    assert case["event_id"] == "EVT-ESC-CONF-001"
    assert case["reason_category"] == "CONFLICTING_DELEGATION"
    assert case["priority"] == "HIGH"
    assert case["review_status"] == "PENDING_REVIEW"


def test_missing_roster_creates_escalation(escalation_db):
    """Test requirement: Missing roster creates escalation."""
    log = SystemLog(
        id=202,
        event_id="EVT-ESC-ROST-002",
        timestamp=datetime(2026, 9, 1, 14, 30, 0),
        username="unknown_external_staff",
        session_id="SESS-UNKNOWN",
        source_system="PACS",
        source_ip="192.168.10.99",
        device_id="RAD-WS-UNKNOWN",
        action="EXPORT_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-202",
        success=True,
        raw_event_hash="hash_esc_rost_002"
    )
    attr = AttributionResult(
        event_id="EVT-ESC-ROST-002",
        attribution_status="UNATTRIBUTED",
        confidence_level="UNATTRIBUTED",
        confidence_score=0.0,
        attribution_method="UNRESOLVED",
        explanation="Account 'unknown_external_staff' is not found in employee roster."
    )
    escalation_db.add_all([log, attr])
    escalation_db.commit()

    manager = EscalationManager(escalation_db)
    queue = manager.build_escalation_queue(simulate_reviews=False)
    assert len(queue) == 1
    case = queue[0]
    assert case["event_id"] == "EVT-ESC-ROST-002"
    assert case["reason_category"] == "MISSING_ROSTER"


def test_expired_delegation_creates_escalation(escalation_db):
    """Test requirement: Expired delegation creates escalation."""
    log = SystemLog(
        id=203,
        event_id="EVT-ESC-EXP-003",
        timestamp=datetime(2026, 9, 1, 23, 0, 0),
        username="radiology_shared",
        session_id="SESS-EXPIRED",
        source_system="PACS",
        source_ip="192.168.10.21",
        device_id="RAD-WS-01",
        action="EXPORT_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-203",
        success=True,
        raw_event_hash="hash_esc_exp_003"
    )
    attr = AttributionResult(
        event_id="EVT-ESC-EXP-003",
        attribution_status="UNATTRIBUTED",
        confidence_level="UNATTRIBUTED",
        confidence_score=0.0,
        attribution_method="UNRESOLVED",
        explanation="Delegation expired at 2026-09-01 16:00. Shared account used outside delegation window."
    )
    escalation_db.add_all([log, attr])
    escalation_db.commit()

    manager = EscalationManager(escalation_db)
    queue = manager.build_escalation_queue(simulate_reviews=False)
    assert len(queue) == 1
    case = queue[0]
    assert case["event_id"] == "EVT-ESC-EXP-003"
    assert case["reason_category"] == "EXPIRED_DELEGATION"
    assert case["priority"] == "HIGH"


def test_escalation_record_contains_required_evidence(escalation_db):
    """Test requirement: Escalation record contains all required fields for human review."""
    log = SystemLog(
        id=204,
        event_id="EVT-ESC-EVID-004",
        timestamp=datetime(2026, 9, 1, 15, 0, 0),
        username="radiology_shared",
        session_id="SESS-004",
        source_system="PACS",
        source_ip="192.168.10.21",
        device_id="RAD-WS-01",
        action="EXPORT_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-204",
        success=True,
        raw_event_hash="hash_esc_evid_004"
    )
    attr = AttributionResult(
        event_id="EVT-ESC-EVID-004",
        attribution_status="AMBIGUOUS",
        confidence_level="AMBIGUOUS",
        confidence_score=40.0,
        attribution_method="UNRESOLVED",
        explanation="Ambiguous attribution: Multiple candidates have competing evidence.",
        candidate_scores_json='[{"full_name": "Dr. Arun Kumar", "employee_id": "EMP001", "total_score": 40.0}]'
    )
    escalation_db.add_all([log, attr])
    escalation_db.commit()

    manager = EscalationManager(escalation_db)
    queue = manager.build_escalation_queue(simulate_reviews=False)
    case = queue[0]

    required_fields = [
        "case_id", "event_id", "created_at", "priority", "reason_category",
        "event_timestamp", "account_id", "session_id", "action_id",
        "candidate_users", "current_status", "recommended_review",
        "review_status", "reviewer", "review_timestamp", "review_notes"
    ]
    for field in required_fields:
        assert field in case, f"Missing required field: {field}"

    assert case["action_id"] == "EXPORT_PATIENT_RECORD"
    assert "Dr. Arun Kumar" in case["candidate_users"]
    assert case["review_status"] in ["PENDING_REVIEW", "UNDER_REVIEW", "RESOLVED", "REJECTED", "NO_ACTION"]
