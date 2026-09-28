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
from app.services.attribution import PrototypeAttributionEngine
from src.telemetry_stress import TelemetryStressTester


@pytest.fixture
def mock_db():
    """Create in-memory SQLite database populated with test fixtures."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Users
    u1 = User(id=1, employee_id="EMP001", full_name="Dr. Arun Kumar", role="Consultant", workforce_type="Visiting", department="Cardiology", active=True)
    u2 = User(id=2, employee_id="EMP002", full_name="Dr. Priya Menon", role="Radiologist", workforce_type="Visiting", department="Radiology", active=True)
    u3 = User(id=3, employee_id="EMP003", full_name="Ravi Kumar", role="Technologist", workforce_type="Permanent", department="Radiology", active=True)
    session.add_all([u1, u2, u3])

    # Shared Accounts
    sa = SharedAccount(id=1, username="radiology_shared", system_name="PACS", department="Radiology", account_type="DEPARTMENTAL", status="ACTIVE", risk_level="HIGH")
    session.add(sa)

    # Privileged Actions
    pa1 = PrivilegedAction(id=1, action_name="VIEW_PATIENT_RECORD", sensitivity_level="HIGH", description="ePHI")
    pa2 = PrivilegedAction(id=2, action_name="EDIT_PATIENT_RECORD", sensitivity_level="CRITICAL", description="Modify ePHI")
    session.add_all([pa1, pa2])

    now = datetime(2026, 9, 1, 10, 0, 0)
    auth = SharedAccountAuthorization(
        id=1,
        shared_account_id=1,
        user_id=3,
        authorized_from=now - timedelta(hours=2),
        authorized_until=now + timedelta(hours=4),
        reason="Morning Radiology Tech Shift",
        approved_by="Dr. Priya Menon",
        status="ACTIVE"
    )
    session.add(auth)
    session.commit()

    yield session
    session.close()


def test_missing_cidr_does_not_crash_system(mock_db):
    """Test requirement: Missing CIDR / IP subnet does not crash system and attribution succeeds."""
    now = datetime(2026, 9, 1, 10, 30, 0)
    log = SystemLog(
        id=101,
        event_id="EVT-NO-CIDR-001",
        timestamp=now,
        username="radiology_shared",
        session_id="SESS-EMP003-RAD-01",
        source_system="PACS",
        source_ip="0.0.0.0",  # CIDR completely missing / unrouted
        device_id="RAD-WS-01",
        action="VIEW_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-101",
        success=True,
        raw_event_hash="hash_no_cidr_001"
    )
    mock_db.add(log)
    mock_db.commit()

    res = PrototypeAttributionEngine.evaluate(mock_db, log)
    assert res is not None
    assert res["status"] == "ATTRIBUTED"
    assert res["user_id"] == 3  # Ravi Kumar
    # Score has delegation (+40) + session (+30) + device (+15) + dept (+5) = 90
    assert res["confidence_score"] >= 85.0
    assert "IP Subnet Match" in " ".join(res["candidate_scores"][0]["missed_signals"])


def test_missing_device_fingerprint_does_not_crash_system(mock_db):
    """Test requirement: Missing device fingerprint does not crash system and attribution succeeds."""
    now = datetime(2026, 9, 1, 11, 0, 0)
    log = SystemLog(
        id=102,
        event_id="EVT-NO-DEV-002",
        timestamp=now,
        username="radiology_shared",
        session_id="SESS-EMP003-RAD-01",
        source_system="PACS",
        source_ip="192.168.10.21",
        device_id="UNKNOWN_DEVICE_FINGERPRINT",  # Missing / unmapped device
        action="EDIT_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-102",
        success=True,
        raw_event_hash="hash_no_dev_002"
    )
    mock_db.add(log)
    mock_db.commit()

    res = PrototypeAttributionEngine.evaluate(mock_db, log)
    assert res is not None
    assert res["status"] == "ATTRIBUTED"
    assert res["user_id"] == 3
    # Delegation (+40) + session (+30) + subnet (+10) + dept (+5) = 85
    assert res["confidence_score"] >= 80.0


def test_missing_user_agent_does_not_crash_system(mock_db):
    """Test requirement: Missing user-agent header does not crash system."""
    now = datetime(2026, 9, 1, 11, 15, 0)
    log = SystemLog(
        id=103,
        event_id="EVT-NO-UA-003",
        timestamp=now,
        username="radiology_shared",
        session_id="SESS-EMP003-RAD-01",
        source_system="PACS",
        source_ip="192.168.10.21",
        device_id="RAD-WS-01",
        action="VIEW_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-103",
        success=True,
        raw_event_hash="hash_no_ua_003"
    )
    mock_db.add(log)
    mock_db.commit()

    res = PrototypeAttributionEngine.evaluate(mock_db, log)
    assert res["status"] == "ATTRIBUTED"
    assert res["user_id"] == 3


def test_combined_telemetry_loss_resilience(mock_db):
    """Test requirement: Both CIDR and Device missing simultaneously."""
    now = datetime(2026, 9, 1, 11, 30, 0)
    log = SystemLog(
        id=104,
        event_id="EVT-NO-BOTH-004",
        timestamp=now,
        username="radiology_shared",
        session_id="SESS-EMP003-RAD-01",
        source_system="PACS",
        source_ip="0.0.0.0",
        device_id="UNKNOWN_DEVICE",
        action="VIEW_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-104",
        success=True,
        raw_event_hash="hash_no_both_004"
    )
    mock_db.add(log)
    mock_db.commit()

    res = PrototypeAttributionEngine.evaluate(mock_db, log)
    # Strong core evidence: Delegation (+40) + Session (+30) + Dept (+5) = 75 >= 60 threshold
    assert res["status"] == "ATTRIBUTED"
    assert res["user_id"] == 3
    assert res["confidence_level"] == "MEDIUM"


def test_inconsistent_telemetry_does_not_create_false_identity(mock_db):
    """
    Test requirement: Inconsistent / spoofed device or user-agent telemetry.
    The system must NOT automatically switch attribution to another user or invent identity.
    """
    now = datetime(2026, 9, 1, 11, 45, 0)
    # Log event comes with a cardiology device and strange IP on radiology_shared
    log = SystemLog(
        id=105,
        event_id="EVT-SPOOF-005",
        timestamp=now,
        username="radiology_shared",
        session_id="SESS-EMP003-RAD-01",
        source_system="PACS",
        source_ip="192.168.60.99",       # Foreign cardiology IP
        device_id="CARDIO-WS-FOREIGN",   # Foreign device
        action="VIEW_PATIENT_RECORD",
        target_type="PATIENT_RECORD",
        target_id="SYN-PAT-105",
        success=True,
        raw_event_hash="hash_spoof_005"
    )
    mock_db.add(log)
    mock_db.commit()

    res = PrototypeAttributionEngine.evaluate(mock_db, log)
    # The system must NOT switch attribution to Dr. Arun Kumar (Cardiology) just because of device/IP!
    assert res["user_id"] != 1  # Must NOT attribute to Cardiology user
    assert res["user_id"] == 3  # Keeps attribution to authorized Ravi Kumar based on delegation + session binding
