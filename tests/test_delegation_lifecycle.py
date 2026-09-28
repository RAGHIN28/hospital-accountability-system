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

from src.delegation_lifecycle import DelegationLifecycleManager, DelegationState


def test_delegation_normal_activation_and_temporal_states():
    """Verify state transitions: CREATED -> ACTIVE -> EXPIRED based on time window."""
    mgr = DelegationLifecycleManager()
    base_time = datetime(2026, 9, 1, 9, 0, 0)
    start_time = base_time + timedelta(hours=1)  # 10:00
    end_time = base_time + timedelta(hours=5)    # 14:00

    # 1. Created before start_time -> status is CREATED
    del_rec = mgr.create_delegation(
        shared_account="radiology_shared",
        delegate_user_id="EMP003",
        start_time=start_time,
        end_time=end_time,
        current_time=base_time  # 09:00
    )
    assert del_rec["status"] == DelegationState.CREATED

    # 2. Before window -> action unauthorized
    is_valid, reason, _ = mgr.is_valid_for_action("radiology_shared", "EMP003", base_time + timedelta(minutes=30))
    assert not is_valid

    # 3. Inside window -> state updates to ACTIVE, action authorized
    st = mgr.update_temporal_status(del_rec["delegation_id"], start_time + timedelta(minutes=15))
    assert st == DelegationState.ACTIVE
    is_valid_act, reason_act, _ = mgr.is_valid_for_action("radiology_shared", "EMP003", start_time + timedelta(minutes=15))
    assert is_valid_act
    assert reason_act == "AUTHORIZED"

    # 4. After window -> state updates to EXPIRED, action unauthorized
    st_exp = mgr.update_temporal_status(del_rec["delegation_id"], end_time + timedelta(minutes=10))
    assert st_exp == DelegationState.EXPIRED
    is_valid_exp, reason_exp, _ = mgr.is_valid_for_action("radiology_shared", "EMP003", end_time + timedelta(minutes=10))
    assert not is_valid_exp
    assert reason_exp == "DELEGATION_EXPIRED"


def test_delegation_revocation():
    """Verify that revoking a delegation immediately blocks subsequent actions."""
    mgr = DelegationLifecycleManager()
    now = datetime(2026, 9, 1, 10, 0, 0)
    del_rec = mgr.create_delegation(
        shared_account="lab_shared",
        delegate_user_id="EMP004",
        start_time=now,
        end_time=now + timedelta(hours=8),
        current_time=now
    )
    assert del_rec["status"] == DelegationState.ACTIVE

    # Action at 11:00 is authorized
    valid_before, _, _ = mgr.is_valid_for_action("lab_shared", "EMP004", now + timedelta(hours=1))
    assert valid_before

    # Revoke at 11:30
    mgr.revoke_delegation(del_rec["delegation_id"], "Emergency reassignment", "Dr. Rajesh Varma", revoked_at=now + timedelta(hours=1, minutes=30))
    assert del_rec["status"] == DelegationState.REVOKED

    # Action at 12:00 is rejected
    valid_after, reason_rev, _ = mgr.is_valid_for_action("lab_shared", "EMP004", now + timedelta(hours=2))
    assert not valid_after
    assert "REVOKED" in reason_rev


def test_delegation_cancellation():
    """Verify that cancelling a scheduled delegation prevents activation."""
    mgr = DelegationLifecycleManager()
    base_time = datetime(2026, 9, 1, 8, 0, 0)
    del_rec = mgr.create_delegation(
        shared_account="pharmacy_shared",
        delegate_user_id="EMP007",
        start_time=base_time + timedelta(hours=2),
        end_time=base_time + timedelta(hours=8),
        current_time=base_time
    )
    assert del_rec["status"] == DelegationState.CREATED

    # Cancel delegation
    mgr.cancel_delegation(del_rec["delegation_id"], "Supervisor", "Shift swap cancelled")
    assert del_rec["status"] == DelegationState.CANCELLED

    # Check temporal update does not resurrect cancelled delegation
    mgr.update_temporal_status(del_rec["delegation_id"], base_time + timedelta(hours=3))
    assert del_rec["status"] == DelegationState.CANCELLED

    is_valid, reason, _ = mgr.is_valid_for_action("pharmacy_shared", "EMP007", base_time + timedelta(hours=3))
    assert not is_valid
    assert reason == "DELEGATION_CANCELLED"


def test_delegation_boundary_timestamps():
    """Verify boundary conditions: exact start_time and exact end_time are authorized."""
    mgr = DelegationLifecycleManager()
    start_t = datetime(2026, 9, 1, 8, 0, 0)
    end_t = datetime(2026, 9, 1, 16, 0, 0)
    mgr.create_delegation("ward_shared", "EMP011", start_t, end_t, current_time=start_t)

    # Exact start
    valid_start, _, _ = mgr.is_valid_for_action("ward_shared", "EMP011", start_t)
    assert valid_start

    # Exact end
    valid_end, _, _ = mgr.is_valid_for_action("ward_shared", "EMP011", end_t)
    assert valid_end

    # 1 second before start
    valid_pre, _, _ = mgr.is_valid_for_action("ward_shared", "EMP011", start_t - timedelta(seconds=1))
    assert not valid_pre

    # 1 second after end
    valid_post, reason_post, _ = mgr.is_valid_for_action("ward_shared", "EMP011", end_t + timedelta(seconds=1))
    assert not valid_post
    assert reason_post == "DELEGATION_EXPIRED"
