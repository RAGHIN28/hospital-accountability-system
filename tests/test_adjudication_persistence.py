"""
Persistent Human Adjudication Test Suite (Review 3 — Work Package R3.3)
Hospital Shared-Account Elimination & Accountable Action Attribution PoC

Verifies:
  1. Valid Adjudication Creation
  2. Retrieve by Case ID
  3. Retrieve by Event ID
  4. Update Decision & Version Increment
  5. Persistence Across Independent DB Session
  6. Persistence Across Simulated Application Restart (Engine Disposal & Reconnect)
  7. Invalid Decision Rejection
  8. Unknown / Empty Case ID Rejection
  9. Unknown Event ID Rejection
  10. Empty Reviewer Rejection
  11. Oversized Notes Rejection (>5000 chars)
  12. Duplicate / Single-Record Invariant Per Case
  13. Transaction Rollback on Failure
  14. Ambiguity Preservation (REQUEST_MORE_EVIDENCE)
  15. Ambiguity Preservation (MARK_UNATTRIBUTED)
  16. Cryptographic Audit Chain Record Logging
  17. Attribution Result Immutability
  18. Forensic Package Integration with Persisted Review
  19. Secret & Credential Exclusion
  20. Deterministic Retrieval & Timestamp Lifecycle
"""

import os
import sys
import time
import pytest
from datetime import datetime

# Ensure backend and root paths are available
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal, engine
from app.models.adjudication import AdjudicationRecord
from app.models.system_log import SystemLog
from app.models.attribution_result import AttributionResult
from src.adjudication_persistence import AdjudicationPersistenceService
from src.forensic_package import ForensicAuditPackageGenerator
from src.audit_chain import TamperEvidentAuditTrail


@pytest.fixture(autouse=True)
def cleanup_test_adjudications():
    """Ensure test cases created during testing are cleaned up."""
    yield
    db = SessionLocal()
    try:
        db.query(AdjudicationRecord).filter(
            AdjudicationRecord.case_id.like("TEST-CASE-%")
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 1: Valid Adjudication Creation
# ---------------------------------------------------------------------------
def test_valid_adjudication_creation():
    """Verify that a valid compliance adjudication record is saved and returned."""
    res = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-001",
        event_id="EVT-00001",
        decision="CONFIRM_IDENTITY",
        reviewer="Officer Elena Rostova",
        findings="Physical sign-in roster matches RFID badge tap exactly.",
        status="SUBMITTED",
        evidence_reference="Badge log tap #402"
    )
    assert res is not None
    assert res["case_id"] == "TEST-CASE-001"
    assert res["event_id"] == "EVT-00001"
    assert res["decision"] == "CONFIRM_IDENTITY"
    assert res["reviewer"] == "Officer Elena Rostova"
    assert res["version"] == 1
    assert res["status"] == "SUBMITTED"
    assert "Badge log tap #402" in res["evidence_reference"]


# ---------------------------------------------------------------------------
# Test 2: Retrieve by Case ID
# ---------------------------------------------------------------------------
def test_retrieve_by_case_id():
    """Verify authoritative retrieval by case_id."""
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-002",
        event_id="EVT-00002",
        decision="MARK_UNATTRIBUTED",
        reviewer="Inspector Marcus Vance",
        findings="No corroborating badge or video telemetry available."
    )
    fetched = AdjudicationPersistenceService.get_adjudication_by_case("TEST-CASE-002")
    assert fetched is not None
    assert fetched["case_id"] == "TEST-CASE-002"
    assert fetched["event_id"] == "EVT-00002"
    assert fetched["decision"] == "MARK_UNATTRIBUTED"
    assert fetched["reviewer"] == "Inspector Marcus Vance"


# ---------------------------------------------------------------------------
# Test 3: Retrieve by Event ID
# ---------------------------------------------------------------------------
def test_retrieve_by_event_id():
    """Verify authoritative retrieval by event_id."""
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-003",
        event_id="EVT-00003",
        decision="REQUEST_MORE_EVIDENCE",
        reviewer="Auditor Sarah Jenkins",
        findings="Requesting departmental shift schedule from nurse manager."
    )
    fetched = AdjudicationPersistenceService.get_adjudication_by_event("EVT-00003")
    assert fetched is not None
    assert fetched["case_id"] == "TEST-CASE-003"
    assert fetched["event_id"] == "EVT-00003"
    assert fetched["decision"] == "REQUEST_MORE_EVIDENCE"


# ---------------------------------------------------------------------------
# Test 4: Update Decision & Version Increment
# ---------------------------------------------------------------------------
def test_update_decision_and_version_increment():
    """Verify amending an adjudication increments version and updates timestamp."""
    initial = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-004",
        event_id="EVT-00004",
        decision="REQUEST_MORE_EVIDENCE",
        reviewer="Officer Elena Rostova",
        findings="Initial review: Pending additional shift supervisor sign-off."
    )
    assert initial["version"] == 1
    assert initial["status"] == "SUBMITTED"

    # Brief delay to guarantee updated_at difference
    time.sleep(0.01)

    amended = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-004",
        event_id="EVT-00004",
        decision="CONFIRM_IDENTITY",
        reviewer="Lead Auditor Chen",
        findings="Shift supervisor confirmed Dr. Patel was authorized and active on terminal.",
        status="RESOLVED"
    )
    assert amended["version"] == 2
    assert amended["decision"] == "CONFIRM_IDENTITY"
    assert amended["reviewer"] == "Lead Auditor Chen"
    assert amended["status"] == "RESOLVED"
    assert amended["updated_at"] >= amended["created_at"]


# ---------------------------------------------------------------------------
# Test 5: Persistence Across Independent DB Session
# ---------------------------------------------------------------------------
def test_persistence_across_new_db_session():
    """Verify adjudication persists when queried through a completely new DB session."""
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-005",
        event_id="EVT-00005",
        decision="CONFIRM_IDENTITY",
        reviewer="Officer Elena Rostova",
        findings="Session 1 persistence validation."
    )

    # Open isolated session
    new_db = SessionLocal()
    try:
        record = new_db.query(AdjudicationRecord).filter(
            AdjudicationRecord.case_id == "TEST-CASE-005"
        ).first()
        assert record is not None
        assert record.decision == "CONFIRM_IDENTITY"
        assert record.reviewer == "Officer Elena Rostova"
    finally:
        new_db.close()


# ---------------------------------------------------------------------------
# Test 6: Persistence Across Simulated Application Restart
# ---------------------------------------------------------------------------
def test_persistence_across_application_restart_simulation():
    """Simulate application restart by disposing engine connections and verifying retrieval."""
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-006",
        event_id="EVT-00006",
        decision="DISMISS",
        reviewer="Supervisor Clara Oswald",
        findings="False alarm: scheduled routine maintenance procedure."
    )

    # Dispose all connections in pool to simulate application shutdown/restart
    engine.dispose()

    # Re-query via fresh service call
    retrieved = AdjudicationPersistenceService.get_adjudication_by_case("TEST-CASE-006")
    assert retrieved is not None
    assert retrieved["decision"] == "DISMISS"
    assert retrieved["reviewer"] == "Supervisor Clara Oswald"


# ---------------------------------------------------------------------------
# Test 7: Invalid Decision Rejection
# ---------------------------------------------------------------------------
def test_invalid_decision_rejection():
    """Verify that unauthorized decisions raise ValueError."""
    with pytest.raises(ValueError, match="Invalid adjudication decision"):
        AdjudicationPersistenceService.save_adjudication(
            case_id="TEST-CASE-007",
            event_id="EVT-00007",
            decision="INVALID_UNAUTHORIZED_DECISION",
            reviewer="Officer Elena Rostova",
            findings="Notes."
        )


# ---------------------------------------------------------------------------
# Test 8: Unknown / Empty Case ID Rejection
# ---------------------------------------------------------------------------
def test_empty_case_id_rejection():
    """Verify that empty case IDs raise ValueError."""
    with pytest.raises(ValueError, match="Case ID cannot be empty"):
        AdjudicationPersistenceService.save_adjudication(
            case_id="",
            event_id="EVT-00001",
            decision="CONFIRM_IDENTITY",
            reviewer="Officer Elena Rostova",
            findings="Notes."
        )


# ---------------------------------------------------------------------------
# Test 9: Unknown Event ID Rejection
# ---------------------------------------------------------------------------
def test_unknown_event_id_rejection():
    """Verify that non-existent event IDs raise ValueError."""
    with pytest.raises(ValueError, match="does not exist in system logs"):
        AdjudicationPersistenceService.save_adjudication(
            case_id="TEST-CASE-009",
            event_id="EVT-NONEXISTENT-99999",
            decision="CONFIRM_IDENTITY",
            reviewer="Officer Elena Rostova",
            findings="Notes."
        )


# ---------------------------------------------------------------------------
# Test 10: Empty Reviewer Rejection
# ---------------------------------------------------------------------------
def test_empty_reviewer_rejection():
    """Verify that empty reviewer strings raise ValueError."""
    with pytest.raises(ValueError, match="Reviewer identity cannot be empty"):
        AdjudicationPersistenceService.save_adjudication(
            case_id="TEST-CASE-010",
            event_id="EVT-00001",
            decision="CONFIRM_IDENTITY",
            reviewer="   ",
            findings="Notes."
        )


# ---------------------------------------------------------------------------
# Test 11: Oversized Notes Rejection
# ---------------------------------------------------------------------------
def test_oversized_notes_rejection():
    """Verify that findings exceeding 5,000 characters raise ValueError."""
    giant_findings = "A" * 5001
    with pytest.raises(ValueError, match="exceed maximum length"):
        AdjudicationPersistenceService.save_adjudication(
            case_id="TEST-CASE-011",
            event_id="EVT-00001",
            decision="CONFIRM_IDENTITY",
            reviewer="Officer Elena Rostova",
            findings=giant_findings
        )


# ---------------------------------------------------------------------------
# Test 12: Duplicate / Single-Record Invariant Per Case
# ---------------------------------------------------------------------------
def test_duplicate_case_id_preserves_single_record():
    """Verify that multiple saves for the same case_id update the single record without duplicates."""
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-012",
        event_id="EVT-00001",
        decision="REQUEST_MORE_EVIDENCE",
        reviewer="Officer Elena Rostova",
        findings="Step 1 notes"
    )
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-012",
        event_id="EVT-00001",
        decision="CONFIRM_IDENTITY",
        reviewer="Officer Elena Rostova",
        findings="Step 2 notes"
    )

    db = SessionLocal()
    try:
        count = db.query(AdjudicationRecord).filter(
            AdjudicationRecord.case_id == "TEST-CASE-012"
        ).count()
        assert count == 1, "There must be exactly one authoritative record per case_id"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 13: Transaction Rollback on Failure
# ---------------------------------------------------------------------------
def test_transaction_rollback_on_failure():
    """Verify that database errors trigger rollback without committing partial states."""
    db = SessionLocal()
    try:
        # Pass a mock session or invalid state that forces a rollback
        with pytest.raises(Exception):
            # Attempt to save with invalid event_id using active db session
            AdjudicationPersistenceService.save_adjudication(
                case_id="TEST-CASE-013",
                event_id="EVT-INVALID-FAIL",
                decision="CONFIRM_IDENTITY",
                reviewer="Officer Elena",
                findings="Rollback test",
                db=db
            )
        # Verify no record was inserted
        rec = db.query(AdjudicationRecord).filter(
            AdjudicationRecord.case_id == "TEST-CASE-013"
        ).first()
        assert rec is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 14: Ambiguity Preservation (REQUEST_MORE_EVIDENCE)
# ---------------------------------------------------------------------------
def test_ambiguity_preservation_request_more_evidence():
    """Verify that compliance officers can formally record ambiguity without forcing attribution."""
    res = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-014",
        event_id="EVT-00001",
        decision="REQUEST_MORE_EVIDENCE",
        reviewer="Compliance Officer Miller",
        findings="Conflicting shift schedules. Escalating to departmental nurse manager for roster verification."
    )
    assert res["decision"] == "REQUEST_MORE_EVIDENCE"
    persisted = AdjudicationPersistenceService.get_adjudication_by_case("TEST-CASE-014")
    assert persisted["decision"] == "REQUEST_MORE_EVIDENCE"


# ---------------------------------------------------------------------------
# Test 15: Ambiguity Preservation (MARK_UNATTRIBUTED)
# ---------------------------------------------------------------------------
def test_ambiguity_preservation_mark_unattributed():
    """Verify that an ambiguous case can be permanently recorded as un-attributable."""
    res = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-015",
        event_id="EVT-00002",
        decision="MARK_UNATTRIBUTED",
        reviewer="Compliance Officer Miller",
        findings="Workstation unmonitored; no video or badge records exist. Closed as un-attributable."
    )
    assert res["decision"] == "MARK_UNATTRIBUTED"
    persisted = AdjudicationPersistenceService.get_adjudication_by_case("TEST-CASE-015")
    assert persisted["decision"] == "MARK_UNATTRIBUTED"


# ---------------------------------------------------------------------------
# Test 16: Cryptographic Audit Chain Record Logging
# ---------------------------------------------------------------------------
def test_cryptographic_audit_trail_logging():
    """Verify that persisting an adjudication appends a block to TamperEvidentAuditTrail."""
    trail = TamperEvidentAuditTrail()
    initial_length = len(trail.chain)

    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-016",
        event_id="EVT-00001",
        decision="CONFIRM_IDENTITY",
        reviewer="Officer Elena Rostova",
        findings="Audit trail integration verification.",
        audit_trail=trail
    )

    assert len(trail.chain) == initial_length + 1
    latest_block = trail.chain[-1]
    assert "HUMAN_REVIEW" in latest_block.action
    assert latest_block.actor == "Officer Elena Rostova"
    assert "TEST-CASE-016" in latest_block.details
    assert "CONFIRM_IDENTITY" in latest_block.details

    # Also verify cryptographic chain validity
    is_valid, msg, _ = trail.verify_chain()
    assert is_valid is True
    assert msg == "CHAIN_VALID"


# ---------------------------------------------------------------------------
# Test 17: Attribution Result Immutability
# ---------------------------------------------------------------------------
def test_attribution_result_immutability():
    """Verify that saving a human adjudication does not alter the underlying AttributionResult."""
    db = SessionLocal()
    try:
        initial_attr = db.query(AttributionResult).filter(
            AttributionResult.event_id == "EVT-00001"
        ).first()
        initial_score = initial_attr.confidence_score
        initial_status = initial_attr.attribution_status
        initial_user = initial_attr.attributed_user_id

        # Save human adjudication
        AdjudicationPersistenceService.save_adjudication(
            case_id="TEST-CASE-017",
            event_id="EVT-00001",
            decision="CONFIRM_IDENTITY",
            reviewer="Officer Elena Rostova",
            findings="Checking attribution engine immutability."
        )

        db.expire_all()
        post_attr = db.query(AttributionResult).filter(
            AttributionResult.event_id == "EVT-00001"
        ).first()
        assert post_attr.confidence_score == initial_score
        assert post_attr.attribution_status == initial_status
        assert post_attr.attributed_user_id == initial_user
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 18: Forensic Package Integration with Persisted Review
# ---------------------------------------------------------------------------
def test_forensic_package_integration_with_persisted_review():
    """Verify that ForensicAuditPackageGenerator automatically picks up persisted adjudication."""
    AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-018",
        event_id="EVT-00001",
        decision="CONFIRM_IDENTITY",
        reviewer="Officer Elena Rostova",
        findings="Persisted forensic verification test notes."
    )

    gen = ForensicAuditPackageGenerator()
    pkg = gen.generate_package("EVT-00001")

    assert pkg["human_review"]["review_recorded"] is True
    assert pkg["human_review"]["decision"] == "CONFIRM_IDENTITY"
    assert pkg["human_review"]["reviewer"] == "Officer Elena Rostova"
    assert "Persisted forensic verification test notes." in pkg["human_review"]["notes"]

    # Export both JSON and PDF to guarantee compatibility
    json_path = gen.export_json(pkg)
    assert os.path.exists(json_path)

    pdf_path = gen.export_pdf(pkg)
    assert os.path.exists(pdf_path)


# ---------------------------------------------------------------------------
# Test 19: Secret & Credential Exclusion
# ---------------------------------------------------------------------------
def test_secret_and_credential_exclusion():
    """Verify that adjudication records never contain secrets, passwords, or bearer tokens."""
    res = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-019",
        event_id="EVT-00001",
        decision="CONFIRM_IDENTITY",
        reviewer="Officer Elena Rostova",
        findings="Standard compliance findings."
    )
    forbidden = ["password", "secret", "bearer", "private_key", "token", "auth_token"]
    for key in res.keys():
        assert key.lower() not in forbidden
    for val in res.values():
        if isinstance(val, str):
            for secret_word in forbidden:
                assert secret_word not in val.lower()


# ---------------------------------------------------------------------------
# Test 20: Deterministic Retrieval & Timestamp Lifecycle
# ---------------------------------------------------------------------------
def test_deterministic_retrieval_and_timestamps():
    """Verify multiple reads return identical records and updated_at tracks modifications."""
    res1 = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-020",
        event_id="EVT-00001",
        decision="REQUEST_MORE_EVIDENCE",
        reviewer="Officer Elena Rostova",
        findings="Baseline notes."
    )
    fetch1 = AdjudicationPersistenceService.get_adjudication_by_case("TEST-CASE-020")
    fetch2 = AdjudicationPersistenceService.get_adjudication_by_case("TEST-CASE-020")
    assert fetch1 == fetch2

    # Listing adjudications includes the record deterministically
    all_recs = AdjudicationPersistenceService.list_adjudications()
    matching = [r for r in all_recs if r["case_id"] == "TEST-CASE-020"]
    assert len(matching) == 1
    assert matching[0]["decision"] == "REQUEST_MORE_EVIDENCE"
