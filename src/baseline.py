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
from app.models.attribution_result import AttributionResult
from app.services.baseline import BaselineAttributionEngine


def evaluate_baseline_all(db=None) -> Dict[str, Any]:
    """
    Evaluates all system logs using the Baseline Attribution Engine:
    - 1 active authorized delegate -> ATTRIBUTED (confidence 60.0%)
    - >1 active authorized delegates -> AMBIGUOUS (confidence 30.0%)
    - 0 active authorized delegates -> UNATTRIBUTED (confidence 0.0%)
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        privileged_actions = db.query(PrivilegedAction).all()
        sensitive_names = set(pa.action_name for pa in privileged_actions)

        all_logs = db.query(SystemLog).filter(SystemLog.processing_status != "INVALID").all()
        sensitive_logs = [l for l in all_logs if l.action in sensitive_names]

        total_events = len(all_logs)
        total_sensitive = len(sensitive_logs)

        attributed = 0
        ambiguous = 0
        unattributed = 0

        for log in sensitive_logs:
            res = BaselineAttributionEngine.evaluate(db, log)
            status = res.get("status")
            if status == "ATTRIBUTED":
                attributed += 1
            elif status == "AMBIGUOUS":
                ambiguous += 1
            else:
                unattributed += 1

        attr_pct = round((attributed / total_sensitive * 100.0), 2) if total_sensitive > 0 else 0.0

        metrics = {
            "total_system_events": total_events,
            "total_sensitive_actions": total_sensitive,
            "baseline_attributed": attributed,
            "baseline_ambiguous": ambiguous,
            "baseline_unattributed": unattributed,
            "baseline_attribution_percentage": attr_pct
        }

        print("=" * 60)
        print("BASELINE ATTRIBUTION ENGINE EXECUTION RESULTS")
        print("=" * 60)
        print(f"Total System Events Ingested:    {total_events}")
        print(f"Total Sensitive Clinical Actions: {total_sensitive}")
        print(f"Baseline Attributed Actions:     {attributed}")
        print(f"Baseline Ambiguous Actions:      {ambiguous}")
        print(f"Baseline Unattributed Actions:   {unattributed}")
        print(f"Baseline Attribution Percentage: {attr_pct:.2f}%")
        print("=" * 60)

        return metrics
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    evaluate_baseline_all()
