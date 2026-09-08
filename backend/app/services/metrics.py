import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.system_log import SystemLog
from app.models.attribution_result import AttributionResult
from app.models.privileged_action import PrivilegedAction


class MetricsService:
    @staticmethod
    def calculate_attribution_metrics(db: Session) -> Dict[str, Any]:
        # 1. Fetch all privileged actions list
        privileged_actions = db.query(PrivilegedAction).all()
        sensitive_action_names = set(pa.action_name for pa in privileged_actions)

        # 2. Get all system logs that have completed processing
        all_logs = db.query(SystemLog).filter(SystemLog.processing_status != "INVALID").all()
        total_events = len(all_logs)

        # 3. Identify sensitive action logs
        sensitive_logs = [log for log in all_logs if log.action in sensitive_action_names]
        total_sensitive_actions = len(sensitive_logs)
        sensitive_event_ids = set(log.event_id for log in sensitive_logs)

        if total_sensitive_actions == 0:
            return {
                "total_events": total_events,
                "total_sensitive_actions": 0,
                "baseline_attributed": 0,
                "baseline_ambiguous": 0,
                "baseline_unattributed": 0,
                "baseline_attribution_percentage": 0.0,
                "prototype_attributed": 0,
                "prototype_ambiguous": 0,
                "prototype_unattributed": 0,
                "prototype_attribution_percentage": 0.0,
                "improvement_percentage": 0.0,
                "confidence_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNATTRIBUTED": 0, "AMBIGUOUS": 0},
                "failure_reasons": {},
                "method_distribution": {},
            }

        # 4. Fetch attribution results for sensitive logs
        results = db.query(AttributionResult).filter(AttributionResult.event_id.in_(sensitive_event_ids)).all()
        result_map = {res.event_id: res for res in results}

        # Baseline metrics
        baseline_attributed = 0
        baseline_ambiguous = 0
        baseline_unattributed = 0

        # Prototype metrics
        prototype_attributed = 0
        prototype_ambiguous = 0
        prototype_unattributed = 0

        confidence_dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNATTRIBUTED": 0, "AMBIGUOUS": 0}
        method_dist = {}
        failure_reasons = {
            "Multiple authorized users": 0,
            "Missing session ID": 0,
            "Missing delegation record": 0,
            "Expired authorization": 0,
            "Shared account used outside delegation window": 0,
            "Inactive user": 0,
            "Missing user roster": 0,
            "Conflicting signals": 0,
        }

        for log in sensitive_logs:
            res = result_map.get(log.event_id)
            if not res:
                baseline_unattributed += 1
                prototype_unattributed += 1
                confidence_dist["UNATTRIBUTED"] += 1
                failure_reasons["Missing delegation record"] += 1
                continue

            # Baseline check
            if res.baseline_status == "ATTRIBUTED":
                baseline_attributed += 1
            elif res.baseline_status == "AMBIGUOUS":
                baseline_ambiguous += 1
            else:
                baseline_unattributed += 1

            # Prototype check
            if res.attribution_status == "ATTRIBUTED":
                prototype_attributed += 1
            elif res.attribution_status == "AMBIGUOUS":
                prototype_ambiguous += 1
            else:
                prototype_unattributed += 1

            # Prototype Confidence distribution
            conf_level = res.confidence_level or "UNATTRIBUTED"
            confidence_dist[conf_level] = confidence_dist.get(conf_level, 0) + 1

            # Method distribution
            method = res.attribution_method or "UNRESOLVED"
            method_dist[method] = method_dist.get(method, 0) + 1

            # Failure reasons tracking for unresolved/ambiguous prototype events
            if res.attribution_status in ["UNATTRIBUTED", "AMBIGUOUS"]:
                expl = res.explanation.lower() if res.explanation else ""
                if "multiple" in expl or "competing" in expl:
                    failure_reasons["Multiple authorized users"] += 1
                elif "expired" in expl:
                    failure_reasons["Expired authorization"] += 1
                elif "missing session" in expl or "no session" in expl:
                    failure_reasons["Missing session ID"] += 1
                elif "inactive" in expl:
                    failure_reasons["Inactive user"] += 1
                elif "outside delegation" in expl:
                    failure_reasons["Shared account used outside delegation window"] += 1
                elif "not found in employee roster" in expl or "missing user roster" in expl:
                    failure_reasons["Missing user roster"] += 1
                elif "no candidate" in expl or "no active delegation" in expl or "no delegation" in expl:
                    failure_reasons["Missing delegation record"] += 1
                else:
                    failure_reasons["Conflicting signals"] += 1

        baseline_pct = round((baseline_attributed / total_sensitive_actions) * 100.0, 2)
        prototype_pct = round((prototype_attributed / total_sensitive_actions) * 100.0, 2)
        improvement_pct = round(prototype_pct - baseline_pct, 2)

        # Filter out 0 counts in failure reasons for cleaner response
        active_failures = {k: v for k, v in failure_reasons.items() if v > 0}

        return {
            "total_events": total_events,
            "total_sensitive_actions": total_sensitive_actions,
            "baseline_attributed": baseline_attributed,
            "baseline_ambiguous": baseline_ambiguous,
            "baseline_unattributed": baseline_unattributed,
            "baseline_attribution_percentage": baseline_pct,
            "prototype_attributed": prototype_attributed,
            "prototype_ambiguous": prototype_ambiguous,
            "prototype_unattributed": prototype_unattributed,
            "prototype_attribution_percentage": prototype_pct,
            "improvement_percentage": improvement_pct,
            "confidence_distribution": confidence_dist,
            "failure_reasons": active_failures,
            "method_distribution": method_dist,
        }
