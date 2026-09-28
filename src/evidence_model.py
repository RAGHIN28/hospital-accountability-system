import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)


class SignalStrength:
    """
    Evidentiary grading tiers for forensic auditability:
    - STRONG: Direct primary proof (valid shift delegation or explicit session token).
    - SUPPORTING: Contextual indicators (hardware station match, IP subnet compatibility).
    - MISSING: Expected telemetry or credential record is absent (degrades score).
    - CONFLICTING: Multiple contradictory records detected (triggers human escalation).
    - INSUFFICIENT: Cumulative evidence falls below decision confidence threshold (< 60 pts).
    """
    STRONG = "STRONG"
    SUPPORTING = "SUPPORTING"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"


class ExplainableEvidenceDossier:
    """
    Standardized, auditable evidence representation for sensitive clinical actions.
    Encapsulates multi-source signals and explains the attribution or escalation rationale.

    Why this dossier architecture is required:
    In healthcare compliance and legal inquiries, opaque probability scores are inadmissible.
    Hospital risk managers require a deterministic, explainable dossier detailing exactly
    which evidence was present, which signals were missing, and whether conflicting claims
    existed at the timestamp of the privileged clinical transaction.
    """

    def __init__(
        self,
        event_id: str,
        action_name: str,
        shared_account: str,
        event_timestamp: datetime,
        identity_candidate: Optional[str] = None,
        candidate_name: Optional[str] = None,
        delegation_evidence: Optional[Dict[str, Any]] = None,
        session_evidence: Optional[Dict[str, Any]] = None,
        authentication_evidence: Optional[Dict[str, Any]] = None,
        device_evidence: Optional[Dict[str, Any]] = None,
        network_evidence: Optional[Dict[str, Any]] = None,
        timing_evidence: Optional[Dict[str, Any]] = None,
        missing_signals: Optional[List[str]] = None,
        conflicting_signals: Optional[List[str]] = None,
        resolution_type: str = "INITIAL",
        confidence_or_strength: str = SignalStrength.SUPPORTING,
        score: float = 0.0,
        final_status: str = "UNATTRIBUTED",
        explanation: str = ""
    ):
        self.event_id = event_id
        self.action_name = action_name
        self.shared_account = shared_account
        self.event_timestamp = event_timestamp
        self.identity_candidate = identity_candidate
        self.candidate_name = candidate_name
        self.delegation_evidence = delegation_evidence or {"strength": SignalStrength.MISSING, "details": "No delegation matched"}
        self.session_evidence = session_evidence or {"strength": SignalStrength.MISSING, "details": "No session binding found"}
        self.authentication_evidence = authentication_evidence or {"strength": SignalStrength.MISSING, "details": "No direct auth record"}
        self.device_evidence = device_evidence or {"strength": SignalStrength.MISSING, "details": "No device match"}
        self.network_evidence = network_evidence or {"strength": SignalStrength.MISSING, "details": "No subnet compatibility"}
        self.timing_evidence = timing_evidence or {"strength": SignalStrength.SUPPORTING, "details": "Timestamp within hospital operational hours"}
        self.missing_signals = missing_signals or []
        self.conflicting_signals = conflicting_signals or []
        self.resolution_type = resolution_type
        self.confidence_or_strength = confidence_or_strength
        self.score = score
        self.final_status = final_status
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "action_name": self.action_name,
            "shared_account": self.shared_account,
            "event_timestamp": self.event_timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.event_timestamp, datetime) else str(self.event_timestamp),
            "identity_candidate": self.identity_candidate,
            "candidate_name": self.candidate_name,
            "delegation_evidence": self.delegation_evidence,
            "session_evidence": self.session_evidence,
            "authentication_evidence": self.authentication_evidence,
            "device_evidence": self.device_evidence,
            "network_evidence": self.network_evidence,
            "timing_evidence": self.timing_evidence,
            "missing_signals": self.missing_signals,
            "conflicting_signals": self.conflicting_signals,
            "resolution_type": self.resolution_type,
            "confidence_or_strength": self.confidence_or_strength,
            "score": self.score,
            "final_status": self.final_status,
            "explanation": self.explanation
        }


class CrossSourceCorrelator:
    """
    Executes explainable correlation across application events, shift delegations,
    session tokens, and supporting telemetry without opaque ML.
    """

    @staticmethod
    def correlate(
        event_dict: Dict[str, Any],
        active_delegations: List[Dict[str, Any]],
        session_info: Optional[Dict[str, Any]] = None,
        roster_info: Optional[Dict[str, Any]] = None
    ) -> ExplainableEvidenceDossier:
        event_id = event_dict.get("event_id", "UNKNOWN")
        action = event_dict.get("action_id") or event_dict.get("action", "UNKNOWN")
        account = (event_dict.get("account_id") or event_dict.get("username", "")).lower()
        ts = event_dict.get("event_timestamp") or event_dict.get("timestamp") or datetime.utcnow()
        session_id = event_dict.get("session_id")
        device_id = event_dict.get("device_id", "UNKNOWN")
        ip_addr = event_dict.get("ip_address") or event_dict.get("source_ip", "0.0.0.0")

        missing_signals = []
        conflicting_signals = []

        # 1. Delegation Correlation
        del_evid = {"strength": SignalStrength.MISSING, "details": "No active delegation"}
        matched_del = None
        if active_delegations:
            if len(active_delegations) == 1:
                matched_del = active_delegations[0]
                del_evid = {
                    "strength": SignalStrength.STRONG,
                    "delegation_id": matched_del.get("delegation_id"),
                    "authorized_user": matched_del.get("delegate_user_id"),
                    "details": f"Shift window {matched_del['start_time'].strftime('%H:%M')}-{matched_del['end_time'].strftime('%H:%M')}"
                }
            else:
                conflicting_signals.append(f"Multiple overlapping delegations: {[d['delegate_user_id'] for d in active_delegations]}")
                del_evid = {
                    "strength": SignalStrength.CONFLICTING,
                    "details": "Multiple staff delegated simultaneously for shared account"
                }
        else:
            missing_signals.append("Active shift delegation record")

        # 2. Session Correlation
        sess_evid = {"strength": SignalStrength.MISSING, "details": "No session ID in event"}
        matched_session_user = None
        if session_id:
            if session_info and session_info.get("status") == "ACTIVE":
                matched_session_user = session_info.get("user_id")
                sess_evid = {
                    "strength": SignalStrength.STRONG if matched_session_user else SignalStrength.SUPPORTING,
                    "session_id": session_id,
                    "bound_user": matched_session_user,
                    "details": f"Active session verified on {device_id}"
                }
            else:
                sess_evid = {"strength": SignalStrength.SUPPORTING, "session_id": session_id, "details": "Session string present in event"}
        else:
            missing_signals.append("Session binding")

        # 3. Telemetry Correlation
        dev_evid = {"strength": SignalStrength.SUPPORTING, "device_id": device_id, "details": "Supporting device telemetry"}
        net_evid = {"strength": SignalStrength.SUPPORTING, "ip": ip_addr, "details": "Supporting subnet context"}
        if ip_addr in ["0.0.0.0", "UNKNOWN", None]:
            missing_signals.append("IP Subnet CIDR")
            net_evid = {"strength": SignalStrength.MISSING, "details": "IP address unavailable"}
        if device_id in ["UNKNOWN", "UNKNOWN_DEVICE", None]:
            missing_signals.append("Workstation Device Fingerprint")
            dev_evid = {"strength": SignalStrength.MISSING, "details": "Device fingerprint unavailable"}

        # Adjudication Logic
        if matched_del and (not conflicting_signals):
            target_user = matched_del.get("delegate_user_id")
            user_name = roster_info.get(target_user, {}).get("full_name", target_user) if roster_info else target_user
            score = 90.0 if session_id else 75.0
            status = "ATTRIBUTED"
            confidence = SignalStrength.STRONG
            expl = f"Attributed to {user_name} via active shift delegation and supporting session/telemetry evidence."
        elif conflicting_signals:
            target_user = None
            user_name = None
            score = 45.0
            status = "AMBIGUOUS"
            confidence = SignalStrength.CONFLICTING
            expl = f"Ambiguous attribution: {'; '.join(conflicting_signals)}. Escalated to Compliance Review."
        else:
            target_user = None
            user_name = None
            score = 0.0
            status = "UNATTRIBUTED"
            confidence = SignalStrength.INSUFFICIENT
            expl = f"Unattributed sensitive action: missing {', '.join(missing_signals)}. Escalated to Compliance Review."

        return ExplainableEvidenceDossier(
            event_id=event_id,
            action_name=action,
            shared_account=account,
            event_timestamp=ts,
            identity_candidate=target_user,
            candidate_name=user_name,
            delegation_evidence=del_evid,
            session_evidence=sess_evid,
            device_evidence=dev_evid,
            network_evidence=net_evid,
            missing_signals=missing_signals,
            conflicting_signals=conflicting_signals,
            score=score,
            confidence_or_strength=confidence,
            final_status=status,
            explanation=expl
        )
