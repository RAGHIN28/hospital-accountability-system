import os
import sys
import copy
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from src.normalization import NormalizedEvent, EventNormalizer


class MultiSourceIngestionEngine:
    """
    Simulates and ingests five distinct hospital log streams:
    1. APPLICATION_LOGS: Clinical actions performed inside EHR, PACS, LIS, Pharmacy.
    2. AUTHENTICATION_LOGS: Domain workstation logins and GINA credential events.
    3. SESSION_LOGS: Session start, refresh, and termination events.
    4. DELEGATION_LOGS: Shift authorization grants, renewals, and revocations.
    5. TELEMETRY_LOGS: Network flow metadata, IP subnet assignments, and device heartbeats.
    """

    def __init__(self):
        self.ingested_events: List[NormalizedEvent] = []
        self.validation_errors: List[Dict[str, Any]] = []
        self.source_counts = {
            "APPLICATION_LOGS": 0,
            "AUTHENTICATION_LOGS": 0,
            "SESSION_LOGS": 0,
            "DELEGATION_LOGS": 0,
            "TELEMETRY_LOGS": 0
        }

    def ingest_raw_record(self, source_type: str, raw_payload: Dict[str, Any]) -> Tuple[bool, Optional[NormalizedEvent], Optional[str]]:
        """Validates and normalizes an incoming raw record from any recognized source."""
        if source_type in ["APPLICATION_LOGS", "SYSTEM_LOG"]:
            event, err = EventNormalizer.normalize_system_log(raw_payload)
        elif source_type in ["AUTHENTICATION_LOGS", "AUTH"]:
            event, err = EventNormalizer.normalize_auth_log(raw_payload)
        elif source_type == "SESSION_LOGS":
            # Normalize session event
            ts = raw_payload.get("timestamp") or datetime.utcnow()
            event = NormalizedEvent(
                event_id=raw_payload.get("event_id", f"SESS-EVT-{len(self.ingested_events)}"),
                source="SESSION_BROKER",
                event_type="SESSION_LIFECYCLE",
                event_time=ts,
                shared_account=raw_payload.get("shared_account", ""),
                user_id=raw_payload.get("user_id"),
                session_id=raw_payload.get("session_id"),
                action_type=raw_payload.get("action", "SESSION_UPDATE"),
                device_id=raw_payload.get("device_id"),
                ip_address=raw_payload.get("ip_address"),
                raw_reference=raw_payload
            )
            err = None
        elif source_type == "DELEGATION_LOGS":
            ts = raw_payload.get("timestamp") or datetime.utcnow()
            event = NormalizedEvent(
                event_id=raw_payload.get("event_id", f"DEL-EVT-{len(self.ingested_events)}"),
                source="DELEGATION_REGISTRY",
                event_type="AUTHORIZATION",
                event_time=ts,
                shared_account=raw_payload.get("shared_account", ""),
                user_id=raw_payload.get("delegate_user_id"),
                delegation_id=raw_payload.get("delegation_id"),
                action_type=raw_payload.get("action", "DELEGATION_GRANTED"),
                raw_reference=raw_payload
            )
            err = None
        elif source_type == "TELEMETRY_LOGS":
            ts = raw_payload.get("timestamp") or datetime.utcnow()
            event = NormalizedEvent(
                event_id=raw_payload.get("event_id", f"TEL-EVT-{len(self.ingested_events)}"),
                source="NETWORK_TELEMETRY",
                event_type="TELEMETRY_SAMPLE",
                event_time=ts,
                shared_account=raw_payload.get("shared_account", ""),
                ip_address=raw_payload.get("source_ip"),
                device_id=raw_payload.get("device_id"),
                subnet_cidr=raw_payload.get("subnet_cidr"),
                user_agent=raw_payload.get("user_agent"),
                action_type="TELEMETRY_PROBE",
                raw_reference=raw_payload
            )
            err = None
        else:
            err = f"UNKNOWN_SOURCE_TYPE: {source_type}"
            event = None

        if err:
            self.validation_errors.append({
                "source_type": source_type,
                "payload": raw_payload,
                "error": err,
                "timestamp": datetime.utcnow()
            })
            return False, None, err

        self.ingested_events.append(event)
        canonical_src = source_type if source_type in self.source_counts else "APPLICATION_LOGS"
        self.source_counts[canonical_src] = self.source_counts.get(canonical_src, 0) + 1
        return True, event, None

    def get_ingestion_summary(self) -> Dict[str, Any]:
        return {
            "total_ingested": len(self.ingested_events),
            "validation_errors": len(self.validation_errors),
            "source_breakdown": self.source_counts
        }
