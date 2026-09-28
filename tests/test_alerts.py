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

from src.alerts import OperationalAlertManager, AlertSeverity, AlertStatus


def test_alert_generation_and_deduplication():
    """Verify that alerts are created and duplicate events within same window are suppressed."""
    mgr = OperationalAlertManager()
    now = datetime(2026, 9, 1, 10, 0, 0)

    # First alert trigger
    is_new1, alert1 = mgr.trigger_alert(
        alert_type="EXPIRED_DELEGATION_USED",
        severity=AlertSeverity.HIGH,
        event_id="EVT-ALT-001",
        message="Sensitive record viewed after delegation expired",
        shared_account="radiology_shared",
        created_at=now,
        dedupe_key="EXPIRED:radiology_shared:EVT-ALT-001"
    )
    assert is_new1
    assert alert1["status"] == AlertStatus.OPEN
    assert alert1["occurrence_count"] == 1

    # Second trigger with identical dedupe_key (e.g. repeated log spike)
    is_new2, alert2 = mgr.trigger_alert(
        alert_type="EXPIRED_DELEGATION_USED",
        severity=AlertSeverity.HIGH,
        event_id="EVT-ALT-001",
        message="Sensitive record viewed after delegation expired",
        shared_account="radiology_shared",
        created_at=now + timedelta(seconds=5),
        dedupe_key="EXPIRED:radiology_shared:EVT-ALT-001"
    )
    assert not is_new2
    assert alert2["alert_id"] == alert1["alert_id"]
    assert alert2["occurrence_count"] == 2
    assert len(mgr.alerts) == 1  # No duplicate alert created


def test_alert_lifecycle_flow():
    """Verify transition from OPEN -> ACKNOWLEDGED -> RESOLVED."""
    mgr = OperationalAlertManager()
    now = datetime(2026, 9, 1, 14, 0, 0)

    _, alert = mgr.trigger_alert(
        alert_type="CONFLICTING_DELEGATIONS",
        severity=AlertSeverity.CRITICAL,
        event_id="EVT-CONF-99",
        message="Multiple staff active on lab_shared during specimen edit",
        shared_account="lab_shared",
        created_at=now
    )
    assert alert["status"] == AlertStatus.OPEN

    # SOC Analyst acknowledges alert
    mgr.acknowledge_alert(alert["alert_id"], actor="Analyst Elena")
    assert alert["status"] == AlertStatus.ACKNOWLEDGED
    assert alert["acknowledged_by"] == "Analyst Elena"

    # Compliance Officer resolves alert
    mgr.resolve_alert(alert["alert_id"], actor="Officer Marcus", notes="Confirmed legitimate shift handover")
    assert alert["status"] == AlertStatus.RESOLVED
    assert alert["resolved_by"] == "Officer Marcus"
    assert "legitimate" in alert["resolution_notes"]

    # No remaining open alerts
    assert len(mgr.get_open_alerts()) == 0
