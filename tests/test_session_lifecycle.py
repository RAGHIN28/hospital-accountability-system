import os
import sys
import pytest
from datetime import datetime, timedelta

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from src.session_lifecycle import SessionLifecycleManager, SessionState


def test_normal_session_and_activity_refresh():
    """Verify normal session activity refresh within timeout window."""
    mgr = SessionLifecycleManager(default_timeout_minutes=30)
    now = datetime(2026, 9, 1, 9, 0, 0)
    session = mgr.create_session("SESS-TEST-01", "radiology_shared", user_id="EMP003", created_at=now)
    assert session["status"] == SessionState.ACTIVE

    # Action after 10 minutes refreshes activity
    valid_act1, status1, s1 = mgr.record_activity("SESS-TEST-01", now + timedelta(minutes=10))
    assert valid_act1
    assert s1["last_activity"] == now + timedelta(minutes=10)

    # Action after another 20 minutes (total 30 mins from start, 20 mins from last) succeeds
    valid_act2, status2, s2 = mgr.record_activity("SESS-TEST-01", now + timedelta(minutes=30))
    assert valid_act2
    assert s2["status"] == SessionState.ACTIVE


def test_session_inactivity_timeout_expiration():
    """Verify that inactivity exceeding configured timeout transitions session to EXPIRED."""
    mgr = SessionLifecycleManager(default_timeout_minutes=30)
    now = datetime(2026, 9, 1, 9, 0, 0)
    mgr.create_session("SESS-TEST-02", "lab_shared", user_id="EMP004", created_at=now)

    # Inactivity gap of 31 minutes
    valid, status, s = mgr.record_activity("SESS-TEST-02", now + timedelta(minutes=31))
    assert not valid
    assert status == "SESSION_EXPIRED"
    assert s["status"] == SessionState.EXPIRED

    # Subsequent activity on expired session remains rejected
    valid_sub, status_sub, _ = mgr.record_activity("SESS-TEST-02", now + timedelta(minutes=35))
    assert not valid_sub
    assert status_sub == "SESSION_EXPIRED"


def test_explicit_session_termination():
    """Verify that administrator termination immediately invalidates session."""
    mgr = SessionLifecycleManager()
    now = datetime(2026, 9, 1, 10, 0, 0)
    mgr.create_session("SESS-TEST-03", "billing_shared", user_id="EMP009", created_at=now)

    # Terminate session
    mgr.terminate_session("SESS-TEST-03", now + timedelta(minutes=5), reason="Suspected credential sharing")
    valid, status = mgr.is_session_valid("SESS-TEST-03", now + timedelta(minutes=10))
    assert not valid
    assert status == "SESSION_TERMINATED"


def test_duplicate_session_creation_handling():
    """Verify that duplicate session creation returns duplicate status without corrupting state."""
    mgr = SessionLifecycleManager()
    now = datetime(2026, 9, 1, 8, 0, 0)
    res1 = mgr.create_session("SESS-DUP-01", "ward_shared", user_id="EMP011", created_at=now)
    assert res1.get("status") != "DUPLICATE"

    # Second creation with identical session_id
    res2 = mgr.create_session("SESS-DUP-01", "ward_shared", user_id="EMP011", created_at=now)
    assert res2["status"] == "DUPLICATE"


def test_out_of_order_session_events():
    """Verify that an activity timestamp before session creation is rejected."""
    mgr = SessionLifecycleManager()
    now = datetime(2026, 9, 1, 10, 0, 0)
    mgr.create_session("SESS-ORD-01", "pharmacy_shared", user_id="EMP007", created_at=now)

    # Activity timestamp 5 minutes BEFORE session creation
    valid, status, _ = mgr.record_activity("SESS-ORD-01", now - timedelta(minutes=5))
    assert not valid
    assert status == "TIMESTAMP_BEFORE_SESSION_START"
