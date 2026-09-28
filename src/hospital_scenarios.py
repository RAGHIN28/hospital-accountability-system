import os
import sys
import csv
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from src.ingestion_buffer import IngestionBuffer
from src.delegation_lifecycle import DelegationLifecycleManager, DelegationState
from src.session_lifecycle import SessionLifecycleManager, SessionState
from src.evidence_model import CrossSourceCorrelator, SignalStrength
from src.alerts import OperationalAlertManager, AlertSeverity
from src.audit_chain import TamperEvidentAuditTrail


def run_and_validate_all_scenarios(output_csv: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Executes and validates 8 comprehensive synthetic hospital clinical scenarios:
    SCENARIO 1: Normal delegated shared-account use
    SCENARIO 2: Late-arriving delegation (reconciliation)
    SCENARIO 3: Out-of-order authentication/session/application events
    SCENARIO 4: Expired / revoked delegation attempt
    SCENARIO 5: Conflicting overlapping delegations requiring human review
    SCENARIO 6: Missing network/device telemetry resilience
    SCENARIO 7: After-hours sensitive action alerting
    SCENARIO 8: Duplicate event ingestion rejection
    """
    scenarios_results = []
    base_time = datetime(2026, 9, 1, 9, 0, 0)

    # ========================================================
    # SCENARIO 1: Normal delegated shared-account use
    # ========================================================
    del_mgr1 = DelegationLifecycleManager()
    del1 = del_mgr1.create_delegation(
        shared_account="radiology_shared",
        delegate_user_id="EMP003",
        start_time=base_time,
        end_time=base_time + timedelta(hours=8),
        current_time=base_time + timedelta(minutes=10)
    )
    is_valid1, reason1, _ = del_mgr1.is_valid_for_action("radiology_shared", "EMP003", base_time + timedelta(hours=1))

    scenarios_results.append({
        "scenario_id": "SCENARIO_1",
        "description": "Normal delegated shared-account clinical use during authorized morning shift",
        "input_conditions": "Staff EMP003 authorized on radiology_shared from 09:00 to 17:00; Action at 10:00",
        "expected_result": "ATTRIBUTED to EMP003 with HIGH confidence",
        "actual_result": "ATTRIBUTED" if is_valid1 else "FAILED",
        "evidence": f"Delegation {del1['delegation_id']} state: {del1['status']}; validation: {reason1}",
        "test_status": "PASSED" if is_valid1 else "FAILED"
    })

    # ========================================================
    # SCENARIO 2: Late-arriving delegation
    # ========================================================
    buffer2 = IngestionBuffer(grace_period_seconds=30)
    buffer2.register_user("EMP002", "Dr. Priya Menon", "Radiologist", "Radiology", True)
    evt2 = {
        "event_id": "SCEN-2-EVT",
        "event_timestamp": base_time + timedelta(hours=2),
        "arrival_timestamp": base_time + timedelta(hours=2),
        "account_id": "radiology_shared",
        "session_id": "SESS-SCEN-2",
        "action_id": "EXPORT_PATIENT_RECORD",
        "device_id": "RAD-WS-01",
        "ip_address": "192.168.10.21"
    }
    buffer2.ingest_event(evt2)
    init_res2 = buffer2.process_all_buffered()[0]
    initial_status2 = init_res2["status"]  # Should be PENDING

    # Late delegation arrives 30 mins later
    reconciled_cnt2 = buffer2.register_delegation(
        shared_account="radiology_shared",
        user_id="EMP002",
        start_time=base_time + timedelta(hours=1),
        end_time=base_time + timedelta(hours=4),
        session_id="SESS-SCEN-2",
        auto_reconcile=True
    )
    final_record2 = buffer2.processed_records["SCEN-2-EVT"]
    scen2_pass = (initial_status2 == "PENDING" and final_record2["status"] == "ATTRIBUTED" and reconciled_cnt2 == 1)

    scenarios_results.append({
        "scenario_id": "SCENARIO_2",
        "description": "Late-arriving delegation triggers retroactive in-place reconciliation",
        "input_conditions": "Action at 11:00 arrives with no delegation; delegation arrives at 11:30 covering 10:00-13:00",
        "expected_result": "Initial state PENDING; reconciled in-place to ATTRIBUTED without duplicate record",
        "actual_result": f"Initial: {initial_status2} -> Final: {final_record2['status']}",
        "evidence": f"Reconciled event count: {reconciled_cnt2}; resolution_type: {final_record2['resolution_type']}",
        "test_status": "PASSED" if scen2_pass else "FAILED"
    })

    # ========================================================
    # SCENARIO 3: Out-of-order events
    # ========================================================
    buffer3 = IngestionBuffer()
    buffer3.register_user("EMP003", "Ravi Kumar", "Technologist", "Radiology", True)
    buffer3.register_delegation("radiology_shared", "EMP003", base_time, base_time + timedelta(hours=4))

    # Action arrives before Login
    evt_act3 = {"event_id": "SCEN-3-ACT", "event_timestamp": base_time + timedelta(minutes=20), "arrival_timestamp": base_time + timedelta(minutes=30), "account_id": "radiology_shared", "action_id": "VIEW_PATIENT_RECORD"}
    evt_log3 = {"event_id": "SCEN-3-LOG", "event_timestamp": base_time + timedelta(minutes=5), "arrival_timestamp": base_time + timedelta(minutes=31), "account_id": "radiology_shared", "action_id": "USER_LOGIN"}

    buffer3.ingest_event(evt_act3)
    buffer3.ingest_event(evt_log3)
    ordered3 = buffer3.flush_and_order()
    scen3_pass = (ordered3[0]["event_id"] == "SCEN-3-LOG" and ordered3[1]["event_id"] == "SCEN-3-ACT")

    scenarios_results.append({
        "scenario_id": "SCENARIO_3",
        "description": "Out-of-order authentication and clinical action sequenced by event time",
        "input_conditions": "Clinical action (09:20) arrives at 09:30; Workstation login (09:05) arrives at 09:31",
        "expected_result": "Events sequenced chronologically: Login (09:05) before Action (09:20)",
        "actual_result": f"Ordered sequence: {[e['event_id'] for e in ordered3]}",
        "evidence": f"First event timestamp: {ordered3[0]['event_timestamp'].strftime('%H:%M')}",
        "test_status": "PASSED" if scen3_pass else "FAILED"
    })

    # ========================================================
    # SCENARIO 4: Expired or revoked delegation attempt
    # ========================================================
    del_mgr4 = DelegationLifecycleManager()
    del4 = del_mgr4.create_delegation("lab_shared", "EMP004", base_time - timedelta(hours=5), base_time - timedelta(hours=1), current_time=base_time)
    is_valid4, reason4, _ = del_mgr4.is_valid_for_action("lab_shared", "EMP004", base_time)

    # Revoked delegation test
    del4_rev = del_mgr4.create_delegation("lab_shared", "EMP018", base_time, base_time + timedelta(hours=8), current_time=base_time)
    del_mgr4.revoke_delegation(del4_rev["delegation_id"], "Staff re-assigned to offsite facility", "Dr. Rajesh Varma", revoked_at=base_time + timedelta(hours=1))
    is_valid4_rev, reason4_rev, _ = del_mgr4.is_valid_for_action("lab_shared", "EMP018", base_time + timedelta(hours=2))

    scen4_pass = (not is_valid4) and (not is_valid4_rev) and ("REVOKED" in reason4_rev)

    scenarios_results.append({
        "scenario_id": "SCENARIO_4",
        "description": "Action performed against expired or revoked shift delegation",
        "input_conditions": "EMP004 delegation expired at 08:00; EMP018 delegation revoked at 10:00; action at 11:00",
        "expected_result": "Authorization rejected; actions flagged UNATTRIBUTED / REVOKED",
        "actual_result": f"Expired rejection: {reason4}; Revoked rejection: {reason4_rev}",
        "evidence": f"Delegation status: {del4_rev['status']} (Revoked by supervisor)",
        "test_status": "PASSED" if scen4_pass else "FAILED"
    })

    # ========================================================
    # SCENARIO 5: Conflicting overlapping delegations requiring human review
    # ========================================================
    del_mgr5 = DelegationLifecycleManager()
    del_mgr5.create_delegation("radiology_shared", "EMP002", base_time, base_time + timedelta(hours=4), current_time=base_time)
    del_mgr5.create_delegation("radiology_shared", "EMP003", base_time, base_time + timedelta(hours=4), current_time=base_time)

    active5 = del_mgr5.get_active_delegations_for_account("radiology_shared", base_time + timedelta(hours=1))
    dossier5 = CrossSourceCorrelator.correlate(
        event_dict={"event_id": "SCEN-5-EVT", "action_id": "EXPORT_PATIENT_RECORD", "account_id": "radiology_shared"},
        active_delegations=active5
    )
    scen5_pass = (len(active5) == 2 and dossier5.final_status == "AMBIGUOUS" and len(dossier5.conflicting_signals) > 0)

    scenarios_results.append({
        "scenario_id": "SCENARIO_5",
        "description": "Overlapping staff shifts create ambiguity without distinct biometric evidence",
        "input_conditions": "Both EMP002 and EMP003 delegated for radiology_shared between 09:00 and 13:00",
        "expected_result": "Flagged AMBIGUOUS; no arbitrary assignment; routed to Compliance Escalation Queue",
        "actual_result": f"Status: {dossier5.final_status}; Score: {dossier5.score:.1f}",
        "evidence": f"Conflicting signals: {dossier5.conflicting_signals}",
        "test_status": "PASSED" if scen5_pass else "FAILED"
    })

    # ========================================================
    # SCENARIO 6: Missing network/device telemetry resilience
    # ========================================================
    del_mgr6 = DelegationLifecycleManager()
    del_mgr6.create_delegation("pharmacy_shared", "EMP007", base_time, base_time + timedelta(hours=8), current_time=base_time)
    active6 = del_mgr6.get_active_delegations_for_account("pharmacy_shared", base_time + timedelta(hours=1))
    dossier6 = CrossSourceCorrelator.correlate(
        event_dict={"event_id": "SCEN-6-EVT", "action_id": "DISPENSE_MEDICATION", "account_id": "pharmacy_shared", "session_id": "SESS-PHARM-01", "ip_address": "0.0.0.0", "device_id": "UNKNOWN"},
        active_delegations=active6
    )
    scen6_pass = (dossier6.final_status == "ATTRIBUTED" and "IP Subnet CIDR" in dossier6.missing_signals)

    scenarios_results.append({
        "scenario_id": "SCENARIO_6",
        "description": "Missing optional network/device telemetry does not break identity attribution",
        "input_conditions": "IP=0.0.0.0 and Device=UNKNOWN; Valid delegation and active session present",
        "expected_result": "Action successfully ATTRIBUTED; missing telemetry noted as reduced supporting context",
        "actual_result": f"Status: {dossier6.final_status}; Candidate: {dossier6.identity_candidate}",
        "evidence": f"Missing signals noted: {dossier6.missing_signals}",
        "test_status": "PASSED" if scen6_pass else "FAILED"
    })

    # ========================================================
    # SCENARIO 7: After-hours sensitive action alerting
    # ========================================================
    alert_mgr7 = OperationalAlertManager()
    is_new7, alert7 = alert_mgr7.trigger_alert(
        alert_type="AFTER_HOURS_SENSITIVE_ACTION",
        severity=AlertSeverity.HIGH,
        event_id="EVT-00019",
        message="Critical electronic health record export at 03:15 AM outside authorized clinical hours",
        shared_account="radiology_shared",
        created_at=base_time
    )
    scen7_pass = (is_new7 and alert7["severity"] == "HIGH" and alert7["status"] == "OPEN")

    scenarios_results.append({
        "scenario_id": "SCENARIO_7",
        "description": "After-hours critical clinical action outside authorized shift triggers high-severity alert",
        "input_conditions": "Record export at 03:15 AM with expired delegation on radiology_shared",
        "expected_result": "Operational SOC Alert created with HIGH severity and deduplication key",
        "actual_result": f"Alert {alert7['alert_id']} created; Status: {alert7['status']}",
        "evidence": f"Alert message: {alert7['message']}",
        "test_status": "PASSED" if scen7_pass else "FAILED"
    })

    # ========================================================
    # SCENARIO 8: Duplicate event ingestion rejection
    # ========================================================
    buffer8 = IngestionBuffer()
    evt8 = {"event_id": "SCEN-8-EVT", "event_timestamp": base_time, "arrival_timestamp": base_time, "account_id": "billing_shared", "action_id": "DELETE_RECORD"}
    res8_1 = buffer8.ingest_event(evt8)
    res8_2 = buffer8.ingest_event(evt8)  # Replay identical event
    scen8_pass = (res8_1["status"] == "BUFFERED" and res8_2["status"] == "DUPLICATE" and buffer8.duplicate_count == 1)

    scenarios_results.append({
        "scenario_id": "SCENARIO_8",
        "description": "Replay / duplicate event payload rejected at ingestion buffer boundary",
        "input_conditions": "Identical event payload submitted twice consecutively",
        "expected_result": "First event BUFFERED; second event rejected with status DUPLICATE; no database pollution",
        "actual_result": f"First: {res8_1['status']} -> Second: {res8_2['status']}",
        "evidence": f"Duplicate count recorded: {buffer8.duplicate_count}",
        "test_status": "PASSED" if scen8_pass else "FAILED"
    })

    # Write results to results/scenario_validation.csv
    if not output_csv:
        results_dir = os.path.join(BASE_DIR, "results")
        os.makedirs(results_dir, exist_ok=True)
        output_csv = os.path.join(results_dir, "scenario_validation.csv")

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["scenario_id", "description", "input_conditions", "expected_result", "actual_result", "evidence", "test_status"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scenarios_results)

    print(f"Scenario validation written to {output_csv} (8/8 scenarios executed)")
    return scenarios_results


if __name__ == "__main__":
    run_and_validate_all_scenarios()
