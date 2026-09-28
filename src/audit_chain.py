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


class AuditChainRecord:
    """Immutable single record in the cryptographic audit trail."""

    def __init__(
        self,
        audit_id: str,
        timestamp: datetime,
        actor: str,
        event_id: str,
        action: str,
        details: str,
        previous_hash: str
    ):
        self.audit_id = audit_id
        self.timestamp = timestamp
        self.actor = actor
        self.event_id = event_id
        self.action = action
        self.details = details
        self.previous_hash = previous_hash
        self.record_hash = self.compute_hash()

    def compute_hash(self) -> str:
        ts_str = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp)
        payload = f"{self.audit_id}|{ts_str}|{self.actor}|{self.event_id}|{self.action}|{self.details}|{self.previous_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "actor": self.actor,
            "event_id": self.event_id,
            "action": self.action,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash
        }


class TamperEvidentAuditTrail:
    """
    Append-only tamper-evident audit ledger with SHA-256 cryptographic linkage.

    Architectural and Regulatory Design Context:
    Informed by the security principles of the HIPAA Security Rule (§ 164.312(b) Audit Controls)
    and FDA 21 CFR Part 11 guidance on tamper-evident electronic audit records in healthcare,
    audit trails must guarantee non-repudiation and withstand insider tampering. In this academic
    proof-of-concept, an append-only cryptographic hash chain provides verifiable mathematical
    tamper detection (implemented as an architectural design pattern; does not constitute formal
    regulatory compliance certification).
    
    If an authorized user or compromised administrator attempts to alter historical attribution
    logs to disguise unauthorized actions, the cryptographic hash chain immediately breaks at the
    altered block index, exposing the tampering.

    Verification guarantees:
    - Altering any historical field invalidates that record's SHA-256 hash.
    - Deleting, inserting, or reordering any record breaks the previous_hash link.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self):
        self.chain: List[AuditChainRecord] = []

    def append(
        self,
        actor: str,
        event_id: str,
        action: str,
        details: str,
        timestamp: Optional[datetime] = None
    ) -> AuditChainRecord:
        """Appends a new immutable entry to the ledger."""
        now = timestamp or datetime.utcnow()
        audit_id = f"AUDIT-{len(self.chain) + 1:06d}"
        prev_hash = self.chain[-1].record_hash if self.chain else self.GENESIS_HASH

        record = AuditChainRecord(
            audit_id=audit_id,
            timestamp=now,
            actor=actor,
            event_id=event_id,
            action=action,
            details=details,
            previous_hash=prev_hash
        )
        self.chain.append(record)
        return record

    def verify_chain(self) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Validates the entire audit chain from genesis to head.
        Returns: (is_valid, failure_reason, invalid_index)
        """
        if not self.chain:
            return True, None, None

        expected_prev_hash = self.GENESIS_HASH

        for idx, record in enumerate(self.chain):
            # 1. Verify previous hash pointer
            if record.previous_hash != expected_prev_hash:
                return (
                    False,
                    f"BROKEN_CHAIN: Record {record.audit_id} at index {idx} has previous_hash "
                    f"'{record.previous_hash[:12]}...' but expected '{expected_prev_hash[:12]}...'",
                    idx
                )

            # 2. Verify record's own hash integrity
            recomputed = record.compute_hash()
            if record.record_hash != recomputed:
                return (
                    False,
                    f"TAMPERED_RECORD: Record {record.audit_id} at index {idx} has altered content. "
                    f"Recorded hash '{record.record_hash[:12]}...' != recomputed '{recomputed[:12]}...'",
                    idx
                )

            expected_prev_hash = record.record_hash

        return True, "CHAIN_VALID", None

    def export_ledger(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.chain]
