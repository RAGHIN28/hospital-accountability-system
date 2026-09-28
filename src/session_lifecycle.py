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


class SessionState:
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    ENDED = "ENDED"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class SessionLifecycleManager:
    """
    Manages the lifecycle of clinical workstation sessions.

    States:
    - CREATED: Session token generated at workstation login.
    - ACTIVE: Workstation in active use; heartbeat or clinical actions occurring.
    - IDLE: No activity within idle threshold (e.g. 15 minutes).
    - ENDED: Explicit user logout.
    - EXPIRED: Inactivity exceeds configurable timeout (default: 30 minutes).
    - TERMINATED: Forced termination by security administrator or automated policy.

    Rules:
    - Sensitive actions performed after session expiration or termination are flagged.
    - Activity refreshes update last_activity and keep session ACTIVE if within timeout.
    """

    def __init__(self, default_timeout_minutes: int = 30, idle_threshold_minutes: int = 15):
        self.default_timeout = timedelta(minutes=default_timeout_minutes)
        self.idle_threshold = timedelta(minutes=idle_threshold_minutes)
        # session_id -> session record
        self.sessions: Dict[str, Dict[str, Any]] = {}
        # Session audit log
        self.session_events: List[Dict[str, Any]] = []

    def create_session(
        self,
        session_id: str,
        shared_account: str,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        source: str = "WORKSTATION_GINA",
        created_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Create or initialize a clinical session."""
        now = created_at or datetime.utcnow()

        if session_id in self.sessions:
            # Duplicate session creation
            return {
                "status": "DUPLICATE",
                "message": f"Session {session_id} already exists.",
                "session": self.sessions[session_id]
            }

        session_record = {
            "session_id": session_id,
            "shared_account": shared_account.lower(),
            "user_id": user_id,
            "device_id": device_id,
            "ip_address": ip_address,
            "source": source,
            "created_at": now,
            "last_activity": now,
            "ended_at": None,
            "status": SessionState.ACTIVE,
            "termination_reason": None
        }
        self.sessions[session_id] = session_record

        self.session_events.append({
            "event_type": "SESSION_CREATED",
            "session_id": session_id,
            "timestamp": now,
            "status": SessionState.ACTIVE,
            "note": f"Session started on {shared_account} by {user_id or 'UNKNOWN'}"
        })
        return session_record

    def record_activity(
        self,
        session_id: str,
        activity_timestamp: datetime,
        action_name: str = "USER_ACTION"
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Record clinical activity on the session.
        If current time exceeds last_activity + timeout, session is marked EXPIRED.
        Returns: (is_valid_activity, status, session_record)
        """
        session = self.sessions.get(session_id)
        if not session:
            return False, "UNKNOWN_SESSION", {}

        # If already ended or terminated
        if session["status"] in [SessionState.ENDED, SessionState.TERMINATED]:
            return False, f"SESSION_{session['status']}", session

        # Clinical Causality Check:
        # Prevents clock-skewed or backdated logs from claiming validity under a session
        # that was created subsequent to the clinical act.
        if activity_timestamp < session["created_at"]:
            return False, "TIMESTAMP_BEFORE_SESSION_START", session

        # Workstation Inactivity Timeout Check:
        # Aligns with hospital workstation security policy (default: 30 minutes).
        # Unattended clinical terminals that exceed the idle window are marked EXPIRED
        # to prevent unauthorized shoulder-surfing actions from being falsely attributed
        # to the previously logged-in clinician.
        inactivity_gap = activity_timestamp - session["last_activity"]
        if inactivity_gap > self.default_timeout:
            session["status"] = SessionState.EXPIRED
            session["ended_at"] = session["last_activity"] + self.default_timeout
            session["termination_reason"] = f"Inactivity timeout ({inactivity_gap.total_seconds() / 60:.1f} mins)"
            self.session_events.append({
                "event_type": "SESSION_EXPIRED",
                "session_id": session_id,
                "timestamp": activity_timestamp,
                "status": SessionState.EXPIRED,
                "note": session["termination_reason"]
            })
            return False, "SESSION_EXPIRED", session

        # Rolling Activity Refresh:
        # Active clinical engagement extends session validity, ensuring working clinicians
        # do not experience disruptive mid-procedure logouts while actively treating patients.
        session["last_activity"] = max(session["last_activity"], activity_timestamp)
        session["status"] = SessionState.ACTIVE
        return True, "ACTIVE", session

    def terminate_session(
        self,
        session_id: str,
        terminated_at: datetime,
        reason: str = "Administrative Security Override",
        terminated_by: str = "SOC_ADMIN"
    ) -> Dict[str, Any]:
        """Forcibly terminate a session."""
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(f"Session {session_id} not found")

        session["status"] = SessionState.TERMINATED
        session["ended_at"] = terminated_at
        session["termination_reason"] = reason

        self.session_events.append({
            "event_type": "SESSION_TERMINATED",
            "session_id": session_id,
            "timestamp": terminated_at,
            "status": SessionState.TERMINATED,
            "actor": terminated_by,
            "note": reason
        })
        return session

    def end_session(
        self,
        session_id: str,
        logout_timestamp: datetime
    ) -> Dict[str, Any]:
        """Normal user logout ending session."""
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(f"Session {session_id} not found")

        session["status"] = SessionState.ENDED
        session["ended_at"] = logout_timestamp
        session["last_activity"] = max(session["last_activity"], logout_timestamp)

        self.session_events.append({
            "event_type": "SESSION_ENDED",
            "session_id": session_id,
            "timestamp": logout_timestamp,
            "status": SessionState.ENDED,
            "note": "Normal user logout"
        })
        return session

    def is_session_valid(
        self,
        session_id: str,
        check_timestamp: datetime
    ) -> Tuple[bool, str]:
        """Evaluate if session is currently valid at check_timestamp."""
        session = self.sessions.get(session_id)
        if not session:
            return False, "UNKNOWN_SESSION"

        if session["status"] == SessionState.TERMINATED:
            return False, "SESSION_TERMINATED"

        if session["status"] == SessionState.ENDED:
            if check_timestamp > session["ended_at"]:
                return False, "SESSION_ENDED"

        if check_timestamp - session["last_activity"] > self.default_timeout:
            return False, "SESSION_EXPIRED"

        return True, "VALID"
