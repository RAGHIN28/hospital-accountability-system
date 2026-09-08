import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.system_log import SystemLog


# Department IP Subnets & Device Prefixes for Network Fingerprinting
DEPT_NETWORK_MAP = {
    "Radiology": {"subnets": ["192.168.10."], "devices": ["RAD-WS-", "RAD-PACS-", "RAD-PORT-"]},
    "Laboratory": {"subnets": ["192.168.20."], "devices": ["LAB-PC-", "LAB-LIS-", "LAB-ANALYZER-"]},
    "Pharmacy": {"subnets": ["192.168.30."], "devices": ["PHARM-TERM-", "PHARM-DISP-"]},
    "Billing": {"subnets": ["192.168.40."], "devices": ["BILL-DESK-", "BILL-POS-"]},
    "Ward": {"subnets": ["192.168.50."], "devices": ["WARD-STN-", "WARD-TAB-", "WARD-CLINIC-"]},
    "Cardiology": {"subnets": ["192.168.60."], "devices": ["CARDIO-WS-", "ECG-TERM-"]},
    "IT Support": {"subnets": ["192.168.99.", "10.0.0."], "devices": ["IT-ADMIN-", "SOC-TERM-", "SRV-CON-"]},
}


class PrototypeAttributionEngine:
    """
    Multi-Signal Weighted Evidence Attribution Engine:
    1. Active Delegation Window: +40 pts
    2. Session Match / Binding:   +30 pts
    3. Device Affinity / Station: +15 pts
    4. IP Subnet Compatibility:   +10 pts
    5. Department Match:          +5 pts
    Total Maximum: 100 pts

    Confidence Tiers:
    - HIGH: 80 - 100
    - MEDIUM: 60 - 79
    - LOW: 40 - 59
    - UNATTRIBUTED / AMBIGUOUS: < 40 or Close Contenders (<= 5 pts)
    """

    @staticmethod
    def evaluate(db: Session, log: SystemLog) -> Dict[str, Any]:
        # Check if direct user account
        shared_account = db.query(SharedAccount).filter(SharedAccount.username == log.username).first()

        if not shared_account:
            user = db.query(User).filter(
                (User.employee_id.ilike(log.username)) |
                (User.full_name.ilike(log.username))
            ).first()

            if user:
                if user.active:
                    return {
                        "status": "ATTRIBUTED",
                        "user_id": user.id,
                        "user_name": user.full_name,
                        "method": "DIRECT_ACCOUNT",
                        "confidence_score": 100.0,
                        "confidence_level": "HIGH",
                        "explanation": f"Direct user account '{log.username}' uniquely identified as active user '{user.full_name}' ({user.role}, {user.department}).",
                        "candidate_scores": [],
                        "failure_reason": None,
                    }
                else:
                    return {
                        "status": "UNATTRIBUTED",
                        "user_id": None,
                        "user_name": None,
                        "method": "UNRESOLVED",
                        "confidence_score": 0.0,
                        "confidence_level": "UNATTRIBUTED",
                        "explanation": f"Direct account '{log.username}' corresponds to user '{user.full_name}' who is flagged as INACTIVE in HR roster.",
                        "candidate_scores": [],
                        "failure_reason": "Inactive user",
                    }
            else:
                return {
                    "status": "UNATTRIBUTED",
                    "user_id": None,
                    "user_name": None,
                    "method": "UNRESOLVED",
                    "confidence_score": 0.0,
                    "confidence_level": "UNATTRIBUTED",
                    "explanation": f"Account '{log.username}' is neither a recognized shared account nor found in user roster.",
                    "candidate_scores": [],
                    "failure_reason": "Missing user roster",
                }

        # Shared Account Attribution: Evaluate candidates
        # 1. Fetch all authorizations for this shared account
        all_authorizations = db.query(SharedAccountAuthorization).filter(
            SharedAccountAuthorization.shared_account_id == shared_account.id
        ).all()

        # 2. Gather candidate users:
        # Include users with delegations to this account, plus users in the same department
        candidate_ids = set()
        for auth in all_authorizations:
            candidate_ids.add(auth.user_id)

        # Also add users from the matching department (e.g. in case delegation was missed/delayed)
        dept_users = db.query(User).filter(User.department == shared_account.department).all()
        for u in dept_users:
            candidate_ids.add(u.id)

        if not candidate_ids:
            return {
                "status": "UNATTRIBUTED",
                "user_id": None,
                "user_name": None,
                "method": "UNRESOLVED",
                "confidence_score": 0.0,
                "confidence_level": "UNATTRIBUTED",
                "explanation": f"No candidate users found for shared account '{shared_account.username}' in authorization table or department roster.",
                "candidate_scores": [],
                "failure_reason": "Missing delegation record",
            }

        candidates = db.query(User).filter(User.id.in_(candidate_ids)).all()

        # Check session history to see if this session_id was associated with a specific user
        session_associated_user_id = None
        if log.session_id:
            # Look for explicit session binding or historical log in same session where user was determined or known
            # e.g., an earlier log in this session with single active delegation
            earlier_log = db.query(SystemLog).filter(
                SystemLog.session_id == log.session_id,
                SystemLog.id < log.id
            ).first() if log.id else None

            # Or check session ID naming convention or session prefix (e.g., SESS-<EMPLOYEE_ID>-...)
            for c in candidates:
                if c.employee_id.lower() in log.session_id.lower():
                    session_associated_user_id = c.id
                    break

        candidate_scores: List[Dict[str, Any]] = []

        for candidate in candidates:
            c_score = 0.0
            matched_signals = []
            missed_signals = []
            notes = []

            # A. Check active status
            if not candidate.active:
                notes.append("User is INACTIVE in HR roster - disqualified from attribution")
                candidate_scores.append({
                    "user_id": candidate.id,
                    "employee_id": candidate.employee_id,
                    "full_name": candidate.full_name,
                    "role": candidate.role,
                    "department": candidate.department,
                    "delegation_score": 0.0,
                    "session_score": 0.0,
                    "device_score": 0.0,
                    "ip_score": 0.0,
                    "department_score": 0.0,
                    "total_score": 0.0,
                    "matched_signals": [],
                    "missed_signals": ["Active User Status"],
                    "notes": notes,
                })
                continue

            # B. Delegation Window Match (+40 pts)
            # Find active authorization for this candidate covering log timestamp
            user_auth = next((
                a for a in all_authorizations
                if a.user_id == candidate.id and
                a.status == "ACTIVE" and
                a.authorized_from <= log.timestamp <= a.authorized_until
            ), None)

            delegation_pts = 0.0
            if user_auth:
                delegation_pts = 40.0
                matched_signals.append("Active Delegation Window (+40)")
                notes.append(f"Authorized shift: {user_auth.authorized_from.strftime('%H:%M')} to {user_auth.authorized_until.strftime('%H:%M')} ({user_auth.reason})")
            else:
                # Check expired
                expired_auth = next((
                    a for a in all_authorizations
                    if a.user_id == candidate.id and
                    a.authorized_until < log.timestamp
                ), None)
                if expired_auth:
                    missed_signals.append("Active Delegation Window (Expired)")
                    notes.append(f"Delegation expired at {expired_auth.authorized_until.strftime('%Y-%m-%d %H:%M')}")
                else:
                    missed_signals.append("Active Delegation Window")

            # C. Session Match (+30 pts)
            session_pts = 0.0
            if log.session_id:
                # 1. If session has user's employee_id tag
                if session_associated_user_id == candidate.id:
                    session_pts = 30.0
                    matched_signals.append("Session Identity Binding (+30)")
                    notes.append(f"Session '{log.session_id}' explicitly bound to user")
                # 2. Or if candidate has active delegation and session matches candidate's shift/department session prefix
                elif user_auth and (candidate.department.lower() in log.session_id.lower() or "shift" in log.session_id.lower()):
                    # Candidate is in active delegation and session pattern aligns
                    session_pts = 25.0
                    matched_signals.append("Session Context Correlation (+25)")
                    notes.append(f"Session '{log.session_id}' aligns with active shift window")
                else:
                    missed_signals.append("Session Match")
            else:
                missed_signals.append("Session ID (Missing in log)")
                notes.append("Log event has no session_id recorded")

            # D. Device Match (+15 pts)
            device_pts = 0.0
            dept_info = DEPT_NETWORK_MAP.get(candidate.department, {})
            dept_device_prefixes = dept_info.get("devices", [])
            if any(log.device_id.startswith(pref) for pref in dept_device_prefixes):
                device_pts = 15.0
                matched_signals.append(f"Device Station Match '{log.device_id}' (+15)")
            else:
                missed_signals.append(f"Device Station Match (Device '{log.device_id}' not typical for {candidate.department})")

            # E. IP Subnet Match (+10 pts)
            ip_pts = 0.0
            dept_subnets = dept_info.get("subnets", [])
            if any(log.source_ip.startswith(sub) for sub in dept_subnets):
                ip_pts = 10.0
                matched_signals.append(f"IP Subnet Match '{log.source_ip}' (+10)")
            else:
                missed_signals.append(f"IP Subnet Match (IP '{log.source_ip}' not in {candidate.department} subnet)")

            # F. Department Match (+5 pts)
            dept_pts = 0.0
            if candidate.department.lower() == shared_account.department.lower():
                dept_pts = 5.0
                matched_signals.append(f"Department Alignment ({candidate.department}) (+5)")
            else:
                missed_signals.append(f"Department Alignment (User {candidate.department} vs Account {shared_account.department})")

            total_pts = min(100.0, delegation_pts + session_pts + device_pts + ip_pts + dept_pts)

            candidate_scores.append({
                "user_id": candidate.id,
                "employee_id": candidate.employee_id,
                "full_name": candidate.full_name,
                "role": candidate.role,
                "department": candidate.department,
                "delegation_score": delegation_pts,
                "session_score": session_pts,
                "device_score": device_pts,
                "ip_score": ip_pts,
                "department_score": dept_pts,
                "total_score": total_pts,
                "matched_signals": matched_signals,
                "missed_signals": missed_signals,
                "notes": notes,
            })

        # Sort candidate scores descending by total_score
        candidate_scores.sort(key=lambda x: x["total_score"], reverse=True)

        if not candidate_scores:
            return {
                "status": "UNATTRIBUTED",
                "user_id": None,
                "user_name": None,
                "method": "UNRESOLVED",
                "confidence_score": 0.0,
                "confidence_level": "UNATTRIBUTED",
                "explanation": "No eligible candidate scores computed.",
                "candidate_scores": [],
                "failure_reason": "No eligible candidates",
            }

        top_candidate = candidate_scores[0]
        second_candidate = candidate_scores[1] if len(candidate_scores) > 1 else None

        # Determine confidence level string
        score = top_candidate["total_score"]
        if score >= 80:
            level = "HIGH"
        elif score >= 60:
            level = "MEDIUM"
        elif score >= 40:
            level = "LOW"
        else:
            level = "UNATTRIBUTED"

        # Check for ambiguity / close tie
        if second_candidate and second_candidate["total_score"] >= 40:
            diff = top_candidate["total_score"] - second_candidate["total_score"]
            if diff < 10.0:  # Within 10 points is ambiguous when multiple users have active credentials
                names = f"{top_candidate['full_name']} ({top_candidate['total_score']:.0f} pts) vs {second_candidate['full_name']} ({second_candidate['total_score']:.0f} pts)"
                return {
                    "status": "AMBIGUOUS",
                    "user_id": None,
                    "user_name": None,
                    "method": "UNRESOLVED",
                    "confidence_score": round((top_candidate["total_score"] + second_candidate["total_score"]) / 2, 1),
                    "confidence_level": "AMBIGUOUS",
                    "explanation": (
                        f"Ambiguous attribution: Multiple candidates have competing evidence within {diff:.1f} pts. "
                        f"Candidates: {names}. Additional biometric or terminal confirmation required."
                    ),
                    "candidate_scores": candidate_scores,
                    "failure_reason": "Multiple authorized users",
                }

        # Check threshold for successful attribution
        if score >= 60:
            # Determine attribution method description
            has_delegation = top_candidate["delegation_score"] > 0
            has_session = top_candidate["session_score"] > 0
            if has_delegation and has_session:
                method = "SESSION_AND_DELEGATION"
            elif has_delegation:
                method = "DELEGATION_MATCH"
            elif has_session:
                method = "SESSION_MATCH"
            else:
                method = "BASELINE"

            explanation_lines = [
                f"Attributed to {top_candidate['full_name']} ({top_candidate['employee_id']}, {top_candidate['role']}) "
                f"with {level} confidence ({score:.1f}/100) using {method}."
            ]
            explanation_lines.append("Evidence breakdown:")
            for sig in top_candidate["matched_signals"]:
                explanation_lines.append(f"  • {sig}")
            if top_candidate["notes"]:
                for n in top_candidate["notes"]:
                    explanation_lines.append(f"  Note: {n}")

            return {
                "status": "ATTRIBUTED",
                "user_id": top_candidate["user_id"],
                "user_name": top_candidate["full_name"],
                "method": method,
                "confidence_score": score,
                "confidence_level": level,
                "explanation": "\n".join(explanation_lines),
                "candidate_scores": candidate_scores,
                "failure_reason": None,
            }
        else:
            # Score below 60 -> Unattributed or Low confidence failure
            failure_reason = "Shared account used outside delegation window"
            if not any(c["delegation_score"] > 0 for c in candidate_scores):
                # Check if expired
                has_expired = any("Expired" in " ".join(c["missed_signals"]) for c in candidate_scores)
                if has_expired:
                    failure_reason = "Expired authorization"
                else:
                    failure_reason = "Missing delegation record"
            elif not log.session_id:
                failure_reason = "Missing session ID"

            return {
                "status": "UNATTRIBUTED",
                "user_id": None,
                "user_name": None,
                "method": "UNRESOLVED",
                "confidence_score": score,
                "confidence_level": "UNATTRIBUTED",
                "explanation": (
                    f"Insufficient evidence to reliably attribute shared account '{shared_account.username}' "
                    f"(Top candidate {top_candidate['full_name']} achieved only {score:.1f}/100 points, threshold 60 required). "
                    f"Reason: {failure_reason}."
                ),
                "candidate_scores": candidate_scores,
                "failure_reason": failure_reason,
            }
