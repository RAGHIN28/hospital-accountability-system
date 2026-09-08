import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.system_log import SystemLog
from app.models.attribution_result import AttributionResult
from app.models.privileged_action import PrivilegedAction
from app.services.baseline import BaselineAttributionEngine
from app.services.attribution import PrototypeAttributionEngine


def calculate_event_hash(
    timestamp: datetime,
    username: str,
    source_system: str,
    source_ip: str,
    device_id: str,
    action: str,
    target_id: str
) -> str:
    """Compute SHA-256 fingerprint from immutable event payload fields."""
    ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
    payload = f"{ts_str}|{username}|{source_system}|{source_ip}|{device_id}|{action}|{target_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EventProcessor:
    """
    Hospital Event Ingestion & Processing Pipeline:
    - Ingests raw events immutably
    - Detects duplicates using unique event_id & SHA-256 raw_event_hash
    - Validates payload structure
    - Executes Baseline and Prototype attribution algorithms
    - Persists attribution results and links to audit trail
    - Implements resilient fallbacks for missing session, delegation, or roster data
    """

    @staticmethod
    def process_raw_event(db: Session, event_data: Dict[str, Any]) -> Dict[str, Any]:
        event_id = event_data.get("event_id")
        if not event_id:
            return {"status": "INVALID", "message": "Missing required field: event_id"}

        # 1. Validation
        required_fields = ["timestamp", "username", "source_system", "source_ip", "device_id", "action", "target_type", "target_id"]
        missing = [f for f in required_fields if event_data.get(f) is None]
        if missing:
            # We still record the log if possible, marked as INVALID
            raw_hash = calculate_event_hash(
                datetime.utcnow(),
                event_data.get("username", "UNKNOWN"),
                event_data.get("source_system", "UNKNOWN"),
                event_data.get("source_ip", "0.0.0.0"),
                event_data.get("device_id", "UNKNOWN"),
                event_data.get("action", "UNKNOWN"),
                event_data.get("target_id", "UNKNOWN")
            )
            log = SystemLog(
                event_id=event_id,
                timestamp=event_data.get("timestamp") or datetime.utcnow(),
                username=event_data.get("username", "UNKNOWN"),
                session_id=event_data.get("session_id"),
                source_system=event_data.get("source_system", "UNKNOWN"),
                source_ip=event_data.get("source_ip", "0.0.0.0"),
                device_id=event_data.get("device_id", "UNKNOWN"),
                action=event_data.get("action", "UNKNOWN"),
                target_type=event_data.get("target_type", "UNKNOWN"),
                target_id=event_data.get("target_id", "UNKNOWN"),
                success=event_data.get("success", False),
                raw_event_hash=raw_hash,
                processing_status="INVALID"
            )
            db.add(log)
            db.commit()
            return {"status": "INVALID", "message": f"Validation failed: missing {', '.join(missing)}"}

        timestamp = event_data["timestamp"]
        if isinstance(timestamp, str):
            # Parse ISO string
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except Exception:
                timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")

        raw_event_hash = calculate_event_hash(
            timestamp=timestamp,
            username=event_data["username"],
            source_system=event_data["source_system"],
            source_ip=event_data["source_ip"],
            device_id=event_data["device_id"],
            action=event_data["action"],
            target_id=event_data["target_id"]
        )

        # 2. Duplicate Detection
        # Check by event_id or raw_event_hash
        existing_log = db.query(SystemLog).filter(
            (SystemLog.event_id == event_id) | (SystemLog.raw_event_hash == raw_event_hash)
        ).first()

        if existing_log:
            # If the log already exists and was processed or marked duplicate, return duplicate response
            return {
                "status": "DUPLICATE",
                "message": f"Duplicate event rejected: matches existing log {existing_log.event_id} (hash {raw_event_hash[:12]}...)",
                "event_id": existing_log.event_id
            }

        # 3. Create Immutable Raw SystemLog
        log = SystemLog(
            event_id=event_id,
            timestamp=timestamp,
            username=event_data["username"],
            session_id=event_data.get("session_id"),
            source_system=event_data["source_system"],
            source_ip=event_data["source_ip"],
            device_id=event_data["device_id"],
            action=event_data["action"],
            target_type=event_data["target_type"],
            target_id=event_data["target_id"],
            success=event_data.get("success", True),
            raw_event_hash=raw_event_hash,
            received_at=datetime.utcnow(),
            processing_status="NEW"
        )
        db.add(log)
        db.flush()

        # 4. Process Attribution
        result = EventProcessor.run_attribution_for_log(db, log)
        log.processing_status = "PROCESSED"
        db.commit()

        return {
            "status": "PROCESSED",
            "event_id": log.event_id,
            "attribution": result
        }

    @staticmethod
    def run_attribution_for_log(db: Session, log: SystemLog) -> AttributionResult:
        """Runs both Baseline and Prototype engines for a given system log."""
        # 1. Baseline Attribution
        baseline_res = BaselineAttributionEngine.evaluate(db, log)

        # 2. Prototype Multi-signal Attribution
        proto_res = PrototypeAttributionEngine.evaluate(db, log)

        # Check if attribution record already exists for this event
        existing_result = db.query(AttributionResult).filter(AttributionResult.event_id == log.event_id).first()

        candidate_scores_json = json.dumps(proto_res.get("candidate_scores", []))

        if existing_result:
            existing_result.baseline_user_id = baseline_res.get("user_id")
            existing_result.baseline_confidence = baseline_res.get("confidence", 0.0)
            existing_result.baseline_status = baseline_res.get("status", "UNATTRIBUTED")
            existing_result.baseline_explanation = baseline_res.get("explanation")

            existing_result.attributed_user_id = proto_res.get("user_id")
            existing_result.attribution_method = proto_res.get("method", "UNRESOLVED")
            existing_result.confidence_score = proto_res.get("confidence_score", 0.0)
            existing_result.confidence_level = proto_res.get("confidence_level", "UNATTRIBUTED")
            existing_result.attribution_status = proto_res.get("status", "UNATTRIBUTED")
            existing_result.explanation = proto_res.get("explanation", "")
            existing_result.candidate_scores_json = candidate_scores_json
            existing_result.processed_at = datetime.utcnow()
            return existing_result
        else:
            attr_result = AttributionResult(
                event_id=log.event_id,
                baseline_user_id=baseline_res.get("user_id"),
                baseline_confidence=baseline_res.get("confidence", 0.0),
                baseline_status=baseline_res.get("status", "UNATTRIBUTED"),
                baseline_explanation=baseline_res.get("explanation"),
                attributed_user_id=proto_res.get("user_id"),
                attribution_method=proto_res.get("method", "UNRESOLVED"),
                confidence_score=proto_res.get("confidence_score", 0.0),
                confidence_level=proto_res.get("confidence_level", "UNATTRIBUTED"),
                attribution_status=proto_res.get("status", "UNATTRIBUTED"),
                explanation=proto_res.get("explanation", ""),
                candidate_scores_json=candidate_scores_json,
                processed_at=datetime.utcnow()
            )
            db.add(attr_result)
            db.flush()
            return attr_result

    @staticmethod
    def process_all_unprocessed(db: Session) -> Dict[str, Any]:
        """Batch process all NEW or unprocessed logs."""
        logs = db.query(SystemLog).filter(SystemLog.processing_status.in_(["NEW", "PROCESSED"])).all()
        processed_count = 0
        for log in logs:
            EventProcessor.run_attribution_for_log(db, log)
            log.processing_status = "PROCESSED"
            processed_count += 1
        db.commit()
        return {"processed_count": processed_count, "status": "COMPLETED"}
