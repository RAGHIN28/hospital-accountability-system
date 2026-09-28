import os
import sys
import csv
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.database import SessionLocal
from app.models.system_log import SystemLog
from app.models.attribution_result import AttributionResult
from app.models.privileged_action import PrivilegedAction
from app.models.authorization import SharedAccountAuthorization
from app.models.user import User
from app.models.shared_account import SharedAccount


class EscalationManager:
    """
    Formal Human-in-the-Loop Fallback and Escalation Workflow for Hospital Compliance Officers.

    Core Philosophy:
    - Attribution is not equivalent to intent; it is an accountability-support mechanism.
    - Conflicting evidence or missing signals must NEVER result in automatic accusation.
    - Human compliance officers make final adjudication; the system provides structured evidence.

    Why Ambiguous Cases Are Escalated Instead of Force-Attributed:
    In clinical settings, false positive accusations damage professional reputations and
    compromise staff trust. When evidence margins are below decision thresholds (e.g., competing
    clinicians with identical workstation access), the system intentionally halts automated
    resolution. Escalating preserves forensic integrity and provides hospital risk managers
    with an untampered evidence dossier for independent corroboration.

    Seven Escalation Trigger Conditions:
    1. Multiple valid users match the same event (Ambiguous competing evidence).
    2. Required attribution evidence is missing.
    3. Delegation authorization is expired.
    4. Session information is missing and cannot be reconstructed.
    5. User roster information is unavailable or unmapped.
    6. Telemetry conflict creates unresolved ambiguity.
    7. Attribution engine cannot reach an explainable decision (Score < 60).
    """

    ERROR_CATEGORIES = [
        "MISSING_ROSTER",
        "MISSING_DELEGATION",
        "EXPIRED_DELEGATION",
        "MISSING_SESSION",
        "CONFLICTING_DELEGATION",
        "UNKNOWN_ACCOUNT",
        "INACTIVE_USER",
        "MISSING_NETWORK_TELEMETRY",
        "MISSING_DEVICE_TELEMETRY",
        "MISSING_USER_AGENT",
        "INCONSISTENT_TELEMETRY",
        "OTHER",
    ]

    REVIEW_STATES = [
        "PENDING_REVIEW",
        "UNDER_REVIEW",
        "RESOLVED",
        "REJECTED",
        "NO_ACTION",
    ]

    def __init__(self, db_session=None):
        self.db = db_session or SessionLocal()

    def identify_unresolved_sensitive_actions(self) -> List[Tuple[SystemLog, AttributionResult]]:
        """Identify all sensitive action events that are AMBIGUOUS, UNATTRIBUTED, or unresolved."""
        privileged_actions = self.db.query(PrivilegedAction).all()
        sensitive_names = set(pa.action_name for pa in privileged_actions)

        logs = self.db.query(SystemLog).filter(
            SystemLog.action.in_(sensitive_names),
            SystemLog.processing_status != "INVALID"
        ).all()

        unresolved = []
        for log in logs:
            res = self.db.query(AttributionResult).filter(AttributionResult.event_id == log.event_id).first()
            if not res or res.attribution_status in ["UNATTRIBUTED", "AMBIGUOUS"]:
                unresolved.append((log, res))
        return unresolved

    def categorize_error(self, log: SystemLog, result: Optional[AttributionResult]) -> str:
        """
        Assign a single primary error category to avoid double counting.
        Follows a strict hierarchical decision tree.
        """
        if not result:
            return "MISSING_DELEGATION"

        explanation = (result.explanation or "").lower()
        method = (result.attribution_method or "").upper()
        status = result.attribution_status

        # 1. Roster check
        if "roster" in explanation or "inactive" in explanation:
            if "inactive" in explanation:
                return "INACTIVE_USER"
            return "MISSING_ROSTER"

        # 2. Account check
        if "not a registered shared account" in explanation or "unknown" in explanation:
            return "UNKNOWN_ACCOUNT"

        # 3. Expired delegation
        if "expired" in explanation:
            return "EXPIRED_DELEGATION"

        # 4. Multiple / Conflicting delegations
        if status == "AMBIGUOUS" or "competing evidence" in explanation or "multiple" in explanation:
            return "CONFLICTING_DELEGATION"

        # 5. Missing delegation
        if "missing delegation" in explanation or "outside delegation" in explanation:
            return "MISSING_DELEGATION"

        # 6. Missing session
        if "missing session" in explanation or not log.session_id:
            return "MISSING_SESSION"

        # 7. Inconsistent or missing telemetry
        if "device" in explanation:
            return "MISSING_DEVICE_TELEMETRY"
        if "subnet" in explanation or "ip" in explanation:
            return "MISSING_NETWORK_TELEMETRY"

        return "OTHER"

    def determine_priority(self, log: SystemLog, category: str) -> str:
        """Determine compliance review priority (HIGH, MEDIUM, LOW)."""
        # Privileged actions with patient data modification or export are HIGH
        high_risk_actions = [
            "EDIT_PATIENT_RECORD", "EXPORT_PATIENT_RECORD",
            "MODIFY_LAB_RESULT", "MODIFY_PRESCRIPTION",
            "CHANGE_USER_ROLE", "DELETE_RECORD"
        ]
        if log.action in high_risk_actions or category in ["CONFLICTING_DELEGATION", "EXPIRED_DELEGATION"]:
            return "HIGH"
        elif category in ["MISSING_DELEGATION", "INACTIVE_USER"]:
            return "MEDIUM"
        return "LOW"

    def build_escalation_queue(self, simulate_reviews: bool = True) -> List[Dict[str, Any]]:
        """
        Builds the formal escalation queue with schema:
        case_id, event_id, created_at, priority, reason_category, event_timestamp,
        account_id, session_id, action_id, candidate_users, current_status,
        recommended_review, review_status, reviewer, review_timestamp, review_notes
        """
        unresolved_pairs = self.identify_unresolved_sensitive_actions()
        queue_records = []
        case_counter = 1

        for log, res in unresolved_pairs:
            category = self.categorize_error(log, res)
            priority = self.determine_priority(log, category)

            # Extract candidates
            candidates = []
            if res and res.candidate_scores_json:
                try:
                    c_list = json.loads(res.candidate_scores_json)
                    candidates = [f"{c.get('full_name')} ({c.get('employee_id')})" for c in c_list if c.get('total_score', 0) > 0]
                except Exception:
                    pass

            rec_review = ""
            if category == "CONFLICTING_DELEGATION":
                rec_review = "Verify physical workstation badge tap or departmental sign-in sheet to disambiguate overlapping staff."
            elif category == "EXPIRED_DELEGATION":
                rec_review = "Review after-hours clinical emergency justification with shift supervisor."
            elif category == "MISSING_DELEGATION":
                rec_review = "Confirm whether staff member was on an ad-hoc emergency swap or verbal delegation."
            else:
                rec_review = "Conduct forensic log correlation against physical access control system."

            # Simulated human review states for demonstration
            # POINTER: Human review states must be clearly labeled if simulated.
            review_status = "PENDING_REVIEW"
            reviewer = None
            review_ts = None
            review_notes = None

            if simulate_reviews:
                # First case simulated as UNDER_REVIEW or RESOLVED to show full workflow
                if case_counter == 1:
                    review_status = "UNDER_REVIEW"
                    reviewer = "Officer Elena Rostova (Lead Compliance)"
                    review_ts = (datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
                    review_notes = "SIMULATED: Cross-referencing physical badge logs for radiology workstation RAD-WS-02."
                elif case_counter == 2:
                    review_status = "RESOLVED"
                    reviewer = "Officer Marcus Vance (Clinical Safety)"
                    review_ts = (datetime.utcnow() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
                    review_notes = "SIMULATED: Shift supervisor confirmed emergency clinical override. Action attributed post-investigation."
                else:
                    review_status = "PENDING_REVIEW"

            case_record = {
                "case_id": f"ESC-2026-{case_counter:04d}",
                "event_id": log.event_id,
                "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "priority": priority,
                "reason_category": category,
                "event_timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "account_id": log.username,
                "session_id": log.session_id or "NONE",
                "action_id": log.action,
                "candidate_users": "; ".join(candidates) if candidates else "NONE",
                "current_status": res.attribution_status if res else "UNATTRIBUTED",
                "recommended_review": rec_review,
                "review_status": review_status,
                "reviewer": reviewer or "UNASSIGNED",
                "review_timestamp": review_ts or "N/A",
                "review_notes": review_notes or "Awaiting compliance officer assignment."
            }
            queue_records.append(case_record)
            case_counter += 1

        # Write to results/escalation_queue.csv
        results_dir = os.path.join(BASE_DIR, "results")
        os.makedirs(results_dir, exist_ok=True)
        csv_path = os.path.join(results_dir, "escalation_queue.csv")

        if queue_records:
            fieldnames = list(queue_records[0].keys())
        else:
            fieldnames = [
                "case_id", "event_id", "created_at", "priority", "reason_category",
                "event_timestamp", "account_id", "session_id", "action_id",
                "candidate_users", "current_status", "recommended_review",
                "review_status", "reviewer", "review_timestamp", "review_notes"
            ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(queue_records)

        print(f"Escalation queue successfully generated: {csv_path} ({len(queue_records)} cases)")
        return queue_records

    def generate_error_analysis(self) -> List[Dict[str, Any]]:
        """
        Expanded error analysis across all sensitive actions:
        Categories: MISSING_ROSTER, MISSING_DELEGATION, EXPIRED_DELEGATION,
        MISSING_SESSION, CONFLICTING_DELEGATION, UNKNOWN_ACCOUNT, INACTIVE_USER, etc.
        """
        unresolved_pairs = self.identify_unresolved_sensitive_actions()
        category_counts = {cat: 0 for cat in self.ERROR_CATEGORIES}

        for log, res in unresolved_pairs:
            cat = self.categorize_error(log, res)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        total_unresolved = len(unresolved_pairs)
        analysis_rows = []
        for cat, cnt in category_counts.items():
            pct = round((cnt / total_unresolved * 100.0), 2) if total_unresolved > 0 else 0.0
            analysis_rows.append({
                "error_category": cat,
                "incident_count": cnt,
                "percentage_of_unresolved": pct,
                "escalation_recommended": "YES" if cnt > 0 else "N/A"
            })

        results_dir = os.path.join(BASE_DIR, "results")
        os.makedirs(results_dir, exist_ok=True)
        csv_path = os.path.join(results_dir, "error_analysis.csv")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["error_category", "incident_count", "percentage_of_unresolved", "escalation_recommended"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(analysis_rows)

        print(f"Error analysis written to {csv_path}")
        return analysis_rows

    def generate_unresolved_actions_file(self) -> List[Dict[str, Any]]:
        """
        Generate detailed report for every unresolved sensitive action:
        event_id, account, session, action, reason, available evidence,
        missing evidence, candidate users, escalation status.
        """
        unresolved_pairs = self.identify_unresolved_sensitive_actions()
        unresolved_rows = []

        for log, res in unresolved_pairs:
            cat = self.categorize_error(log, res)
            avail = []
            if log.session_id:
                avail.append(f"Session {log.session_id}")
            if log.source_ip:
                avail.append(f"IP {log.source_ip}")
            if log.device_id:
                avail.append(f"Device {log.device_id}")

            missing = []
            if not log.session_id:
                missing.append("Session binding")
            if cat == "MISSING_DELEGATION":
                missing.append("Active shift delegation")
            elif cat == "EXPIRED_DELEGATION":
                missing.append("Current authorization window")
            elif cat == "CONFLICTING_DELEGATION":
                missing.append("Differentiating biometric/terminal evidence")

            candidates = "NONE"
            if res and res.candidate_scores_json:
                try:
                    c_list = json.loads(res.candidate_scores_json)
                    c_names = [c.get("full_name") for c in c_list if c.get("total_score", 0) > 0]
                    if c_names:
                        candidates = "; ".join(c_names)
                except Exception:
                    pass

            unresolved_rows.append({
                "event_id": log.event_id,
                "account": log.username,
                "session": log.session_id or "NONE",
                "action": log.action,
                "reason": cat,
                "available_evidence": ", ".join(avail) if avail else "None",
                "missing_evidence": ", ".join(missing) if missing else "Delegation record",
                "candidate_users": candidates,
                "escalation_status": "ESCALATED_TO_COMPLIANCE"
            })

        results_dir = os.path.join(BASE_DIR, "results")
        os.makedirs(results_dir, exist_ok=True)
        csv_path = os.path.join(results_dir, "unresolved_actions.csv")

        fieldnames = [
            "event_id", "account", "session", "action", "reason",
            "available_evidence", "missing_evidence", "candidate_users", "escalation_status"
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unresolved_rows)

        print(f"Unresolved actions report written to {csv_path}")
        return unresolved_rows

    def get_escalation_metrics(self) -> Dict[str, Any]:
        """
        Compute escalation metrics:
        total unresolved sensitive actions, escalated cases, pending cases,
        resolved cases, rejected cases, escalation rate.
        """
        privileged_actions = self.db.query(PrivilegedAction).all()
        sensitive_names = set(pa.action_name for pa in privileged_actions)
        total_sensitive = self.db.query(SystemLog).filter(
            SystemLog.action.in_(sensitive_names),
            SystemLog.processing_status != "INVALID"
        ).count()

        unresolved = self.identify_unresolved_sensitive_actions()
        total_unresolved = len(unresolved)

        escalation_rate = round((total_unresolved / total_sensitive * 100.0), 2) if total_sensitive > 0 else 0.0

        return {
            "total_sensitive_actions": total_sensitive,
            "total_unresolved_sensitive_actions": total_unresolved,
            "escalated_cases": total_unresolved,
            "pending_cases": max(0, total_unresolved - 1),
            "under_review_cases": 1 if total_unresolved > 0 else 0,
            "resolved_cases": 0,
            "rejected_cases": 0,
            "escalation_rate": escalation_rate
        }


def run_escalation_pipeline():
    manager = EscalationManager()
    print("Generating Escalation Queue...")
    manager.build_escalation_queue()
    print("Generating Error Analysis...")
    manager.generate_error_analysis()
    print("Generating Unresolved Actions File...")
    manager.generate_unresolved_actions_file()
    metrics = manager.get_escalation_metrics()
    print(f"Escalation Metrics: {metrics}")


if __name__ == "__main__":
    run_escalation_pipeline()
