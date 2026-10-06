# Review 3 (R3.1) Evidence Artifact: Security Hardening & API Testing

> **Project**: Hospital Shared-Account Elimination / Accountability PoC  
> **Milestone**: Review 3 — Work Package R3.1: Security Hardening + Comprehensive API Testing  
> **Evaluation Date**: 2026-10-06  
> **Target Path**: `R:\COE PROJECT`  
> **Test Framework**: `pytest` 9.1.1 / `Python` 3.11.0 (win32)  
> **Status**: **PASS (120/120 Tests Passing, 0 Regressions)**  

---

## 1. Executive Implementation Summary

Work Package R3.1 of Review 3 implements comprehensive security hardening, automated API boundary testing, and evidentiary regression verification for the Hospital Shared-Account Attribution PoC.

All existing Review 2 business logic, historical evaluation metrics, datasets, and benchmark baselines were strictly preserved:
- No database wipe, reset, or regeneration was executed.
- Core attribution algorithms (`attribution_engine.py`, `baseline.py`, `event_processor.py`) were kept untouched.
- Baseline metrics remain identical:
  - Total events: 364
  - Sensitive events: 205
  - Prototype attribution: 203 / 205 = 99.02%
  - Baseline attribution: 90 / 205 = 43.90%
  - Percentage point improvement: +55.12 pp
  - Delayed reconciliation: 15 / 15 = 100.0%
  - Escalation rate: 2 / 205 = 0.98%

---

## 2. API Endpoint Inventory Audited

Ten RESTful endpoints under `/api` were audited and tested for schema conformance, input validation, and HTTP method restrictions:

1. `GET /api/health` — Service liveness and database connection status.
2. `GET /api/users` — Staff roster retrieval with department, workforce type, and active status filters.
3. `GET /api/shared-accounts` — Workstation inventory with authorized user counts.
4. `GET /api/delegations` — Shift delegation records with user, shared account, and status filters.
5. `GET /api/privileged-actions` — Privileged clinical action catalog.
6. `GET /api/logs` — Ingested system audit logs with pagination (`limit <= 500`, `offset >= 0`) and sensitivity filters.
7. `GET /api/attribution/results` — Historical attribution results with pagination and status filters.
8. `GET /api/attribution/metrics` — Aggregate attribution comparison metrics.
9. `GET /api/attribution/{event_id}` — Granular evidentiary dossier for a specific clinical action.
10. `POST /api/process-events` — Batch attribution pipeline trigger.

---

## 3. Security Controls Verified

| Security Dimension | Implementation Mechanism | Verification Result |
|:---|:---|:---:|
| **SQL Injection Prevention** | All ORM queries utilize SQLAlchemy parameterized prepared statements (`?` bindings). | **PASS** — Verified against payloads: `' OR '1'='1`, `'; DROP TABLE users; --`, `' UNION SELECT ... --`. No tables altered, no SQL syntax errors. |
| **Input Validation** | FastAPI Query parameter constraints (`le=500`, `ge=0`) and Pydantic datatype coercion. | **PASS** — Verified against out-of-range pagination, negative offsets, and type-mismatched parameters (all return HTTP 422). |
| **HTTP Verb Tampering** | Strict method bindings on FastAPI router with custom fallback handling. | **PASS** — Verified: GET-only routes reject `POST`, `PUT`, `DELETE`, `PATCH` with HTTP 405; POST-only route rejects `GET`, `PUT`, `DELETE` with HTTP 405. |
| **Information Leakage Prevention** | Error boundaries return structured JSON (`{"detail": ...}`) without tracebacks. | **PASS** — Verified: Error responses contain no Python tracebacks, stack traces, local disk paths, or database URLs. |
| **XSS & Traversal Resilience** | Script tags and directory traversal strings treated as inert literal values. | **PASS** — Verified: `<script>alert(1)</script>`, `../../etc/passwd`, and encoded traversal sequences handled safely without file disclosure or execution. |
| **Database Integrity Constraints** | SQLAlchemy schema constraints (unique indexes, not-null constraints, and foreign keys). | **PASS** — Verified: Duplicate employee IDs, usernames, action names, and event IDs raise `IntegrityError`; session rollback preserves transaction state. |
| **Non-Forcing Fallback** | Clinical evidence evaluation refuses to guess when data is missing or ambiguous. | **PASS** — Actions outside delegation windows produce `UNATTRIBUTED`; unknown users trigger safe escalation without database corruption. |

---

## 4. Defect Discovered & Remediated

During API testing of method security and error containment, a subtle routing bug was identified and resolved:
- **Defect Description**: The SPA catch-all route `@app.get("/{full_path:path}")` in `backend/app/main.py` returned `None` (HTTP 200 with `null` body) when requests targeted unmatched `/api` paths or when a client sent a `GET` request to `POST /api/process-events`.
- **Root Cause**: The route handler contained `if full_path.startswith("api"): return None` intended to prevent frontend interception of API routes, but in FastAPI returning `None` serializes as HTTP 200 with JSON `null`.
- **Safe Remediation**: Modified `backend/app/main.py` so that unmatched paths starting with `api/` check `api_router.routes`; if the endpoint exists under a different HTTP method, it raises `HTTPException(status_code=405, detail="Method Not Allowed")`, otherwise raising `HTTPException(status_code=404, detail="Resource not found")`.
- **Regression Impact**: Zero negative side effects. All 39 baseline tests and 81 security tests now pass cleanly.

---

## 5. Automated Test Suite Execution Summary

```text
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-9.1.1, pluggy-1.6.0
rootdir: R:\COE PROJECT
plugins: anyio-4.15.1
collected 120 items

tests\test_alerts.py ..                                                  [  1%]
tests\test_api_security.py ............................................. [ 39%]
....................................                                     [ 69%]
tests\test_attribution.py ...........                                    [ 78%]
tests\test_audit_chain.py ....                                           [ 81%]
tests\test_delegation_lifecycle.py ....                                  [ 85%]
tests\test_escalation.py ....                                            [ 88%]
tests\test_ingestion_buffer.py ....                                      [ 91%]
tests\test_session_lifecycle.py .....                                    [ 95%]
tests\test_telemetry_degradation.py .....                                [100%]

======================= 120 passed, 2 warnings in 5.17s =======================
```

### Test Count Breakdown
- **Pre-existing Review 2 Tests**: 39 passed / 39 total (100%)
- **New Review 3 Security Tests (`tests/test_api_security.py`)**: 81 passed / 81 total (100%)
- **Total Suite Passing**: 120 / 120 (100%)
- **Total Test Failures**: 0
- **Execution Runtime**: 5.17 seconds

---

## 6. Authentication & RBAC Boundary Audit

1. **Authentication Reality**:
   - The backend API does not enforce token-based authentication (OAuth2, JWT, or API keys).
   - This architectural decision is documented as an academic PoC characteristic for automated evaluation harnesses.
2. **Authorization Reality**:
   - The Streamlit dashboard role selector (`dashboard/app.py`) provides an illustrative persona lens ("Compliance Officer", "Auditor", "Student") for demo purposes only.
   - It is not an API-level security perimeter.
3. **Delegation Clarification**:
   - The `SharedAccountAuthorization` database model represents clinical shift authorizations (clinical delegations), not HTTP access permissions.

---

## 7. Known Limitations & Academic PoC Disclosures

- **Non-Production Storage**: The prototype utilizes SQLite in single-writer mode without hardware security module (HSM) key storage or encrypted tablespaces.
- **Transport Security**: Evaluated in local test environments over HTTP; production deployment requires TLS 1.3 and mutual TLS (mTLS) for terminal authentication.
- **No Regulatory Certifications Claimed**: The project is an academic proof of concept and has not undergone HIPAA Security Rule certification, FDA Premarket Cybersecurity evaluation, or independent third-party penetration testing.

---

## 8. Evidence File References

- Test Suite: [`tests/test_api_security.py`](file:///r:/COE%20PROJECT/tests/test_api_security.py)
- Security Documentation: [`docs/security_testing.md`](file:///r:/COE%20PROJECT/docs/security_testing.md)
- Routing Implementation: [`backend/app/main.py`](file:///r:/COE%20PROJECT/backend/app/main.py)
- API Routes: [`backend/app/api/routes.py`](file:///r:/COE%20PROJECT/backend/app/api/routes.py)
- Verified Metrics: [`results/metrics.csv`](file:///r:/COE%20PROJECT/results/metrics.csv)
- Acceptance Gate: [`results/review3_acceptance_gate.md`](file:///r:/COE%20PROJECT/results/review3_acceptance_gate.md)
