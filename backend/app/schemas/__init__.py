from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    employee_id: str
    full_name: str
    role: str
    workforce_type: str
    department: str
    active: bool = True


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SharedAccountBase(BaseModel):
    username: str
    system_name: str
    department: str
    account_type: str
    status: str = "ACTIVE"
    risk_level: str = "MEDIUM"


class SharedAccountCreate(SharedAccountBase):
    pass


class SharedAccountResponse(SharedAccountBase):
    id: int
    created_at: datetime
    authorized_users_count: Optional[int] = 0
    active_authorized_users: Optional[List[str]] = []
    model_config = ConfigDict(from_attributes=True)


class AuthorizationBase(BaseModel):
    shared_account_id: int
    user_id: int
    authorized_from: datetime
    authorized_until: datetime
    reason: str
    approved_by: str
    status: str = "ACTIVE"


class AuthorizationCreate(AuthorizationBase):
    pass


class AuthorizationResponse(AuthorizationBase):
    id: int
    user_name: Optional[str] = None
    user_employee_id: Optional[str] = None
    user_department: Optional[str] = None
    shared_account_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PrivilegedActionBase(BaseModel):
    action_name: str
    sensitivity_level: str
    description: str


class PrivilegedActionResponse(PrivilegedActionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SystemLogBase(BaseModel):
    event_id: str
    timestamp: datetime
    username: str
    session_id: Optional[str] = None
    source_system: str
    source_ip: str
    device_id: str
    action: str
    target_type: str
    target_id: str
    success: bool = True
    raw_event_hash: str
    processing_status: str = "NEW"


class SystemLogCreate(BaseModel):
    event_id: str
    timestamp: datetime
    username: str
    session_id: Optional[str] = None
    source_system: str
    source_ip: str
    device_id: str
    action: str
    target_type: str
    target_id: str
    success: bool = True


class SystemLogResponse(SystemLogBase):
    id: int
    received_at: datetime
    is_sensitive: bool = False
    sensitivity_level: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class CandidateScore(BaseModel):
    user_id: int
    employee_id: str
    full_name: str
    role: str
    department: str
    delegation_score: float = 0.0
    session_score: float = 0.0
    device_score: float = 0.0
    ip_score: float = 0.0
    department_score: float = 0.0
    total_score: float = 0.0
    matched_signals: List[str] = []
    missed_signals: List[str] = []
    notes: List[str] = []


class AttributionResultResponse(BaseModel):
    id: int
    event_id: str
    baseline_user_id: Optional[int] = None
    baseline_user_name: Optional[str] = None
    baseline_confidence: float
    baseline_status: str
    baseline_explanation: Optional[str] = None

    attributed_user_id: Optional[int] = None
    attributed_user_name: Optional[str] = None
    attribution_method: str
    confidence_score: float
    confidence_level: str
    attribution_status: str
    explanation: str
    processed_at: datetime
    candidate_scores: Optional[List[CandidateScore]] = None
    model_config = ConfigDict(from_attributes=True)


class EventDetailResponse(BaseModel):
    event: SystemLogResponse
    is_shared_account: bool
    shared_account: Optional[SharedAccountResponse] = None
    privileged_action: Optional[PrivilegedActionResponse] = None
    attribution: Optional[AttributionResultResponse] = None
    baseline_attribution: Dict[str, Any]
    prototype_attribution: Dict[str, Any]
    candidate_scores: List[CandidateScore] = []
    evidence_checklist: Dict[str, Any] = {}


class MetricsBreakdown(BaseModel):
    total_events: int
    total_sensitive_actions: int
    baseline_attributed: int
    baseline_ambiguous: int
    baseline_unattributed: int
    baseline_attribution_percentage: float

    prototype_attributed: int
    prototype_ambiguous: int
    prototype_unattributed: int
    prototype_attribution_percentage: float

    improvement_percentage: float
    confidence_distribution: Dict[str, int]
    failure_reasons: Dict[str, int]
    method_distribution: Dict[str, int]


class AdjudicationBase(BaseModel):
    case_id: str
    event_id: str
    decision: str
    reviewer: str
    findings: str
    status: str = "SUBMITTED"
    evidence_reference: Optional[str] = None


class AdjudicationCreate(AdjudicationBase):
    pass


class AdjudicationResponse(AdjudicationBase):
    id: int
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
