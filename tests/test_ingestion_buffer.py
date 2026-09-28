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

from src.ingestion_buffer import IngestionBuffer


def test_delayed_event_enters_pending_buffer():
    """
    Test requirement:
    Event arrives first: E_DELAY_001 at 09:20.
    At this moment: delegation info is unavailable.
    Initial result: PENDING / UNATTRIBUTED (waiting for delegation).
    """
    buffer = IngestionBuffer(grace_period_seconds=30)
    buffer.register_user("EMP001", "Dr. Arun Kumar", "Consultant", "Radiology", True)

    event = {
        "event_id": "E_DELAY_001",
        "event_timestamp": datetime(2026, 9, 1, 9, 20, 0),
        "arrival_timestamp": datetime(2026, 9, 1, 9, 20, 5),
        "account_id": "radiology_shared",
        "session_id": "S_DELAY_001",
        "action_id": "MODIFY_PATIENT_RECORD",
        "device_id": "RAD-WS-01",
        "ip_address": "192.168.10.21",
        "user_agent": "Mozilla/5.0",
        "source_system": "PACS"
    }

    # Ingest event
    ingest_res = buffer.ingest_event(event)
    assert ingest_res["status"] == "BUFFERED"

    # Process buffered events
    results = buffer.process_all_buffered()
    assert len(results) == 1
    res = results[0]

    # Initial state must be PENDING (waiting for missing delegation context)
    assert res["status"] == "PENDING"
    assert res["initial_status"] == "PENDING"
    assert "E_DELAY_001" in buffer.pending_events


def test_late_delegation_reconciles_same_event_without_duplicate():
    """
    Test requirement:
    1. E_DELAY_001 enters pending state
    2. Later delegation arrives covering 09:00 - 09:30
    3. Reconcile updates the SAME event to ATTRIBUTED
    4. Records resolution reason and resolution_timestamp
    5. Does NOT create a duplicate record
    """
    buffer = IngestionBuffer(grace_period_seconds=30)
    buffer.register_user("U001", "Dr. Alice Stone", "Senior Radiologist", "Radiology", True)

    event = {
        "event_id": "E_DELAY_001",
        "event_timestamp": datetime(2026, 9, 1, 9, 20, 0),
        "arrival_timestamp": datetime(2026, 9, 1, 9, 20, 5),
        "account_id": "radiology_shared",
        "session_id": "S_DELAY_001",
        "action_id": "MODIFY_PATIENT_RECORD",
        "device_id": "RAD-WS-01",
        "ip_address": "192.168.10.21",
        "user_agent": "Mozilla/5.0",
        "source_system": "PACS"
    }

    buffer.ingest_event(event)
    buffer.process_all_buffered()
    assert buffer.processed_records["E_DELAY_001"]["status"] == "PENDING"

    # Later delegation arrives
    reconciled_count = buffer.register_delegation(
        shared_account="radiology_shared",
        user_id="U001",
        start_time=datetime(2026, 9, 1, 9, 0, 0),
        end_time=datetime(2026, 9, 1, 9, 30, 0),
        session_id="S_DELAY_001",
        reason="Morning Emergency Coverage",
        status="ACTIVE",
        auto_reconcile=True
    )

    assert reconciled_count == 1
    # Check that only ONE processed record exists for E_DELAY_001
    assert len(buffer.processed_records) == 1
    reconciled_record = buffer.processed_records["E_DELAY_001"]

    # Verify updated record attributes
    assert reconciled_record["event_id"] == "E_DELAY_001"
    assert reconciled_record["event_timestamp"] == datetime(2026, 9, 1, 9, 20, 0)
    assert reconciled_record["initial_status"] == "PENDING"
    assert reconciled_record["final_status"] == "ATTRIBUTED"
    assert reconciled_record["status"] == "ATTRIBUTED"
    assert reconciled_record["attributed_user_id"] == "U001"
    assert reconciled_record["attributed_user_name"] == "Dr. Alice Stone"
    assert reconciled_record["resolution_type"] == "LATE_DELEGATION"
    assert reconciled_record["resolution_timestamp"] is not None
    assert "E_DELAY_001" not in buffer.pending_events


def test_out_of_order_events_correctly_ordered():
    """
    Test requirement:
    Arrival order is intentionally inverted:
    1. 09:20 sensitive action
    2. 09:10 login
    3. 09:15 delegation
    Buffer must reconstruct chronological order: 09:10 -> 09:15 -> 09:20.
    The 09:20 action must be evaluated using the 09:15 delegation.
    """
    buffer = IngestionBuffer(grace_period_seconds=60)
    buffer.register_user("U001", "Dr. Alice Stone", "Senior Radiologist", "Radiology", True)

    # 1. 09:20 Sensitive action arrives first at 09:25:00
    evt_action = {
        "event_id": "EVT-ORD-020",
        "event_timestamp": datetime(2026, 9, 1, 9, 20, 0),
        "arrival_timestamp": datetime(2026, 9, 1, 9, 25, 0),
        "account_id": "radiology_shared",
        "session_id": "S_ORD_001",
        "action_id": "VIEW_PATIENT_RECORD",
        "device_id": "RAD-WS-01",
        "ip_address": "192.168.10.21",
        "user_agent": "RIS-Client/1.0",
        "source_system": "PACS"
    }

    # 2. 09:10 Login arrives second at 09:25:05
    evt_login = {
        "event_id": "EVT-ORD-010",
        "event_timestamp": datetime(2026, 9, 1, 9, 10, 0),
        "arrival_timestamp": datetime(2026, 9, 1, 9, 25, 5),
        "account_id": "radiology_shared",
        "session_id": "S_ORD_001",
        "action_id": "USER_LOGIN",
        "device_id": "RAD-WS-01",
        "ip_address": "192.168.10.21",
        "user_agent": "RIS-Client/1.0",
        "source_system": "PACS"
    }

    buffer.ingest_event(evt_action)
    buffer.ingest_event(evt_login)

    # Verify chronological ordering by event_timestamp
    ordered = buffer.flush_and_order()
    assert len(ordered) == 2
    assert ordered[0]["event_id"] == "EVT-ORD-010"  # 09:10 event is first
    assert ordered[1]["event_id"] == "EVT-ORD-020"  # 09:20 event is second

    # Now register the 09:15 delegation covering 09:15 to 09:45
    buffer.register_delegation(
        shared_account="radiology_shared",
        user_id="U001",
        start_time=datetime(2026, 9, 1, 9, 15, 0),
        end_time=datetime(2026, 9, 1, 9, 45, 0),
        session_id="S_ORD_001",
        reason="Morning Shift",
        auto_reconcile=False
    )

    # Evaluate the 09:20 event against the 09:15 delegation
    res_action = buffer.evaluate_single_event(evt_action)
    assert res_action["status"] == "ATTRIBUTED"
    assert res_action["attributed_user_id"] == "U001"


def test_buffer_duplicate_rejection():
    """Test requirement: Duplicate events in buffer rejected via payload hash / event_id."""
    buffer = IngestionBuffer()
    event = {
        "event_id": "EVT-DUP-001",
        "event_timestamp": datetime(2026, 9, 1, 10, 0, 0),
        "arrival_timestamp": datetime(2026, 9, 1, 10, 0, 1),
        "account_id": "radiology_shared",
        "session_id": "SESS-DUP-01",
        "action_id": "VIEW_PATIENT_RECORD",
        "device_id": "RAD-WS-01",
        "ip_address": "192.168.10.21",
        "user_agent": "RIS/1.0",
        "source_system": "PACS"
    }

    res1 = buffer.ingest_event(event)
    assert res1["status"] == "BUFFERED"

    # Second ingestion of same event
    res2 = buffer.ingest_event(event)
    assert res2["status"] == "DUPLICATE"
    assert buffer.duplicate_count == 1
