"""
API Security & Hardening Test Suite (Review 3 — Work Package R3.1)
Hospital Shared-Account Elimination & Accountable Action Attribution PoC

Test Categories:
  A. Health / Basic Availability
  B. Valid Requests across all 10 Endpoints
  C. Invalid Input & Boundary Validation
  D. Not Found / Resource Errors & Information Leakage Prevention
  E. HTTP Method Security (Verb Restrictions & 405 Responses)
  F. Authentication / Authorization Boundary Audit
  G. Input Validation / Injection Resilience (SQLi, XSS, Traversal, Buffer)
  H. Database Security & Integrity Constraints (Unique, Nullable, Rollback)
  I. Error Boundary & Non-Forcing Fallback Verification
"""

import os
import sys
import json
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app
from app.database import get_db, Base
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.privileged_action import PrivilegedAction
from app.models.system_log import SystemLog
from app.models.attribution_result import AttributionResult
from app.services.attribution import PrototypeAttributionEngine
from app.services.baseline import BaselineAttributionEngine
from app.services.event_processor import EventProcessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Standard TestClient against the existing application and seeded DB."""
    return TestClient(app)


@pytest.fixture
def isolated_db():
    """Create a pristine, isolated in-memory SQLite session with StaticPool for cross-thread test isolation."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Seed test users
    u1 = User(id=1, employee_id="SEC_EMP001", full_name="Dr. Alice Smith", role="Consultant", workforce_type="Permanent Staff", department="Cardiology", active=True)
    u2 = User(id=2, employee_id="SEC_EMP002", full_name="Nurse Bob Jones", role="Staff Nurse", workforce_type="Permanent Staff", department="Cardiology", active=True)
    session.add_all([u1, u2])

    # Seed test shared account
    sa = SharedAccount(id=1, username="cardio_workstation", system_name="EMR", department="Cardiology", account_type="DEPARTMENTAL_WORKSTATION", status="ACTIVE", risk_level="HIGH")
    session.add(sa)

    # Seed test privileged action
    pa = PrivilegedAction(id=1, action_name="VIEW_PATIENT_CHART", sensitivity_level="HIGH", description="Access cardiac record")
    session.add(pa)

    # Seed test delegation
    now = datetime.utcnow()
    auth = SharedAccountAuthorization(
        id=1,
        shared_account_id=1,
        user_id=1,
        authorized_from=now - timedelta(hours=2),
        authorized_until=now + timedelta(hours=6),
        reason="Cardiac shift",
        approved_by="ADMIN",
        status="ACTIVE"
    )
    session.add(auth)

    # Seed test log
    log = SystemLog(
        id=1,
        event_id="SEC-EVT-001",
        timestamp=now,
        username="cardio_workstation",
        session_id="SESS-CARDIO-1",
        source_system="EMR",
        source_ip="10.0.1.20",
        device_id="DEV-WS-01",
        action="VIEW_PATIENT_CHART",
        target_type="PATIENT_CHART",
        target_id="PAT-999",
        success=True,
        raw_event_hash="mock_hash_001",
        processing_status="NEW"
    )
    session.add(log)

    session.commit()
    yield session
    session.close()


@pytest.fixture
def isolated_client(isolated_db):
    """TestClient overriding get_db dependency with isolated in-memory DB."""
    def override_get_db():
        try:
            yield isolated_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# CATEGORY A: HEALTH & BASIC AVAILABILITY
# ---------------------------------------------------------------------------

def test_api_health_endpoint_success(client):
    """A1: Verify GET /api/health returns 200 OK with expected structure."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["database"] == "CONNECTED"
    assert "total_users" in data
    assert "total_logs" in data
    assert data["total_users"] >= 0
    assert data["total_logs"] >= 0


def test_api_health_content_type(client):
    """A2: Verify health endpoint returns JSON content type."""
    response = client.get("/api/health")
    assert response.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# CATEGORY B: VALID REQUESTS ACROSS ALL 10 ENDPOINTS
# ---------------------------------------------------------------------------

def test_get_users_endpoint(client):
    """B1: Verify GET /api/users returns roster list with expected user schema."""
    response = client.get("/api/users")
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) >= 1
    sample = users[0]
    for field in ["id", "employee_id", "full_name", "role", "workforce_type", "department", "active"]:
        assert field in sample


def test_get_users_with_filter(client):
    """B2: Verify GET /api/users with department filter returns matches."""
    response = client.get("/api/users", params={"department": "Radiology"})
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    for u in users:
        assert "radiology" in u["department"].lower()


def test_get_shared_accounts_endpoint(client):
    """B3: Verify GET /api/shared-accounts returns inventory with authorized user count."""
    response = client.get("/api/shared-accounts")
    assert response.status_code == 200
    accounts = response.json()
    assert isinstance(accounts, list)
    assert len(accounts) >= 1
    sample = accounts[0]
    for field in ["id", "username", "system_name", "department", "risk_level", "authorized_users_count"]:
        assert field in sample


def test_get_delegations_endpoint(client):
    """B4: Verify GET /api/delegations returns clinical authorizations."""
    response = client.get("/api/delegations")
    assert response.status_code == 200
    delegations = response.json()
    assert isinstance(delegations, list)
    assert len(delegations) >= 1
    sample = delegations[0]
    for field in ["id", "shared_account_id", "user_id", "authorized_from", "authorized_until", "status"]:
        assert field in sample


def test_get_delegations_filtered_by_status(client):
    """B5: Verify GET /api/delegations filter by status parameter."""
    response = client.get("/api/delegations", params={"status": "ACTIVE"})
    assert response.status_code == 200
    delegations = response.json()
    for d in delegations:
        assert d["status"] == "ACTIVE"


def test_get_privileged_actions_endpoint(client):
    """B6: Verify GET /api/privileged-actions returns action catalog."""
    response = client.get("/api/privileged-actions")
    assert response.status_code == 200
    actions = response.json()
    assert isinstance(actions, list)
    assert len(actions) >= 1
    sample = actions[0]
    for field in ["id", "action_name", "sensitivity_level", "description"]:
        assert field in sample


def test_get_logs_endpoint_pagination(client):
    """B7: Verify GET /api/logs with pagination limit and offset."""
    response = client.get("/api/logs", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    logs = response.json()
    assert isinstance(logs, list)
    assert len(logs) <= 5
    if len(logs) > 0:
        sample = logs[0]
        for field in ["id", "event_id", "timestamp", "username", "action", "processing_status"]:
            assert field in sample


def test_get_logs_filter_sensitive(client):
    """B8: Verify GET /api/logs filter by is_sensitive boolean."""
    response = client.get("/api/logs", params={"is_sensitive": True, "limit": 10})
    assert response.status_code == 200
    logs = response.json()
    for l in logs:
        assert l["is_sensitive"] is True


def test_get_attribution_results_endpoint(client):
    """B9: Verify GET /api/attribution/results returns results with attribution fields."""
    response = client.get("/api/attribution/results", params={"limit": 5})
    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    if len(results) > 0:
        sample = results[0]
        for field in ["id", "event_id", "confidence_score", "attribution_status", "attribution_method"]:
            assert field in sample


def test_get_attribution_metrics_endpoint(client):
    """B10: Verify GET /api/attribution/metrics returns comprehensive metrics breakdown."""
    response = client.get("/api/attribution/metrics")
    assert response.status_code == 200
    metrics = response.json()
    for field in [
        "total_events",
        "total_sensitive_actions",
        "baseline_attributed",
        "baseline_attribution_percentage",
        "prototype_attributed",
        "prototype_attribution_percentage",
        "improvement_percentage",
        "confidence_distribution",
        "failure_reasons",
        "method_distribution"
    ]:
        assert field in metrics
    assert metrics["prototype_attribution_percentage"] >= metrics["baseline_attribution_percentage"]


def test_get_attribution_detail_valid_event(client):
    """B11: Verify GET /api/attribution/{event_id} returns complete dossier for known event."""
    response = client.get("/api/attribution/EVT-00001")
    assert response.status_code == 200
    detail = response.json()
    assert "event" in detail
    assert "is_shared_account" in detail
    assert "baseline_attribution" in detail
    assert "prototype_attribution" in detail
    assert "candidate_scores" in detail
    assert "evidence_checklist" in detail


def test_post_process_events_isolated(isolated_client):
    """B12: Verify POST /api/process-events executes attribution pipeline without errors."""
    response = isolated_client.post("/api/process-events")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "processed_count" in data
    assert "metrics" in data


# ---------------------------------------------------------------------------
# CATEGORY C: INVALID INPUT & PARAMETER VALIDATION
# ---------------------------------------------------------------------------

def test_invalid_boolean_param_users(client):
    """C1: Verify non-boolean value for 'active' returns 422 Unprocessable Entity."""
    response = client.get("/api/users", params={"active": "invalid_bool_value"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_integer_param_delegations_user_id(client):
    """C2: Verify non-integer value for 'user_id' returns 422 Unprocessable Entity."""
    response = client.get("/api/delegations", params={"user_id": "not_an_int"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_integer_param_delegations_shared_account_id(client):
    """C3: Verify non-integer value for 'shared_account_id' returns 422 Unprocessable Entity."""
    response = client.get("/api/delegations", params={"shared_account_id": "alpha"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_pagination_limit_exceeds_max(client):
    """C4: Verify limit > 500 on /api/logs returns 422 (le=500 constraint)."""
    response = client.get("/api/logs", params={"limit": 99999})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_pagination_negative_offset(client):
    """C5: Verify negative offset on /api/logs returns 422 (ge=0 constraint)."""
    response = client.get("/api/logs", params={"offset": -10})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_boolean_sensitive_logs(client):
    """C6: Verify non-boolean 'is_sensitive' returns 422."""
    response = client.get("/api/logs", params={"is_sensitive": "perhaps"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_results_limit_exceeds_max(client):
    """C7: Verify limit > 500 on /api/attribution/results returns 422."""
    response = client.get("/api/attribution/results", params={"limit": 501})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_results_negative_offset(client):
    """C8: Verify negative offset on /api/attribution/results returns 422."""
    response = client.get("/api/attribution/results", params={"offset": -1})
    assert response.status_code == 422
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# CATEGORY D: RESOURCE NOT FOUND & INFORMATION LEAKAGE PREVENTION
# ---------------------------------------------------------------------------

def test_attribution_detail_nonexistent_event_returns_404(client):
    """D1: Verify querying nonexistent event_id returns clean 404."""
    response = client.get("/api/attribution/NON_EXISTENT_EVT_99999")
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert "NON_EXISTENT_EVT_99999" in body["detail"]


def test_nonexistent_api_route_returns_404(client):
    """D2: Verify accessing undefined route returns controlled 404."""
    response = client.get("/api/nonexistent_service_path")
    assert response.status_code == 404


def test_filter_nonexistent_department_returns_empty_list(client):
    """D3: Verify filtering for nonexistent department returns [] without 500 crash."""
    response = client.get("/api/users", params={"department": "NonExistentDept_XYZ_123"})
    assert response.status_code == 200
    assert response.json() == []


def test_filter_nonexistent_delegation_user_returns_empty_list(client):
    """D4: Verify filtering delegations for nonexistent user_id returns [] gracefully."""
    response = client.get("/api/delegations", params={"user_id": 999999})
    assert response.status_code == 200
    assert response.json() == []


def test_error_response_no_traceback_leakage(client):
    """D5: Verify 404 and 422 responses do not leak Python stack traces, paths, or secrets."""
    for url in ["/api/attribution/NOT_FOUND_EVT", "/api/logs?limit=99999"]:
        res = client.get(url)
        text = res.text
        assert "Traceback (most recent call last)" not in text
        assert "File \"" not in text
        assert "sqlite:///" not in text
        assert "password" not in text.lower()


# ---------------------------------------------------------------------------
# CATEGORY E: HTTP METHOD SECURITY (VERB RESTRICTIONS)
# ---------------------------------------------------------------------------

def test_disallowed_methods_on_health_endpoint(client):
    """E1: Verify GET-only /api/health rejects POST, PUT, DELETE, PATCH with 405."""
    for method in ["post", "put", "delete", "patch"]:
        caller = getattr(client, method)
        response = caller("/api/health")
        assert response.status_code == 405, f"Expected 405 for {method.upper()} /api/health"


def test_disallowed_methods_on_users_endpoint(client):
    """E2: Verify GET-only /api/users rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/users")
        assert response.status_code == 405, f"Expected 405 for {method.upper()} /api/users"


def test_disallowed_methods_on_shared_accounts(client):
    """E3: Verify GET-only /api/shared-accounts rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/shared-accounts")
        assert response.status_code == 405


def test_disallowed_methods_on_delegations(client):
    """E4: Verify GET-only /api/delegations rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/delegations")
        assert response.status_code == 405


def test_disallowed_methods_on_privileged_actions(client):
    """E5: Verify GET-only /api/privileged-actions rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/privileged-actions")
        assert response.status_code == 405


def test_disallowed_methods_on_logs(client):
    """E6: Verify GET-only /api/logs rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/logs")
        assert response.status_code == 405


def test_disallowed_methods_on_attribution_metrics(client):
    """E7: Verify GET-only /api/attribution/metrics rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/attribution/metrics")
        assert response.status_code == 405


def test_disallowed_methods_on_attribution_results(client):
    """E8: Verify GET-only /api/attribution/results rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/attribution/results")
        assert response.status_code == 405


def test_disallowed_methods_on_attribution_detail(client):
    """E9: Verify GET-only /api/attribution/{event_id} rejects POST, PUT, DELETE with 405."""
    for method in ["post", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/attribution/EVT-00001")
        assert response.status_code == 405


def test_disallowed_methods_on_process_events(client):
    """E10: Verify POST-only /api/process-events rejects GET, PUT, DELETE with 405."""
    for method in ["get", "put", "delete"]:
        caller = getattr(client, method)
        response = caller("/api/process-events")
        assert response.status_code == 405, f"Expected 405 for {method.upper()} /api/process-events"


# ---------------------------------------------------------------------------
# CATEGORY F: AUTHENTICATION / AUTHORIZATION AUDIT & BOUNDARY
# ---------------------------------------------------------------------------

def test_auth_boundary_unauthenticated_requests_succeed(client):
    """
    F1: Audit verification — unauthenticated requests succeed across read endpoints.
    In this academic PoC, API endpoints are designed as open evaluation interfaces
    without HTTP authentication headers or API keys.
    """
    endpoints = ["/api/health", "/api/users", "/api/shared-accounts", "/api/delegations", "/api/privileged-actions"]
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} unexpectedly failed unauthenticated"


def test_auth_boundary_arbitrary_bearer_token_ignored(client):
    """
    F2: Verify that supplying arbitrary Authorization: Bearer headers does not crash
    or trigger unhandled exceptions (system does not parse unconfigured auth).
    """
    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy.token"}
    response = client.get("/api/health", headers=headers)
    assert response.status_code == 200


def test_auth_boundary_demo_roles_not_enforced_at_api_level(client):
    """
    F3: Verify that dashboard personas (e.g. 'Auditor', 'Student') are not enforced
    at API layer via custom headers, confirming that the Streamlit role selector
    is strictly a presentation persona and not enterprise RBAC.
    """
    for role in ["Compliance Officer", "Security Analyst", "Auditor", "Student / Reviewer"]:
        res = client.get("/api/users", headers={"X-User-Role": role})
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# CATEGORY G: INPUT VALIDATION & INJECTION RESILIENCE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "' UNION SELECT 1, 'admin', 'pass' --",
    "admin' --",
    "\" OR \"\"=\"",
])
def test_sql_injection_resilience_query_params(client, payload):
    """G1: Verify SQL injection strings in query parameters are safely parameterized by SQLAlchemy."""
    # Test on users department filter
    res_users = client.get("/api/users", params={"department": payload})
    assert res_users.status_code == 200
    assert isinstance(res_users.json(), list)

    # Test on logs username filter
    res_logs = client.get("/api/logs", params={"username": payload})
    assert res_logs.status_code == 200
    assert isinstance(res_logs.json(), list)


@pytest.mark.parametrize("payload", [
    "' OR '1'='1",
    "'; DROP TABLE system_logs; --",
    "EVT-00001' OR '1'='1",
    "1' UNION SELECT 1--",
])
def test_sql_injection_resilience_path_param(client, payload):
    """G2: Verify SQL injection strings in path parameters do not execute raw queries."""
    res = client.get(f"/api/attribution/{payload}")
    assert res.status_code == 404  # Not found, safely parameterized
    assert "detail" in res.json()


@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert('xss')>",
    "<svg/onload=alert('xss')>",
    "<admin>",
    "</response><injected>",
])
def test_xss_html_injection_resilience_query_params(client, payload):
    """G3a: Verify XSS/HTML payloads in query parameters are safely handled as literal strings."""
    res_users = client.get("/api/users", params={"department": payload})
    assert res_users.status_code == 200
    assert isinstance(res_users.json(), list)

    res_logs = client.get("/api/logs", params={"username": payload})
    assert res_logs.status_code == 200
    assert isinstance(res_logs.json(), list)


@pytest.mark.parametrize("payload", [
    "<admin>",
    "<script>",
    "injected_tag",
    "%3Cscript%3Ealert(1)%3C%2Fscript%3E",
])
def test_xss_html_injection_resilience_path_param(client, payload):
    """G3b: Verify XSS/HTML payloads in event_id path parameter return 404 without script execution."""
    res_event = client.get(f"/api/attribution/{payload}")
    assert res_event.status_code == 404
    assert "detail" in res_event.json()


@pytest.mark.parametrize("payload", [
    "../../etc/passwd",
    "..\\..\\windows\\system32\\drivers\\etc\\hosts",
    "/etc/shadow",
    "....//....//etc/passwd",
])
def test_path_traversal_resilience_query_params(client, payload):
    """G4a: Verify directory traversal strings in query parameters are treated as literal strings."""
    res_users = client.get("/api/users", params={"department": payload})
    assert res_users.status_code == 200
    assert res_users.json() == []

    res_logs = client.get("/api/logs", params={"username": payload})
    assert res_logs.status_code == 200
    assert res_logs.json() == []


@pytest.mark.parametrize("payload", [
    "%2E%2E%2F%2E%2E%2Fetc%2Fpasswd",
    "%2Fetc%2Fshadow",
    "..%5C..%5Cwindows%5Csystem32%5Chosts",
])
def test_path_traversal_resilience_path_param(client, payload):
    """G4b: Verify encoded directory traversal strings in path parameter return 404 without file access."""
    res = client.get(f"/api/attribution/{payload}")
    assert res.status_code in [404, 422]
    assert "detail" in res.json()


def test_extraordinarily_long_input_string(client):
    """G5: Verify handling of buffer-length input (10,000 chars) without server crash."""
    long_str = "A" * 10000
    res = client.get("/api/users", params={"department": long_str})
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.parametrize("payload", [
    "🏥🏨💉🧪⚕️",
    "üñîçødé_clïnïcål_tèst",
    "اختبار_عربي",
    "中文测试",
    "русский_тест",
])
def test_unicode_and_multilingual_resilience(client, payload):
    """G6: Verify multibyte UTF-8 and emoji inputs are processed cleanly."""
    res = client.get("/api/users", params={"department": payload})
    assert res.status_code == 200


def test_unexpected_whitespace_handling(client):
    """G7: Verify inputs with leading, trailing, and embedded whitespace."""
    res = client.get("/api/users", params={"department": "   Cardiology   "})
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# CATEGORY H: DATABASE SECURITY & INTEGRITY CONSTRAINTS
# ---------------------------------------------------------------------------

def test_db_unique_constraint_employee_id(isolated_db):
    """H1: Verify User.employee_id unique constraint prevents duplicate employee records."""
    dup_user = User(
        employee_id="SEC_EMP001",  # Already seeded in isolated_db
        full_name="Duplicate Employee",
        role="Consultant",
        workforce_type="Permanent Staff",
        department="Cardiology",
        active=True
    )
    isolated_db.add(dup_user)
    with pytest.raises(IntegrityError):
        isolated_db.commit()
    isolated_db.rollback()


def test_db_unique_constraint_shared_account_username(isolated_db):
    """H2: Verify SharedAccount.username unique constraint enforces uniqueness."""
    dup_acc = SharedAccount(
        username="cardio_workstation",  # Already seeded
        system_name="EMR2",
        department="Cardiology",
        account_type="WORKSTATION",
        status="ACTIVE",
        risk_level="HIGH"
    )
    isolated_db.add(dup_acc)
    with pytest.raises(IntegrityError):
        isolated_db.commit()
    isolated_db.rollback()


def test_db_unique_constraint_system_log_event_id(isolated_db):
    """H3: Verify SystemLog.event_id unique constraint prevents duplicate log insertion."""
    dup_log = SystemLog(
        event_id="SEC-EVT-001",  # Already seeded
        timestamp=datetime.utcnow(),
        username="cardio_workstation",
        source_system="EMR",
        source_ip="10.0.1.20",
        device_id="DEV-WS-01",
        action="VIEW_PATIENT_CHART",
        target_type="PATIENT_CHART",
        target_id="PAT-999",
        success=True,
        raw_event_hash="hash_dup",
        processing_status="NEW"
    )
    isolated_db.add(dup_log)
    with pytest.raises(IntegrityError):
        isolated_db.commit()
    isolated_db.rollback()


def test_db_unique_constraint_privileged_action_name(isolated_db):
    """H4: Verify PrivilegedAction.action_name unique constraint."""
    dup_action = PrivilegedAction(
        action_name="VIEW_PATIENT_CHART",  # Already seeded
        sensitivity_level="CRITICAL",
        description="Duplicate action"
    )
    isolated_db.add(dup_action)
    with pytest.raises(IntegrityError):
        isolated_db.commit()
    isolated_db.rollback()


def test_db_not_null_constraint_user_fields(isolated_db):
    """H5: Verify User required fields (nullable=False) reject None values."""
    null_user = User(
        employee_id="SEC_EMP_NULL",
        full_name=None,  # Nullable=False
        role="Nurse",
        workforce_type="Permanent Staff",
        department="ICU",
        active=True
    )
    isolated_db.add(null_user)
    with pytest.raises(IntegrityError):
        isolated_db.commit()
    isolated_db.rollback()


def test_db_rollback_recovery(isolated_db):
    """H6: Verify database session rollback preserves transaction state for subsequent queries."""
    # Attempt failing operation
    null_user = User(
        employee_id="SEC_EMP_FAIL",
        full_name=None,
        role="Nurse",
        workforce_type="Permanent Staff",
        department="ICU",
        active=True
    )
    isolated_db.add(null_user)
    try:
        isolated_db.commit()
    except IntegrityError:
        isolated_db.rollback()

    # Verify session is healthy and can execute normal reads/writes
    count = isolated_db.query(User).count()
    assert count == 2  # Seeded users intact


# ---------------------------------------------------------------------------
# CATEGORY I: ERROR BOUNDARY & NON-FORCING FALLBACK VERIFICATION
# ---------------------------------------------------------------------------

def test_non_forcing_fallback_when_no_delegation(isolated_db):
    """
    I1: Core resilience invariant — when a shared account action has zero active delegations,
    the engine MUST NOT force an identity, but produce UNATTRIBUTED status (Non-Forcing Fallback).
    """
    # Event on shared account but outside any delegation window (yesterday)
    past_ts = datetime.utcnow() - timedelta(days=30)
    unauth_log = SystemLog(
        id=99,
        event_id="SEC-EVT-UNAUTH",
        timestamp=past_ts,
        username="cardio_workstation",
        session_id="SESS-PAST-01",
        source_system="EMR",
        source_ip="10.0.1.20",
        device_id="DEV-WS-01",
        action="VIEW_PATIENT_CHART",
        target_type="PATIENT_CHART",
        target_id="PAT-999",
        success=True,
        raw_event_hash="hash_unauth",
        processing_status="NEW"
    )
    isolated_db.add(unauth_log)
    isolated_db.commit()

    proto_res = PrototypeAttributionEngine.evaluate(isolated_db, unauth_log)
    assert proto_res["status"] == "UNATTRIBUTED"
    assert proto_res["user_id"] is None
    assert proto_res["confidence_level"] == "UNATTRIBUTED"


def test_unknown_user_in_direct_log_does_not_crash(isolated_db):
    """
    I2: Verify that a direct log asserting a username not in User roster
    does not throw an unhandled exception, and sets baseline to UNATTRIBUTED.
    """
    unknown_log = SystemLog(
        id=100,
        event_id="SEC-EVT-UNKNOWN-USER",
        timestamp=datetime.utcnow(),
        username="completely_unknown_user_123",
        session_id="SESS-UNK",
        source_system="EMR",
        source_ip="10.0.1.50",
        device_id="DEV-WS-UNK",
        action="VIEW_PATIENT_CHART",
        target_type="PATIENT_CHART",
        target_id="PAT-999",
        success=True,
        raw_event_hash="hash_unknown_user",
        processing_status="NEW"
    )
    isolated_db.add(unknown_log)
    isolated_db.commit()

    baseline_res = BaselineAttributionEngine.evaluate(isolated_db, unknown_log)
    assert baseline_res["status"] == "UNATTRIBUTED"
    assert baseline_res["user_id"] is None


def test_duplicate_event_processing_idempotence(isolated_db):
    """
    I3: Verify event processing idempotence — re-evaluating the same log updates existing
    record rather than creating duplicate attribution rows.
    """
    log = isolated_db.query(SystemLog).filter(SystemLog.event_id == "SEC-EVT-001").first()
    res1 = EventProcessor.run_attribution_for_log(isolated_db, log)
    isolated_db.commit()

    res2 = EventProcessor.run_attribution_for_log(isolated_db, log)
    isolated_db.commit()

    # Exactly 1 attribution result must exist for this event_id
    count = isolated_db.query(AttributionResult).filter(AttributionResult.event_id == "SEC-EVT-001").count()
    assert count == 1
    assert res1.id == res2.id
