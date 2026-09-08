import os
import sys
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "backend"))

from app.database import Base
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.system_log import SystemLog
from app.models.privileged_action import PrivilegedAction
from app.models.attribution_result import AttributionResult
from app.services.baseline import BaselineAttributionEngine
from app.services.attribution import PrototypeAttributionEngine
from app.services.event_processor import EventProcessor, calculate_event_hash
from app.services.metrics import MetricsService


@pytest.fixture
def db_session():
    """Create a pristine in-memory SQLite database for isolated unit testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Seed core test users
    user1 = User(id=1, employee_id="EMP001", full_name="Dr. Arun Kumar", role="Consultant", workforce_type="Visiting Consultant", department="Cardiology", active=True)
    user2 = User(id=2, employee_id="EMP002", full_name="Dr. Priya Menon", role="Radiologist", workforce_type="Visiting Consultant", department="Radiology", active=True)
    user3 = User(id=3, employee_id="EMP003", full_name="Ravi Kumar", role="Radiology Technologist", workforce_type="Permanent Staff", department="Radiology", active=True)
    user4 = User(id=4, employee_id="EMP004", full_name="Meena Joseph", role="Senior Lab Tech", workforce_type="Permanent Staff", department="Laboratory", active=True)
    user_inactive = User(id=5, employee_id="EMP005", full_name="Former Staff", role="Intern", workforce_type="Intern", department="Radiology", active=False)
    session.add_all([user1, user2, user3, user4, user_inactive])

    # Seed shared accounts
    sa_rad = SharedAccount(id=1, username="radiology_shared", system_name="PACS", department="Radiology", account_type="DEPARTMENTAL_WORKSTATION", status="ACTIVE", risk_level="HIGH")
    sa_lab = SharedAccount(id=2, username="lab_shared", system_name="LIS", department="Laboratory", account_type="DEPARTMENTAL_WORKSTATION", status="ACTIVE", risk_level="HIGH")
    session.add_all([sa_rad, sa_lab])

    # Seed privileged action
    pa1 = PrivilegedAction(id=1, action_name="VIEW_PATIENT_RECORD", sensitivity_level="HIGH", description="Access ePHI")
    pa2 = PrivilegedAction(id=2, action_name="EXPORT_PATIENT_RECORD", sensitivity_level="CRITICAL", description="Export health data")
    session.add_all([pa1, pa2])

    session.commit()
    yield session
    session.close()


def test_normal_shared_account_attribution(db_session):
    """Test 1: Single authorized user with active delegation and session match."""
    # Active delegation for Ravi Kumar (id=3) on radiology_shared
    now = datetime(2026, 9, 1, 10, 0, 0)
    auth = SharedAccountAuthorization(
        shared_account_id=1,
        user_id=3,
        authorized_from=now - timedelta(hours=2),
        authorized_until=now + timedelta(hours=4),
        reason="Morning Shift",
        approved_by="Dr. Priya",
        status="ACTIVE"
    )
    db_session.add(auth)
    db_session.commit()

    event = {
        "event_id": "TEST-EVT-001",
        "timestamp": now,
        "username": "radiology_shared",
        "session_id": "SESS-EMP003-RAD-01",
        "source_system": "PACS",
        "source_ip": "192.168.10.21",
        "device_id": "RAD-WS-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-101",
        "success": True
    }
    res = EventProcessor.process_raw_event(db_session, event)
    assert res["status"] == "PROCESSED"

    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-001").first()
    assert attr is not None
    assert attr.attributed_user_id == 3  # Attributed to Ravi Kumar
    assert attr.confidence_level == "HIGH"
    assert attr.confidence_score >= 80.0
    assert "Active Delegation Window" in attr.explanation


def test_direct_named_user_attribution(db_session):
    """Test 2: Direct individual user login attributes with 100% confidence."""
    now = datetime(2026, 9, 1, 10, 30, 0)
    event = {
        "event_id": "TEST-EVT-002",
        "timestamp": now,
        "username": "EMP001",  # Direct login for Dr. Arun Kumar
        "session_id": "SESS-DIR-01",
        "source_system": "CARDIOLOGY_HIS",
        "source_ip": "192.168.60.10",
        "device_id": "CARDIO-WS-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-202",
        "success": True
    }
    res = EventProcessor.process_raw_event(db_session, event)
    assert res["status"] == "PROCESSED"

    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-002").first()
    assert attr is not None
    assert attr.attributed_user_id == 1  # Dr. Arun Kumar
    assert attr.confidence_score == 100.0
    assert attr.baseline_status == "ATTRIBUTED"
    assert attr.attribution_status == "ATTRIBUTED"


def test_multiple_authorized_users_baseline_ambiguous(db_session):
    """Test 3: Multiple authorized users causes baseline to mark AMBIGUOUS."""
    now = datetime(2026, 9, 1, 14, 0, 0)
    # Both Dr. Priya (user 2) and Ravi (user 3) authorized on radiology_shared
    auth1 = SharedAccountAuthorization(
        shared_account_id=1, user_id=2,
        authorized_from=now - timedelta(hours=1), authorized_until=now + timedelta(hours=3),
        reason="Consultation", approved_by="Director", status="ACTIVE"
    )
    auth2 = SharedAccountAuthorization(
        shared_account_id=1, user_id=3,
        authorized_from=now - timedelta(hours=2), authorized_until=now + timedelta(hours=2),
        reason="Tech Shift", approved_by="Dr. Priya", status="ACTIVE"
    )
    db_session.add_all([auth1, auth2])
    db_session.commit()

    event = {
        "event_id": "TEST-EVT-003",
        "timestamp": now,
        "username": "radiology_shared",
        "session_id": "SESS-EMP002-RAD-02",  # Explicitly Dr. Priya's session
        "source_system": "PACS",
        "source_ip": "192.168.10.22",
        "device_id": "RAD-WS-02",
        "action": "EXPORT_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-303",
        "success": True
    }
    EventProcessor.process_raw_event(db_session, event)
    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-003").first()
    assert attr.baseline_status == "AMBIGUOUS"  # Baseline fails to differentiate
    assert attr.attribution_status == "ATTRIBUTED"  # Prototype resolves via session binding
    assert attr.attributed_user_id == 2  # Dr. Priya Menon


def test_expired_delegation_unattributed(db_session):
    """Test 4: Expired delegation results in UNATTRIBUTED with clear explanation."""
    now = datetime(2026, 9, 1, 19, 0, 0)
    # Delegation expired at 16:00
    auth = SharedAccountAuthorization(
        shared_account_id=1, user_id=3,
        authorized_from=now - timedelta(hours=8), authorized_until=now - timedelta(hours=3),
        reason="Expired Shift", approved_by="Dr. Priya", status="EXPIRED"
    )
    db_session.add(auth)
    db_session.commit()

    event = {
        "event_id": "TEST-EVT-004",
        "timestamp": now,
        "username": "radiology_shared",
        "session_id": "SESS-ROGUE-04",
        "source_system": "PACS",
        "source_ip": "192.168.10.99",
        "device_id": "RAD-WS-UNKNOWN",
        "action": "EXPORT_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-404",
        "success": True
    }
    EventProcessor.process_raw_event(db_session, event)
    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-004").first()
    assert attr.attribution_status == "UNATTRIBUTED"
    assert "Expired" in attr.explanation or "outside delegation" in attr.explanation


def test_missing_session_id_resilience(db_session):
    """Test 5: System does not crash when session_id is None; uses delegation/network."""
    now = datetime(2026, 9, 1, 11, 0, 0)
    auth = SharedAccountAuthorization(
        shared_account_id=1, user_id=3,
        authorized_from=now - timedelta(hours=2), authorized_until=now + timedelta(hours=2),
        reason="Shift", approved_by="Dr. Priya", status="ACTIVE"
    )
    db_session.add(auth)
    db_session.commit()

    event = {
        "event_id": "TEST-EVT-005",
        "timestamp": now,
        "username": "radiology_shared",
        "session_id": None,  # Missing session ID!
        "source_system": "PACS",
        "source_ip": "192.168.10.21",
        "device_id": "RAD-WS-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-505",
        "success": True
    }
    res = EventProcessor.process_raw_event(db_session, event)
    assert res["status"] == "PROCESSED"
    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-005").first()
    assert attr is not None
    assert attr.attributed_user_id == 3
    assert attr.confidence_score >= 65.0  # Delegation (40) + Device (15) + IP (10) + Dept (5) = 70


def test_duplicate_event_detection(db_session):
    """Test 6: Duplicate events are detected via event_id / hash and not duplicated in DB."""
    now = datetime(2026, 9, 1, 9, 0, 0)
    event = {
        "event_id": "TEST-EVT-006",
        "timestamp": now,
        "username": "radiology_shared",
        "session_id": "SESS-DUP-01",
        "source_system": "PACS",
        "source_ip": "192.168.10.21",
        "device_id": "RAD-WS-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-606",
        "success": True
    }
    res1 = EventProcessor.process_raw_event(db_session, event)
    assert res1["status"] == "PROCESSED"

    # Second submission of identical event
    res2 = EventProcessor.process_raw_event(db_session, event)
    assert res2["status"] == "DUPLICATE"

    # Check database records count: only 1 log and 1 attribution result
    logs_count = db_session.query(SystemLog).filter(SystemLog.event_id == "TEST-EVT-006").count()
    attrs_count = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-006").count()
    assert logs_count == 1
    assert attrs_count == 1


def test_unknown_shared_account(db_session):
    """Test 7: Unregistered account marks UNATTRIBUTED with clear explanation."""
    now = datetime(2026, 9, 1, 10, 0, 0)
    event = {
        "event_id": "TEST-EVT-007",
        "timestamp": now,
        "username": "unknown_shadow_account",
        "session_id": "SESS-UNKNOWN",
        "source_system": "SHADOW_BOX",
        "source_ip": "10.10.10.10",
        "device_id": "UNKNOWN-DEV",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-707",
        "success": True
    }
    res = EventProcessor.process_raw_event(db_session, event)
    assert res["status"] == "PROCESSED"
    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-007").first()
    assert attr.attribution_status == "UNATTRIBUTED"
    assert "not found in employee roster" in attr.explanation or "neither a recognized shared account" in attr.explanation


def test_inactive_user_disqualification(db_session):
    """Test 8: Inactive user is disqualified from attribution."""
    now = datetime(2026, 9, 1, 10, 0, 0)
    # user 5 is inactive
    event = {
        "event_id": "TEST-EVT-008",
        "timestamp": now,
        "username": "EMP005",  # Inactive user
        "session_id": "SESS-INACTIVE",
        "source_system": "PACS",
        "source_ip": "192.168.10.21",
        "device_id": "RAD-WS-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-808",
        "success": True
    }
    res = EventProcessor.process_raw_event(db_session, event)
    assert res["status"] == "PROCESSED"
    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-008").first()
    assert attr.attribution_status == "UNATTRIBUTED"
    assert "INACTIVE" in attr.explanation


def test_missing_delegation_source_graceful_handling(db_session):
    """Test 9: System does not crash when no delegations exist for account."""
    now = datetime(2026, 9, 1, 12, 0, 0)
    # lab_shared has no delegations in db_session
    event = {
        "event_id": "TEST-EVT-009",
        "timestamp": now,
        "username": "lab_shared",
        "session_id": "SESS-LAB-99",
        "source_system": "LIS",
        "source_ip": "192.168.20.14",
        "device_id": "LAB-PC-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-909",
        "success": True
    }
    res = EventProcessor.process_raw_event(db_session, event)
    assert res["status"] == "PROCESSED"
    attr = db_session.query(AttributionResult).filter(AttributionResult.event_id == "TEST-EVT-009").first()
    assert attr is not None
    # Score from department and device might be present but below 60 -> UNATTRIBUTED
    assert attr.attribution_status == "UNATTRIBUTED"
    assert attr.confidence_score < 60.0


def test_invalid_log_event(db_session):
    """Test 10: Event with missing required fields is flagged INVALID without crashing pipeline."""
    bad_event = {
        "event_id": "TEST-EVT-010-BAD",
        "timestamp": datetime.utcnow(),
        # username, source_system, device_id missing!
    }
    res = EventProcessor.process_raw_event(db_session, bad_event)
    assert res["status"] == "INVALID"
    log = db_session.query(SystemLog).filter(SystemLog.event_id == "TEST-EVT-010-BAD").first()
    assert log is not None
    assert log.processing_status == "INVALID"


def test_metrics_calculation_formula(db_session):
    """Test 11: Verify attribution percentage formula: (Attributed / Total Sensitive) * 100."""
    metrics = MetricsService.calculate_attribution_metrics(db_session)
    assert "baseline_attribution_percentage" in metrics
    assert "prototype_attribution_percentage" in metrics
    assert "improvement_percentage" in metrics
    if metrics["total_sensitive_actions"] > 0:
        expected_base_pct = round((metrics["baseline_attributed"] / metrics["total_sensitive_actions"]) * 100.0, 2)
        assert metrics["baseline_attribution_percentage"] == expected_base_pct
