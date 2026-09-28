import os
import sys
import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)


class NormalizedEvent:
    """
    Common Normalized Event Model across all disparate hospital sources.
    Preserves original raw attributes while standardizing clinical and forensic fields.

    Why this canonical model is necessary:
    In clinical hospital IT, different vendor systems (Epic EHR, Cerner LIS, Philips PACS,
    Active Directory GINA, Cisco wireless controllers) emit logs in conflicting, non-standardized
    JSON, syslog, and CSV formats. Normalizing to a canonical 17-field structure allows uniform
    correlation while `raw_reference` retains the un-mutated original payload for forensic audit.
    """

    REQUIRED_FIELDS = ["event_id", "source", "event_type", "event_time", "shared_account", "action_type"]

    def __init__(
        self,
        event_id: str,
        source: str,
        event_type: str,
        event_time: datetime,
        arrival_time: Optional[datetime] = None,
        shared_account: str = "",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        action_type: str = "",
        resource: Optional[str] = None,
        ip_address: Optional[str] = None,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        subnet_cidr: Optional[str] = None,
        delegation_id: Optional[str] = None,
        raw_reference: Optional[Dict[str, Any]] = None,
        ingestion_id: Optional[str] = None
    ):
        self.event_id = event_id
        self.source = source
        self.event_type = event_type
        self.event_time = event_time
        self.arrival_time = arrival_time or datetime.utcnow()
        self.shared_account = shared_account.lower() if shared_account else ""
        self.user_id = user_id
        self.session_id = session_id
        self.action_type = action_type
        self.resource = resource or "NONE"
        self.ip_address = ip_address or "0.0.0.0"
        self.device_id = device_id or "UNKNOWN"
        self.user_agent = user_agent or "NONE"
        self.subnet_cidr = subnet_cidr or self._derive_subnet(self.ip_address)
        self.delegation_id = delegation_id
        self.raw_reference = raw_reference or {}
        self.ingestion_id = ingestion_id or f"ING-{uuid.uuid4().hex[:8]}"
        self.payload_hash = self._compute_payload_hash()

    def _derive_subnet(self, ip: str) -> str:
        """Derive standard /24 subnet from IPv4 string if available."""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return "UNKNOWN_CIDR"

    def _compute_payload_hash(self) -> str:
        ts_str = self.event_time.isoformat() if isinstance(self.event_time, datetime) else str(self.event_time)
        payload = f"{self.event_id}|{ts_str}|{self.shared_account}|{self.action_type}|{self.ip_address}|{self.device_id}|{self.session_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "event_type": self.event_type,
            "event_time": self.event_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.event_time, datetime) else str(self.event_time),
            "arrival_time": self.arrival_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.arrival_time, datetime) else str(self.arrival_time),
            "shared_account": self.shared_account,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "action_type": self.action_type,
            "resource": self.resource,
            "ip_address": self.ip_address,
            "device_id": self.device_id,
            "user_agent": self.user_agent,
            "subnet_cidr": self.subnet_cidr,
            "delegation_id": self.delegation_id,
            "payload_hash": self.payload_hash,
            "ingestion_id": self.ingestion_id
        }


class EventNormalizer:
    """Standardizes disparate log sources into NormalizedEvent instances."""

    @staticmethod
    def normalize_system_log(raw_log: Dict[str, Any]) -> Tuple[Optional[NormalizedEvent], Optional[str]]:
        """Normalizes a workstation/PACS application audit record."""
        # Validation
        if not raw_log.get("event_id"):
            return None, "VALIDATION_FAILED: Missing event_id"

        ts = raw_log.get("timestamp") or raw_log.get("event_timestamp")
        if not ts:
            return None, "VALIDATION_FAILED: Missing timestamp"

        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                try:
                    ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return None, f"VALIDATION_FAILED: Malformed timestamp format {ts}"

        action = raw_log.get("action") or raw_log.get("action_id") or "UNKNOWN_ACTION"
        account = raw_log.get("username") or raw_log.get("account_id") or "UNKNOWN_ACCOUNT"

        event = NormalizedEvent(
            event_id=raw_log["event_id"],
            source=raw_log.get("source_system", "PACS_APPLICATION"),
            event_type="CLINICAL_ACTION" if "LOGIN" not in action else "AUTHENTICATION",
            event_time=ts,
            arrival_time=raw_log.get("arrival_timestamp") or datetime.utcnow(),
            shared_account=account,
            user_id=raw_log.get("user_id"),
            session_id=raw_log.get("session_id"),
            action_type=action,
            resource=raw_log.get("target_id"),
            ip_address=raw_log.get("source_ip") or raw_log.get("ip_address"),
            device_id=raw_log.get("device_id"),
            user_agent=raw_log.get("user_agent"),
            raw_reference=raw_log
        )
        return event, None

    @staticmethod
    def normalize_auth_log(raw_auth: Dict[str, Any]) -> Tuple[Optional[NormalizedEvent], Optional[str]]:
        """Normalizes an identity/authentication log event."""
        if not raw_auth.get("auth_event_id"):
            return None, "VALIDATION_FAILED: Missing auth_event_id"

        ts = raw_auth.get("auth_time") or datetime.utcnow()
        if isinstance(ts, str):
            ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

        event = NormalizedEvent(
            event_id=raw_auth["auth_event_id"],
            source="IDENTITY_AUTH_SERVICE",
            event_type="AUTHENTICATION",
            event_time=ts,
            arrival_time=raw_auth.get("arrival_time") or datetime.utcnow(),
            shared_account=raw_auth.get("shared_account", ""),
            user_id=raw_auth.get("authenticated_user"),
            session_id=raw_auth.get("issued_session_id"),
            action_type="USER_LOGIN" if raw_auth.get("auth_success", True) else "LOGIN_FAILURE",
            resource=raw_auth.get("target_workstation"),
            ip_address=raw_auth.get("client_ip"),
            device_id=raw_auth.get("workstation_id"),
            raw_reference=raw_auth
        )
        return event, None
