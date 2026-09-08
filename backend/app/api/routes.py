import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.system_log import SystemLog
from app.models.privileged_action import PrivilegedAction
from app.models.attribution_result import AttributionResult
from app.schemas import (
    UserResponse,
    SharedAccountResponse,
    AuthorizationResponse,
    PrivilegedActionResponse,
    SystemLogResponse,
    AttributionResultResponse,
    EventDetailResponse,
    CandidateScore,
    MetricsBreakdown,
)
from app.services.event_processor import EventProcessor
from app.services.metrics import MetricsService

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Healthcheck endpoint returning database and system status."""
    try:
        user_count = db.query(User).count()
        logs_count = db.query(SystemLog).count()
        return {
            "status": "HEALTHY",
            "service": "Hospital Shared-Account Elimination & Attribution Service",
            "milestone": "35% Milestone Proof of Concept",
            "database": "CONNECTED",
            "total_users": user_count,
            "total_logs": logs_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database check failed: {str(e)}")


@router.get("/users", response_model=List[UserResponse])
def get_users(
    department: Optional[str] = None,
    workforce_type: Optional[str] = None,
    active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Retrieve hospital user roster with optional department/role filters."""
    query = db.query(User)
    if department:
        query = query.filter(User.department.ilike(f"%{department}%"))
    if workforce_type:
        query = query.filter(User.workforce_type == workforce_type)
    if active is not None:
        query = query.filter(User.active == active)
    return query.order_by(User.id).all()


@router.get("/shared-accounts", response_model=List[SharedAccountResponse])
def get_shared_accounts(db: Session = Depends(get_db)):
    """Retrieve shared account inventory with active authorized users count."""
    accounts = db.query(SharedAccount).all()
    results = []
    for acc in accounts:
        auths = db.query(SharedAccountAuthorization).filter(
            SharedAccountAuthorization.shared_account_id == acc.id,
            SharedAccountAuthorization.status == "ACTIVE"
        ).all()
        user_ids = [a.user_id for a in auths]
        users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
        results.append(SharedAccountResponse(
            id=acc.id,
            username=acc.username,
            system_name=acc.system_name,
            department=acc.department,
            account_type=acc.account_type,
            status=acc.status,
            risk_level=acc.risk_level,
            created_at=acc.created_at,
            authorized_users_count=len(users),
            active_authorized_users=[f"{u.full_name} ({u.role})" for u in users]
        ))
    return results


@router.get("/delegations", response_model=List[AuthorizationResponse])
def get_delegations(
    shared_account_id: Optional[int] = None,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retrieve delegation records."""
    query = db.query(SharedAccountAuthorization)
    if shared_account_id:
        query = query.filter(SharedAccountAuthorization.shared_account_id == shared_account_id)
    if user_id:
        query = query.filter(SharedAccountAuthorization.user_id == user_id)
    if status:
        query = query.filter(SharedAccountAuthorization.status == status)

    auths = query.order_by(desc(SharedAccountAuthorization.authorized_from)).all()
    res = []
    for a in auths:
        u = db.query(User).filter(User.id == a.user_id).first()
        sa = db.query(SharedAccount).filter(SharedAccount.id == a.shared_account_id).first()
        res.append(AuthorizationResponse(
            id=a.id,
            shared_account_id=a.shared_account_id,
            user_id=a.user_id,
            authorized_from=a.authorized_from,
            authorized_until=a.authorized_until,
            reason=a.reason,
            approved_by=a.approved_by,
            status=a.status,
            user_name=u.full_name if u else "Unknown",
            user_employee_id=u.employee_id if u else "Unknown",
            user_department=u.department if u else "Unknown",
            shared_account_name=sa.username if sa else "Unknown"
        ))
    return res


@router.get("/privileged-actions", response_model=List[PrivilegedActionResponse])
def get_privileged_actions(db: Session = Depends(get_db)):
    """Retrieve catalog of privileged/sensitive clinical actions."""
    return db.query(PrivilegedAction).order_by(PrivilegedAction.action_name).all()


@router.get("/logs", response_model=List[SystemLogResponse])
def get_logs(
    username: Optional[str] = None,
    action: Optional[str] = None,
    is_sensitive: Optional[bool] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """Query ingested system event logs with pagination and filters."""
    query = db.query(SystemLog)
    if username:
        query = query.filter(SystemLog.username.ilike(f"%{username}%"))
    if action:
        query = query.filter(SystemLog.action.ilike(f"%{action}%"))
    if status:
        query = query.filter(SystemLog.processing_status == status)

    priv_actions = {pa.action_name: pa.sensitivity_level for pa in db.query(PrivilegedAction).all()}

    if is_sensitive is True:
        query = query.filter(SystemLog.action.in_(list(priv_actions.keys())))
    elif is_sensitive is False:
        query = query.filter(SystemLog.action.not_in(list(priv_actions.keys())))

    logs = query.order_by(desc(SystemLog.timestamp)).offset(offset).limit(limit).all()

    response_items = []
    for log in logs:
        sens_level = priv_actions.get(log.action)
        response_items.append(SystemLogResponse(
            id=log.id,
            event_id=log.event_id,
            timestamp=log.timestamp,
            username=log.username,
            session_id=log.session_id,
            source_system=log.source_system,
            source_ip=log.source_ip,
            device_id=log.device_id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            success=log.success,
            raw_event_hash=log.raw_event_hash,
            received_at=log.received_at,
            processing_status=log.processing_status,
            is_sensitive=sens_level is not None,
            sensitivity_level=sens_level
        ))
    return response_items


@router.get("/attribution/results", response_model=List[AttributionResultResponse])
def get_attribution_results(
    status: Optional[str] = None,
    method: Optional[str] = None,
    confidence_level: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """Query attribution results with filters."""
    query = db.query(AttributionResult)
    if status:
        query = query.filter(AttributionResult.attribution_status == status)
    if method:
        query = query.filter(AttributionResult.attribution_method == method)
    if confidence_level:
        query = query.filter(AttributionResult.confidence_level == confidence_level)

    results = query.order_by(desc(AttributionResult.processed_at)).offset(offset).limit(limit).all()

    response_items = []
    for r in results:
        base_u = db.query(User).filter(User.id == r.baseline_user_id).first() if r.baseline_user_id else None
        attr_u = db.query(User).filter(User.id == r.attributed_user_id).first() if r.attributed_user_id else None

        scores = []
        if r.candidate_scores_json:
            try:
                scores_data = json.loads(r.candidate_scores_json)
                scores = [CandidateScore(**c) for c in scores_data]
            except Exception:
                pass

        response_items.append(AttributionResultResponse(
            id=r.id,
            event_id=r.event_id,
            baseline_user_id=r.baseline_user_id,
            baseline_user_name=base_u.full_name if base_u else None,
            baseline_confidence=r.baseline_confidence,
            baseline_status=r.baseline_status,
            baseline_explanation=r.baseline_explanation,
            attributed_user_id=r.attributed_user_id,
            attributed_user_name=attr_u.full_name if attr_u else None,
            attribution_method=r.attribution_method,
            confidence_score=r.confidence_score,
            confidence_level=r.confidence_level,
            attribution_status=r.attribution_status,
            explanation=r.explanation,
            processed_at=r.processed_at,
            candidate_scores=scores
        ))
    return response_items


@router.get("/attribution/metrics", response_model=MetricsBreakdown)
def get_metrics(db: Session = Depends(get_db)):
    """Calculate and return comparative attribution metrics for sensitive actions."""
    return MetricsService.calculate_attribution_metrics(db)


@router.get("/attribution/{event_id}", response_model=EventDetailResponse)
def get_attribution_detail(event_id: str, db: Session = Depends(get_db)):
    """Retrieve full audit detail for an event including candidate scores and evidence."""
    log = db.query(SystemLog).filter(SystemLog.event_id == event_id).first()
    if not log:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    shared_acc = db.query(SharedAccount).filter(SharedAccount.username == log.username).first()
    priv_action = db.query(PrivilegedAction).filter(PrivilegedAction.action_name == log.action).first()
    attr_res = db.query(AttributionResult).filter(AttributionResult.event_id == event_id).first()

    candidate_scores = []
    if attr_res and attr_res.candidate_scores_json:
        try:
            scores_data = json.loads(attr_res.candidate_scores_json)
            candidate_scores = [CandidateScore(**c) for c in scores_data]
        except Exception:
            pass

    base_user = db.query(User).filter(User.id == attr_res.baseline_user_id).first() if (attr_res and attr_res.baseline_user_id) else None
    attr_user = db.query(User).filter(User.id == attr_res.attributed_user_id).first() if (attr_res and attr_res.attributed_user_id) else None

    # Evidence checklist
    evidence_checklist = {
        "shared_account_detected": shared_acc is not None,
        "shared_account_name": shared_acc.username if shared_acc else None,
        "session_id_present": bool(log.session_id),
        "source_ip": log.source_ip,
        "device_id": log.device_id,
        "is_privileged_action": priv_action is not None,
        "sensitivity_level": priv_action.sensitivity_level if priv_action else "NORMAL",
        "duplicate_hash_verified": bool(log.raw_event_hash),
    }

    log_response = SystemLogResponse(
        id=log.id,
        event_id=log.event_id,
        timestamp=log.timestamp,
        username=log.username,
        session_id=log.session_id,
        source_system=log.source_system,
        source_ip=log.source_ip,
        device_id=log.device_id,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        success=log.success,
        raw_event_hash=log.raw_event_hash,
        received_at=log.received_at,
        processing_status=log.processing_status,
        is_sensitive=priv_action is not None,
        sensitivity_level=priv_action.sensitivity_level if priv_action else None
    )

    shared_acc_response = None
    if shared_acc:
        auths = db.query(SharedAccountAuthorization).filter(
            SharedAccountAuthorization.shared_account_id == shared_acc.id,
            SharedAccountAuthorization.status == "ACTIVE"
        ).all()
        u_ids = [a.user_id for a in auths]
        u_objs = db.query(User).filter(User.id.in_(u_ids)).all() if u_ids else []
        shared_acc_response = SharedAccountResponse(
            id=shared_acc.id,
            username=shared_acc.username,
            system_name=shared_acc.system_name,
            department=shared_acc.department,
            account_type=shared_acc.account_type,
            status=shared_acc.status,
            risk_level=shared_acc.risk_level,
            created_at=shared_acc.created_at,
            authorized_users_count=len(u_objs),
            active_authorized_users=[f"{u.full_name} ({u.role})" for u in u_objs]
        )

    priv_action_response = None
    if priv_action:
        priv_action_response = PrivilegedActionResponse(
            id=priv_action.id,
            action_name=priv_action.action_name,
            sensitivity_level=priv_action.sensitivity_level,
            description=priv_action.description
        )

    attr_response = None
    if attr_res:
        attr_response = AttributionResultResponse(
            id=attr_res.id,
            event_id=attr_res.event_id,
            baseline_user_id=attr_res.baseline_user_id,
            baseline_user_name=base_user.full_name if base_user else None,
            baseline_confidence=attr_res.baseline_confidence,
            baseline_status=attr_res.baseline_status,
            baseline_explanation=attr_res.baseline_explanation,
            attributed_user_id=attr_res.attributed_user_id,
            attributed_user_name=attr_user.full_name if attr_user else None,
            attribution_method=attr_res.attribution_method,
            confidence_score=attr_res.confidence_score,
            confidence_level=attr_res.confidence_level,
            attribution_status=attr_res.attribution_status,
            explanation=attr_res.explanation,
            processed_at=attr_res.processed_at,
            candidate_scores=candidate_scores
        )

    return EventDetailResponse(
        event=log_response,
        is_shared_account=shared_acc is not None,
        shared_account=shared_acc_response,
        privileged_action=priv_action_response,
        attribution=attr_response,
        baseline_attribution={
            "user": base_user.full_name if base_user else None,
            "status": attr_res.baseline_status if attr_res else "UNATTRIBUTED",
            "confidence": attr_res.baseline_confidence if attr_res else 0.0,
            "explanation": attr_res.baseline_explanation if attr_res else "Not evaluated"
        },
        prototype_attribution={
            "user": attr_user.full_name if attr_user else None,
            "method": attr_res.attribution_method if attr_res else "UNRESOLVED",
            "status": attr_res.attribution_status if attr_res else "UNATTRIBUTED",
            "score": attr_res.confidence_score if attr_res else 0.0,
            "level": attr_res.confidence_level if attr_res else "UNATTRIBUTED",
            "explanation": attr_res.explanation if attr_res else "Not evaluated"
        },
        candidate_scores=candidate_scores,
        evidence_checklist=evidence_checklist
    )


@router.post("/process-events")
def process_events(db: Session = Depends(get_db)):
    """Trigger the end-to-end attribution pipeline on all system events."""
    result = EventProcessor.process_all_unprocessed(db)
    metrics = MetricsService.calculate_attribution_metrics(db)
    return {
        "status": "SUCCESS",
        "processed_count": result["processed_count"],
        "metrics": metrics
    }
