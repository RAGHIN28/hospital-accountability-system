from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.system_log import SystemLog


class BaselineAttributionEngine:
    """
    Simple, deterministic, explainable baseline method:
    - Non-shared accounts: Direct match to user roster.
    - Shared accounts:
        * 1 active authorized user in shift window -> ATTRIBUTED (confidence 60.0%)
        * >1 active authorized users in shift window -> AMBIGUOUS (confidence 30.0%)
        * 0 active authorized users in shift window -> UNATTRIBUTED (confidence 0.0%)
    """

    @staticmethod
    def evaluate(db: Session, log: SystemLog) -> Dict[str, Any]:
        # 1. Check if the username corresponds to a shared account
        shared_account = db.query(SharedAccount).filter(SharedAccount.username == log.username).first()

        if not shared_account:
            # Check if this is a direct individual user account
            # Match by employee_id or username
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
                        "confidence": 100.0,
                        "explanation": f"Direct user account '{log.username}' authenticated directly to individual roster identity ({user.full_name})."
                    }
                else:
                    return {
                        "status": "UNATTRIBUTED",
                        "user_id": None,
                        "user_name": None,
                        "confidence": 0.0,
                        "explanation": f"Direct account '{log.username}' matched user ({user.full_name}) but user status is INACTIVE."
                    }
            else:
                return {
                    "status": "UNATTRIBUTED",
                    "user_id": None,
                    "user_name": None,
                    "confidence": 0.0,
                    "explanation": f"Account '{log.username}' is not a registered shared account and not found in employee roster."
                }

        # 2. It is a shared account. Query active authorizations covering log.timestamp
        authorizations: List[SharedAccountAuthorization] = db.query(SharedAccountAuthorization).filter(
            SharedAccountAuthorization.shared_account_id == shared_account.id,
            SharedAccountAuthorization.status == "ACTIVE",
            SharedAccountAuthorization.authorized_from <= log.timestamp,
            SharedAccountAuthorization.authorized_until >= log.timestamp
        ).all()

        # Check user active status for authorized users
        active_candidates = []
        for auth in authorizations:
            u = db.query(User).filter(User.id == auth.user_id, User.active == True).first()
            if u:
                active_candidates.append(u)

        if len(active_candidates) == 1:
            chosen = active_candidates[0]
            return {
                "status": "ATTRIBUTED",
                "user_id": chosen.id,
                "user_name": chosen.full_name,
                "confidence": 60.0,
                "explanation": (
                    f"Baseline Rule: Exactly 1 active authorized user ({chosen.full_name}, {chosen.role}) "
                    f"delegated for '{shared_account.username}' during event timestamp ({log.timestamp.strftime('%Y-%m-%d %H:%M:%S')})."
                )
            }
        elif len(active_candidates) > 1:
            names = ", ".join([u.full_name for u in active_candidates])
            return {
                "status": "AMBIGUOUS",
                "user_id": None,
                "user_name": None,
                "confidence": 30.0,
                "explanation": (
                    f"Baseline Rule: Multiple ({len(active_candidates)}) active authorized users ({names}) "
                    f"delegated simultaneously for '{shared_account.username}'. Baseline lacks session/network signals to differentiate."
                )
            }
        else:
            # Check if there were expired delegations
            expired_auth = db.query(SharedAccountAuthorization).filter(
                SharedAccountAuthorization.shared_account_id == shared_account.id,
                SharedAccountAuthorization.authorized_until < log.timestamp
            ).first()

            if expired_auth:
                reason = "All delegations for this shared account have expired before event timestamp."
            else:
                reason = f"No active delegation records found for shared account '{shared_account.username}' at event timestamp."

            return {
                "status": "UNATTRIBUTED",
                "user_id": None,
                "user_name": None,
                "confidence": 0.0,
                "explanation": f"Baseline Rule: {reason}"
            }
