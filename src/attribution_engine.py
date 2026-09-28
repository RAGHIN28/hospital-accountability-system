# -*- coding: utf-8 -*-
"""
Attribution Engine Execution & Batch Evaluation Harness.

Why this module exists:
- Provides an automated evaluation harness across all ingested clinical events.
- Enforces the Non-Forcing Fallback Principle: Never force-assign an identity when
  evidence is ambiguous; preserve ambiguity for human compliance review.
- Focuses evaluation strictly on sensitive clinical operations (narcotics dispensing,
  dosage alert overrides, chart modifications, ePHI exports) where individual
  accountability is legally and clinically paramount.
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, List

# Ensure backend and workspace directories are on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(BASE_DIR, "backend") not in sys.path:
    sys.path.append(os.path.join(BASE_DIR, "backend"))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.database import SessionLocal
from app.models.system_log import SystemLog
from app.models.privileged_action import PrivilegedAction
from app.services.attribution import PrototypeAttributionEngine, DEPT_NETWORK_MAP


def evaluate_prototype_all(db=None) -> Dict[str, Any]:
    """
    Evaluates all system logs using the Prototype Multi-Signal Attribution Engine.

    Why this scoring rubric is parameterized:
    - Signal 1: Active Delegation Window (+40 pts)
      Primary authorization signal: Clinician holds an explicit administrative shift grant.
    - Signal 2: Session Identity Binding (+30 pts)
      Direct authentication context: Workstation terminal session asserted by GINA/SSO.
    - Signal 3: Device Affinity / Station Match (+15 pts)
      Hardware context: Terminal fingerprint matches candidate's assigned clinical unit.
    - Signal 4: IP Subnet Compatibility (+10 pts)
      Network context: Subnet CIDR verifies physical ward/department location.
    - Signal 5: Department Alignment (+5 pts)
      Organizational context: Staff roster department matches shared account scope.

    Safety Decision Thresholds:
    - ATTRIBUTED: Top candidate scores >= 60 pts with a clear margin (> 10 pts over second).
    - AMBIGUOUS: Top candidate scores >= 40 pts but competing candidates are within 10 pts.
      Preserving ambiguity prevents false accusations when multiple staff share a terminal.
    - UNATTRIBUTED: Score < 60 pts or candidate pool is empty / unmapped.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Step 1: Isolate privileged actions from mundane operational noise
        # Why: Normal browsing or navigation does not trigger strict accountability auditing;
        # statutory focus is on narcotic dispensing, record overrides, and ePHI exports.
        privileged_actions = db.query(PrivilegedAction).all()
        sensitive_names = set(pa.action_name for pa in privileged_actions)

        # Step 2: Filter out malformed records (INVALID) to prevent corrupted logs from
        # polluting statistical metrics or skewing attribution rates.
        all_logs = db.query(SystemLog).filter(SystemLog.processing_status != "INVALID").all()
        sensitive_logs = [l for l in all_logs if l.action in sensitive_names]

        total_events = len(all_logs)
        total_sensitive = len(sensitive_logs)

        attributed = 0
        ambiguous = 0
        unattributed = 0
        confidence_tiers = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNATTRIBUTED": 0, "AMBIGUOUS": 0}
        methods = {}

        # Step 3: Evaluate each sensitive action deterministically
        for log in sensitive_logs:
            res = PrototypeAttributionEngine.evaluate(db, log)
            status = res.get("status")
            conf_level = res.get("confidence_level", "UNATTRIBUTED")
            method = res.get("method", "UNRESOLVED")

            confidence_tiers[conf_level] = confidence_tiers.get(conf_level, 0) + 1
            methods[method] = methods.get(method, 0) + 1

            if status == "ATTRIBUTED":
                attributed += 1
            elif status == "AMBIGUOUS":
                ambiguous += 1
            else:
                unattributed += 1

        # Step 4: Compute strict sensitive action attribution percentage
        # Note: Decoupled from project requirement coverage (91.15%)
        attr_pct = round((attributed / total_sensitive * 100.0), 2) if total_sensitive > 0 else 0.0

        metrics = {
            "total_system_events": total_events,
            "total_sensitive_actions": total_sensitive,
            "prototype_attributed": attributed,
            "prototype_ambiguous": ambiguous,
            "prototype_unattributed": unattributed,
            "prototype_attribution_percentage": attr_pct,
            "confidence_distribution": confidence_tiers,
            "method_distribution": methods
        }

        print("=" * 60)
        print("PROTOTYPE MULTI-SIGNAL ATTRIBUTION ENGINE RESULTS")
        print("=" * 60)
        print(f"Total System Events Ingested:    {total_events}")
        print(f"Total Sensitive Clinical Actions: {total_sensitive}")
        print(f"Prototype Attributed Actions:    {attributed}")
        print(f"Prototype Ambiguous Actions:     {ambiguous}")
        print(f"Prototype Unattributed Actions:   {unattributed}")
        print(f"Prototype Attribution Percentage: {attr_pct:.2f}%")
        print("-" * 60)
        print(f"Confidence Distribution: {confidence_tiers}")
        print(f"Attribution Methods:     {methods}")
        print("=" * 60)

        return metrics
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    evaluate_prototype_all()
