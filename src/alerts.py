import os
import sys
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)


class AlertSeverity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertStatus:
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class OperationalAlertManager:
    """
    Security Operations Center (SOC) Alerting Engine for Hospital Shared-Account Anomalies.
    Includes automated alert generation, deduplication keys, and workflow state tracking.
    """

    ALERT_TYPES = [
        "EXPIRED_DELEGATION_USED",
        "REVOKED_DELEGATION_USED",
        "CONFLICTING_DELEGATIONS",
        "UNKNOWN_SESSION",
        "EXPIRED_SESSION_ACTION",
        "REPEATED_ATTRIBUTION_FAILURE",
        "AFTER_HOURS_SENSITIVE_ACTION",
        "MISSING_REQUIRED_EVIDENCE",
        "SUSPICIOUS_HIGH_VOLUME_USAGE"
    ]

    def __init__(self):
        # alert_id -> alert dict
        self.alerts: Dict[str, Dict[str, Any]] = {}
        # dedupe_key -> alert_id
        self.dedupe_index: Dict[str, str] = {}
        self.alert_history: List[Dict[str, Any]] = []

    def trigger_alert(
        self,
        alert_type: str,
        severity: str,
        event_id: str,
        message: str,
        shared_account: str,
        created_at: Optional[datetime] = None,
        dedupe_key: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Generates a new alert or suppresses duplicates if an active alert with
        matching dedupe_key already exists.

        CLINICAL SOC RATIONALE:
        In high-volume hospital environments (e.g., ICU/ER nursing stations), an anomalous
        shared-account condition (such as an expired delegation token or unmapped IP subnet)
        may trigger dozens of consecutive events in seconds. Without deduplication,
        "alarm fatigue" causes SOC analysts to ignore critical alerts.
        
        The deduplication key groups related incidents while maintaining an occurrence
        counter and updating `last_seen` timestamps, preserving forensic volume context
        without flooding analyst queues.

        Returns: (is_new_alert, alert_record)
        """
        now = created_at or datetime.utcnow()
        key = dedupe_key or f"{alert_type}:{shared_account}:{event_id}"

        # Check deduplication index for existing OPEN / ACKNOWLEDGED alert
        if key in self.dedupe_index:
            existing_id = self.dedupe_index[key]
            existing = self.alerts.get(existing_id)
            if existing and existing["status"] != AlertStatus.RESOLVED:
                # Suppress duplicate alert flood
                existing["occurrence_count"] = existing.get("occurrence_count", 1) + 1
                existing["last_seen"] = now
                return False, existing

        alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
        alert_record = {
            "alert_id": alert_id,
            "alert_type": alert_type,
            "severity": severity,
            "event_id": event_id,
            "shared_account": shared_account.lower(),
            "message": message,
            "dedupe_key": key,
            "created_at": now,
            "last_seen": now,
            "occurrence_count": 1,
            "status": AlertStatus.OPEN,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "resolved_by": None,
            "resolved_at": None,
            "resolution_notes": None
        }

        self.alerts[alert_id] = alert_record
        self.dedupe_index[key] = alert_id
        self.alert_history.append(alert_record)
        return True, alert_record

    def acknowledge_alert(self, alert_id: str, actor: str) -> Dict[str, Any]:
        """Acknowledge an open alert by SOC analyst."""
        alert = self.alerts.get(alert_id)
        if not alert:
            raise KeyError(f"Alert {alert_id} not found")

        alert["status"] = AlertStatus.ACKNOWLEDGED
        alert["acknowledged_by"] = actor
        alert["acknowledged_at"] = datetime.utcnow()
        return alert

    def resolve_alert(self, alert_id: str, actor: str, notes: str) -> Dict[str, Any]:
        """Resolve alert after investigation."""
        alert = self.alerts.get(alert_id)
        if not alert:
            raise KeyError(f"Alert {alert_id} not found")

        alert["status"] = AlertStatus.RESOLVED
        alert["resolved_by"] = actor
        alert["resolved_at"] = datetime.utcnow()
        alert["resolution_notes"] = notes
        return alert

    def get_open_alerts(self) -> List[Dict[str, Any]]:
        return [a for a in self.alerts.values() if a["status"] in [AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]]
