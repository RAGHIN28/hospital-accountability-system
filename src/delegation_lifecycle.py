import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)


class DelegationState:
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CANCELLED = "CANCELLED"


class DelegationLifecycleManager:
    """
    Manages the lifecycle of shared-account shift delegations in a hospital environment.

    States:
    - CREATED: Shift authorization scheduled in advance; not yet within active time window.
    - ACTIVE: Current timestamp is within [start_time, end_time] and status is not revoked/cancelled.
    - EXPIRED: Shift window has elapsed (current timestamp > end_time).
    - REVOKED: Explicitly revoked before or during shift by supervisor/manager.
    - CANCELLED: Administrative cancellation before activation.

    Rules:
    - Only ACTIVE delegations can authorize sensitive clinical actions.
    - Expired, revoked, or cancelled delegations cannot authorize new actions.
    - All state transitions are immutably logged for auditability.
    """

    def __init__(self):
        # delegation_id -> delegation record
        self.delegations: Dict[str, Dict[str, Any]] = {}
        # Audit log of all lifecycle transitions
        self.transition_history: List[Dict[str, Any]] = []

    def create_delegation(
        self,
        shared_account: str,
        delegate_user_id: str,
        start_time: datetime,
        end_time: datetime,
        delegator_user_id: str = "Dr. Priya Menon",
        reason: str = "Clinical Shift Assignment",
        source: str = "ROSTER_MANAGEMENT",
        session_id: Optional[str] = None,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Create a new delegation record with initial state evaluation."""
        if end_time <= start_time:
            raise ValueError("end_time must be strictly greater than start_time")

        now = current_time or datetime.utcnow()
        delegation_id = f"DEL-{uuid.uuid4().hex[:8].upper()}"

        # Determine initial state based on current time
        if now < start_time:
            initial_status = DelegationState.CREATED
        elif start_time <= now <= end_time:
            initial_status = DelegationState.ACTIVE
        else:
            initial_status = DelegationState.EXPIRED

        record = {
            "delegation_id": delegation_id,
            "shared_account": shared_account.lower(),
            "delegate_user_id": delegate_user_id,
            "delegator_user_id": delegator_user_id,
            "start_time": start_time,
            "end_time": end_time,
            "session_id": session_id,
            "created_at": now,
            "status": initial_status,
            "reason": reason,
            "source": source,
            "revoked_at": None,
            "revocation_reason": None,
            "last_updated": now
        }
        self.delegations[delegation_id] = record

        self._record_transition(
            delegation_id=delegation_id,
            from_state="NONE",
            to_state=initial_status,
            timestamp=now,
            actor=delegator_user_id,
            note=f"Delegation created for {delegate_user_id} on {shared_account}"
        )
        return record

    def update_temporal_status(self, delegation_id: str, current_time: datetime) -> str:
        """
        Update temporal state (CREATED -> ACTIVE -> EXPIRED) based on given timestamp.

        Why dynamic temporal evaluation exists:
        Rather than polling or pinning state to server clock, delegation validity is evaluated
        against the action's event_timestamp. This allows asynchronous, out-of-order, or
        batch-processed events to be adjudicated against their true temporal context.
        """
        record = self.delegations.get(delegation_id)
        if not record:
            raise KeyError(f"Delegation {delegation_id} not found")

        # Security Invariant: Terminal states REVOKED and CANCELLED cannot be overridden by time passage.
        # Once revoked by a supervisor (e.g. following clinical reassignment or security suspension),
        # an authorization must never re-activate even if the wall clock falls within the shift window.
        if record["status"] in [DelegationState.REVOKED, DelegationState.CANCELLED]:
            return record["status"]

        # Inclusive boundary comparison: start_time and end_time are authorized down to the exact second.
        prev_status = record["status"]
        if current_time < record["start_time"]:
            new_status = DelegationState.CREATED
        elif record["start_time"] <= current_time <= record["end_time"]:
            new_status = DelegationState.ACTIVE
        else:
            new_status = DelegationState.EXPIRED

        if new_status != prev_status:
            record["status"] = new_status
            record["last_updated"] = current_time
            self._record_transition(
                delegation_id=delegation_id,
                from_state=prev_status,
                to_state=new_status,
                timestamp=current_time,
                actor="SYSTEM_TIME_MONITOR",
                note=f"Automatic temporal state transition to {new_status}"
            )
        return record["status"]

    def revoke_delegation(
        self,
        delegation_id: str,
        revocation_reason: str,
        revoked_by: str,
        revoked_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Explicitly revoke an active or created delegation."""
        record = self.delegations.get(delegation_id)
        if not record:
            raise KeyError(f"Delegation {delegation_id} not found")

        now = revoked_at or datetime.utcnow()
        prev_status = record["status"]
        record["status"] = DelegationState.REVOKED
        record["revoked_at"] = now
        record["revocation_reason"] = revocation_reason
        record["last_updated"] = now

        self._record_transition(
            delegation_id=delegation_id,
            from_state=prev_status,
            to_state=DelegationState.REVOKED,
            timestamp=now,
            actor=revoked_by,
            note=f"Revocation: {revocation_reason}"
        )
        return record

    def cancel_delegation(
        self,
        delegation_id: str,
        cancelled_by: str,
        cancel_reason: str = "Administrative Shift Adjustment",
        cancelled_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Cancel a scheduled delegation before it takes effect."""
        record = self.delegations.get(delegation_id)
        if not record:
            raise KeyError(f"Delegation {delegation_id} not found")

        now = cancelled_at or datetime.utcnow()
        prev_status = record["status"]
        record["status"] = DelegationState.CANCELLED
        record["last_updated"] = now

        self._record_transition(
            delegation_id=delegation_id,
            from_state=prev_status,
            to_state=DelegationState.CANCELLED,
            timestamp=now,
            actor=cancelled_by,
            note=f"Cancelled: {cancel_reason}"
        )
        return record

    def is_valid_for_action(
        self,
        shared_account: str,
        user_id: str,
        action_time: datetime
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validates whether a user has active, unrevoked authorization for a shared account
        at the precise action timestamp.
        Returns: (is_valid, rejection_reason, delegation_record)
        """
        matching = [
            d for d in self.delegations.values()
            if d["shared_account"] == shared_account.lower() and d["delegate_user_id"] == user_id
        ]

        if not matching:
            return False, "NO_DELEGATION_FOUND", None

        # Check covering delegation
        for d in matching:
            # Check revocation
            if d["status"] == DelegationState.REVOKED:
                if d["revoked_at"] and action_time >= d["revoked_at"]:
                    return False, f"DELEGATION_REVOKED: {d['revocation_reason']}", d

            if d["status"] == DelegationState.CANCELLED:
                return False, "DELEGATION_CANCELLED", d

            # Check validity window
            if d["start_time"] <= action_time <= d["end_time"]:
                if d["status"] == DelegationState.REVOKED:
                    return False, "DELEGATION_REVOKED", d
                return True, "AUTHORIZED", d

            if action_time > d["end_time"]:
                continue

            if action_time < d["start_time"]:
                continue

        # If has delegations but none covered the timestamp
        has_expired = any(d["end_time"] < action_time for d in matching)
        if has_expired:
            return False, "DELEGATION_EXPIRED", None

        return False, "ACTION_OUTSIDE_DELEGATION_WINDOW", None

    def get_active_delegations_for_account(
        self,
        shared_account: str,
        action_time: datetime
    ) -> List[Dict[str, Any]]:
        """Returns all delegations actively authorizing the given account at action_time."""
        active = []
        for d in self.delegations.values():
            if d["shared_account"] != shared_account.lower():
                continue
            if d["status"] in [DelegationState.REVOKED, DelegationState.CANCELLED]:
                continue
            if d["start_time"] <= action_time <= d["end_time"]:
                active.append(d)
        return active

    def _record_transition(self, delegation_id: str, from_state: str, to_state: str,
                           timestamp: datetime, actor: str, note: str):
        self.transition_history.append({
            "transition_id": f"TR-{uuid.uuid4().hex[:8]}",
            "delegation_id": delegation_id,
            "from_state": from_state,
            "to_state": to_state,
            "timestamp": timestamp,
            "actor": actor,
            "note": note
        })
