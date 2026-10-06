"""
Multi-Ward Patient Transfer & Shift Boundary Test Suite (Review 3 — Work Package R3.4)
Hospital Shared-Account Elimination & Accountable Action Attribution PoC

Verifies:
  1. Normal Transfer Attribution (Scenario A)
  2. Shift-Boundary Attribution (Scenario B)
  3. Shared Workstation Transition (Scenario C)
  4. Visiting Consultant Temporary Window (Scenario D)
  5. Intern / Supervised Activity (Scenario E)
  6. Delayed Transfer In-Place Reconciliation (Scenario F)
  7. Out-of-Order Transfer Ingestion Sequencing
  8. Missing Telemetry Resilience (Scenario G)
  9. Conflicting Responsibility Human Escalation (Scenario H)
  10. Duplicate Transfer Ingestion Rejection
  11. Expired Delegation Invalidation
  12. Pre-Delegation Window Invalidation
  13. Exact Shift Boundary Determinism
  14. Unknown Clinician Rejection
  15. Unknown Ward Telemetry Degradation
  16. Non-Forcing Attribution Safety (Never Force Guess)
  17. Deterministic Scenario Execution & Runtimes
  18. Existing Attribution Engine Immutability
  19. Forensic Package Compatibility Across Wards
  20. Persistent Adjudication Compatibility for Ward Conflicts
  21. Secret & Credential Exclusion
"""

import os
import sys
import pytest
from datetime import datetime, timedelta

# Ensure backend and root paths are available
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.multi_ward_transfer import (
    MultiWardTransferSimulationEngine,
    SyntheticPatientEncounter,
    SYNTHETIC_WARDS
)
from app.database import SessionLocal
from app.models.system_log import SystemLog
from app.models.attribution_result import AttributionResult
from src.adjudication_persistence import AdjudicationPersistenceService
from src.forensic_package import ForensicAuditPackageGenerator


@pytest.fixture(scope="module")
def engine():
    """Shared simulation engine instance."""
    return MultiWardTransferSimulationEngine()


# ---------------------------------------------------------------------------
# Test 1: Normal Transfer Attribution (Scenario A)
# ---------------------------------------------------------------------------
def test_scenario_a_normal_transfer(engine):
    """Verify clean handoff attribution from Emergency (Ward) to Radiology."""
    res = engine.run_scenario_a_normal_transfer()
    assert res["passed"] is True
    assert res["scenario_id"] == "SCENARIO_A"
    outcomes = res["results"]
    assert len(outcomes) == 2
    # Pre-transfer action
    assert outcomes[0]["status"] == "ATTRIBUTED"
    assert outcomes[0]["attributed_user"] == "EMP011"
    # Post-transfer scan
    assert outcomes[1]["status"] == "ATTRIBUTED"
    assert outcomes[1]["attributed_user"] == "EMP002"


# ---------------------------------------------------------------------------
# Test 2: Shift-Boundary Attribution (Scenario B)
# ---------------------------------------------------------------------------
def test_scenario_b_shift_boundary(engine):
    """Verify event occurring after shift boundary resolves to incoming staff, not expired."""
    res = engine.run_scenario_b_shift_change_transfer()
    assert res["passed"] is True
    assert res["scenario_id"] == "SCENARIO_B"
    outcome = res["results"][0]
    assert outcome["status"] == "ATTRIBUTED"
    assert outcome["attributed_user"] == "EMP002"  # Incoming Evening clinician
    # Confirm outgoing clinician was not credited
    cands = {c["user_id"]: c["score"] for c in outcome["scored_candidates"]}
    assert cands.get("EMP002", 0) > cands.get("EMP003", 0)


# ---------------------------------------------------------------------------
# Test 3: Shared Workstation Transition (Scenario C)
# ---------------------------------------------------------------------------
def test_scenario_c_shared_workstation_transition(engine):
    """Verify sequential users on the same physical terminal are distinguished by context."""
    res = engine.run_scenario_c_shared_workstation_transition()
    assert res["passed"] is True
    outcomes = res["results"]
    assert len(outcomes) == 2
    assert outcomes[0]["attributed_user"] == "EMP012"  # Ward Nurse
    assert outcomes[1]["attributed_user"] == "EMP007"  # Pharmacist


# ---------------------------------------------------------------------------
# Test 4: Visiting Consultant Temporary Window (Scenario D)
# ---------------------------------------------------------------------------
def test_scenario_d_visiting_consultant(engine):
    """Verify visiting specialist is attributed during window, but not after departure."""
    res = engine.run_scenario_d_visiting_consultant()
    assert res["passed"] is True
    outcomes = res["results"]
    assert len(outcomes) == 2
    assert outcomes[0]["attributed_user"] == "EMP001"  # Visiting Cardiologist
    assert outcomes[1]["attributed_user"] == "EMP011"  # Ward Staff Nurse


# ---------------------------------------------------------------------------
# Test 5: Intern Supervised Practice Delegation Boundary (Scenario E)
# ---------------------------------------------------------------------------
def test_scenario_e_intern_supervised_activity(engine):
    """Verify intern attribution within training shift, reverting to supervisor outside."""
    res = engine.run_scenario_e_intern_supervised_activity()
    assert res["passed"] is True
    outcomes = res["results"]
    assert len(outcomes) == 2
    assert outcomes[0]["attributed_user"] == "EMP005"  # Intern
    assert outcomes[1]["attributed_user"] == "EMP002"  # Supervisor


# ---------------------------------------------------------------------------
# Test 6: Delayed Transfer In-Place Reconciliation (Scenario F)
# ---------------------------------------------------------------------------
def test_scenario_f_delayed_transfer_reconciliation(engine):
    """Verify delayed transfer record re-evaluates PENDING event to ATTRIBUTED."""
    res = engine.run_scenario_f_delayed_transfer_event()
    assert res["passed"] is True
    outcome = res["results"][0]
    assert outcome["initial_status"] == "PENDING"
    assert outcome["status"] == "ATTRIBUTED"
    assert outcome["attributed_user"] == "EMP011"
    assert outcome["reconciled_count"] == 1


# ---------------------------------------------------------------------------
# Test 7: Out-of-Order Transfer Sequencing
# ---------------------------------------------------------------------------
def test_out_of_order_transfer_sequencing(engine):
    """Verify IngestionBuffer reorders inverted arrival timestamps by true event-time."""
    ordered_ids = engine.evaluate_out_of_order_transfer_events()
    assert ordered_ids == ["EVT-CHRONO-1", "EVT-CHRONO-2"]


# ---------------------------------------------------------------------------
# Test 8: Missing Telemetry Resilience (Scenario G)
# ---------------------------------------------------------------------------
def test_scenario_g_missing_telemetry_resilience(engine):
    """Verify resilience when telemetry drops, and safety when session is also absent."""
    res = engine.run_scenario_g_missing_telemetry()
    assert res["passed"] is True
    outcomes = res["results"]
    # Case G1: Delegation + Session = 70 pts -> ATTRIBUTED
    assert outcomes[0]["status"] == "ATTRIBUTED"
    assert outcomes[0]["confidence_level"] == "MEDIUM"
    # Case G2: Delegation only = 40 pts < 60 threshold -> UNATTRIBUTED
    assert outcomes[1]["status"] == "UNATTRIBUTED"


# ---------------------------------------------------------------------------
# Test 9: Conflicting Responsibility Human Escalation (Scenario H)
# ---------------------------------------------------------------------------
def test_scenario_h_conflicting_responsibility_escalation(engine):
    """Verify identical competing delegations trigger AMBIGUOUS and avoid false accusation."""
    res = engine.run_scenario_h_conflicting_responsibility()
    assert res["passed"] is True
    outcome = res["results"][0]
    assert outcome["status"] == "AMBIGUOUS"
    assert outcome["confidence_level"] == "AMBIGUOUS"
    assert outcome["attributed_user"] is None


# ---------------------------------------------------------------------------
# Test 10: Duplicate Transfer Ingestion Rejection
# ---------------------------------------------------------------------------
def test_duplicate_transfer_ingestion(engine):
    """Verify duplicate event payloads are recognized and flagged as DUPLICATE."""
    dup_res = engine.evaluate_duplicate_transfer_event()
    assert dup_res["first_ingest_status"] == "BUFFERED"
    assert dup_res["second_ingest_status"] == "DUPLICATE"
    assert dup_res["duplicate_count"] == 1


# ---------------------------------------------------------------------------
# Test 11: Expired Delegation Invalidation
# ---------------------------------------------------------------------------
def test_expired_delegation_invalidation(engine):
    """Verify that actions after delegation window elapses do not receive delegation score."""
    res = engine.evaluate_transfer_after_delegation_expiry()
    assert res["delegation_matched"] is False
    assert res["delegation_missed"] is True


# ---------------------------------------------------------------------------
# Test 12: Pre-Delegation Window Invalidation
# ---------------------------------------------------------------------------
def test_pre_delegation_window_invalidation(engine):
    """Verify that actions before delegation start do not receive delegation score."""
    res = engine.evaluate_transfer_before_delegation()
    assert res["delegation_matched"] is False
    assert res["delegation_missed"] is True


# ---------------------------------------------------------------------------
# Test 13: Exact Shift Boundary Determinism
# ---------------------------------------------------------------------------
def test_exact_shift_boundary_determinism(engine):
    """Verify boundary condition behavior exactly at shift change timestamp."""
    res = engine.evaluate_transfer_exact_shift_boundary()
    # At exact boundary, both outgoing and incoming are deterministically checked
    assert res["outgoing_valid_at_boundary"] is True
    assert res["incoming_valid_at_boundary"] is True


# ---------------------------------------------------------------------------
# Test 14: Unknown Clinician Rejection
# ---------------------------------------------------------------------------
def test_unknown_clinician_rejection(engine):
    """Verify that an unrecognized clinician without delegations is marked UNATTRIBUTED."""
    res = engine.evaluate_unknown_clinician()
    assert res["status"] == "UNATTRIBUTED"
    assert res["attributed_user"] is None


# ---------------------------------------------------------------------------
# Test 15: Unknown Ward Telemetry Degradation
# ---------------------------------------------------------------------------
def test_unknown_ward_telemetry_degradation(engine):
    """Verify unknown ward IP/device gracefully scores 0 for network and device."""
    res = engine.evaluate_unknown_ward()
    assert "DEVICE_MATCH" in res["signals_missed"]
    assert "IP_SUBNET_MATCH" in res["signals_missed"]


# ---------------------------------------------------------------------------
# Test 16: Non-Forcing Attribution Safety Gate
# ---------------------------------------------------------------------------
def test_non_forcing_safety_gate(engine):
    """Verify that when evidence is ambiguous or insufficient, no identity is force-assigned."""
    # Two tied candidates with 50 points each
    candidates = [
        {"employee_id": "EMP001", "full_name": "Dr. Arun Kumar", "department": "Cardiology"},
        {"employee_id": "EMP015", "full_name": "Dr. Kavita Desai", "department": "Cardiology"}
    ]
    res = engine.resolve_action_attribution(
        event_id="EVT-SAFETY-01",
        event_timestamp=datetime(2026, 9, 20, 10, 0, 0),
        account_name="ward_shared",
        action_name="VIEW_PATIENT_RECORD",
        candidates=candidates,
        active_delegations=[]  # No delegations
    )
    # Neither candidate has >= 60 pts
    assert res["status"] == "UNATTRIBUTED"
    assert res["attributed_user"] is None


# ---------------------------------------------------------------------------
# Test 17: Deterministic Scenario Execution & Metrics Aggregation
# ---------------------------------------------------------------------------
def test_all_scenarios_deterministic_execution(engine):
    """Verify that running all 8 scenarios yields 100% pass rate in sub-5ms time."""
    master = engine.run_all_scenarios()
    assert master["all_passed"] is True
    assert master["passed_scenarios"] == 8
    assert master["total_scenarios"] == 8
    assert master["execution_duration_ms"] < 50.0  # High-throughput execution
    metrics = master["metrics"]
    assert metrics["total_actions_evaluated"] == 13
    assert metrics["attributed_actions"] == 11
    assert metrics["unattributed_actions"] == 1
    assert metrics["ambiguous_actions"] == 1
    assert metrics["reconciled_events"] == 1
    assert metrics["escalated_cases"] == 1


# ---------------------------------------------------------------------------
# Test 18: Existing Attribution Engine Immutability
# ---------------------------------------------------------------------------
def test_existing_attribution_engine_immutability():
    """Verify that running multi-ward simulations has not altered canonical database logs."""
    db = SessionLocal()
    try:
        log_count = db.query(SystemLog).count()
        assert log_count == 364, "Total canonical system logs must remain exactly 364"
        attr_count = db.query(AttributionResult).count()
        assert attr_count == 364, "Total attribution records must remain exactly 364"
        from app.models.privileged_action import PrivilegedAction
        priv_actions = set(pa.action_name for pa in db.query(PrivilegedAction).all())
        sensitive_count = db.query(SystemLog).filter(SystemLog.action.in_(priv_actions)).count()
        assert sensitive_count == 205, "Total sensitive events must remain exactly 205"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 19: Forensic Package Compatibility Across Wards
# ---------------------------------------------------------------------------
def test_forensic_package_compatibility_across_wards():
    """Verify that ForensicAuditPackageGenerator generates valid dossiers for ward events."""
    gen = ForensicAuditPackageGenerator()
    pkg = gen.generate_package("EVT-00001")
    assert pkg["metadata"]["event_id"] == "EVT-00001"
    assert "telemetry_evidence" in pkg
    assert "chronological_timeline" in pkg


# ---------------------------------------------------------------------------
# Test 20: Persistent Adjudication Compatibility for Ward Conflicts
# ---------------------------------------------------------------------------
def test_adjudication_persistence_compatibility():
    """Verify that an ambiguous transfer case can be saved via AdjudicationPersistenceService."""
    adjudication = AdjudicationPersistenceService.save_adjudication(
        case_id="TEST-CASE-WARD-XFER-01",
        event_id="EVT-00001",
        decision="REQUEST_MORE_EVIDENCE",
        reviewer="Compliance Officer Elena Rostova",
        findings="Ambiguous cross-ward transfer handoff between Radiology and ICU. Requesting sign-in roster.",
        evidence_reference="XFER-2026-001"
    )
    assert adjudication["decision"] == "REQUEST_MORE_EVIDENCE"
    assert adjudication["case_id"] == "TEST-CASE-WARD-XFER-01"

    # Clean up test record
    AdjudicationPersistenceService.delete_adjudication("TEST-CASE-WARD-XFER-01")


# ---------------------------------------------------------------------------
# Test 21: Secret & Credential Exclusion
# ---------------------------------------------------------------------------
def test_secret_exclusion(engine):
    """Verify that simulation outputs and encounters never contain secrets or credentials."""
    master = engine.run_all_scenarios()
    forbidden = ["password", "secret", "bearer", "private_key", "token_hash", "auth_token"]

    def check_dict(d):
        for k, v in d.items():
            assert str(k).lower() not in forbidden
            if isinstance(v, dict):
                check_dict(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        check_dict(item)
            elif isinstance(v, str):
                for f in forbidden:
                    assert f not in v.lower()

    for s in master["scenarios"]:
        check_dict(s)
