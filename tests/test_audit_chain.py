import os
import sys
import copy
import pytest
from datetime import datetime, timedelta

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from src.audit_chain import TamperEvidentAuditTrail


def test_audit_chain_valid_append_and_verification():
    """Verify that sequentially appended records form a mathematically valid cryptographic chain."""
    ledger = TamperEvidentAuditTrail()
    now = datetime(2026, 9, 1, 10, 0, 0)

    ledger.append("EMP003", "EVT-001", "LOGIN", "Workstation login", now)
    ledger.append("EMP003", "EVT-002", "VIEW_PATIENT_RECORD", "Accessed SYN-PAT-1082", now + timedelta(minutes=5))
    ledger.append("EMP003", "EVT-003", "EDIT_PATIENT_RECORD", "Updated clinical notes", now + timedelta(minutes=10))

    is_valid, reason, bad_idx = ledger.verify_chain()
    assert is_valid
    assert reason == "CHAIN_VALID"
    assert bad_idx is None
    assert len(ledger.chain) == 3


def test_audit_chain_detects_modified_record():
    """Verify that tampering with any field in a historical record breaks record_hash validation."""
    ledger = TamperEvidentAuditTrail()
    now = datetime(2026, 9, 1, 10, 0, 0)

    ledger.append("EMP003", "EVT-001", "LOGIN", "Workstation login", now)
    ledger.append("EMP003", "EVT-002", "VIEW_PATIENT_RECORD", "Accessed SYN-PAT-1082", now + timedelta(minutes=5))

    # Malicious actor tampers with details of record 0 to disguise activity
    ledger.chain[0].details = "Harmless ping action"

    is_valid, reason, bad_idx = ledger.verify_chain()
    assert not is_valid
    assert "TAMPERED_RECORD" in reason
    assert bad_idx == 0


def test_audit_chain_detects_broken_previous_hash_link():
    """Verify that altering previous_hash breaks the cryptographic pointer."""
    ledger = TamperEvidentAuditTrail()
    now = datetime(2026, 9, 1, 10, 0, 0)

    ledger.append("EMP003", "EVT-001", "LOGIN", "Login", now)
    ledger.append("EMP003", "EVT-002", "ACTION", "Action", now + timedelta(minutes=1))

    # Break previous_hash link
    ledger.chain[1].previous_hash = "f" * 64

    is_valid, reason, bad_idx = ledger.verify_chain()
    assert not is_valid
    assert "BROKEN_CHAIN" in reason
    assert bad_idx == 1


def test_audit_chain_detects_deleted_or_reordered_record():
    """Verify that deleting an intermediate record breaks the previous_hash link of following records."""
    ledger = TamperEvidentAuditTrail()
    now = datetime(2026, 9, 1, 10, 0, 0)

    ledger.append("EMP003", "EVT-001", "LOGIN", "Login", now)
    ledger.append("EMP003", "EVT-002", "VIEW_RECORD", "Viewed ePHI", now + timedelta(minutes=2))
    ledger.append("EMP003", "EVT-003", "EXPORT_RECORD", "Exported ePHI", now + timedelta(minutes=4))

    # Delete intermediate record EVT-002
    del ledger.chain[1]

    is_valid, reason, bad_idx = ledger.verify_chain()
    assert not is_valid
    assert "BROKEN_CHAIN" in reason
    assert bad_idx == 1  # Record 2 now at index 1 does not link to Record 1's hash
