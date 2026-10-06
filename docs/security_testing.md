# API Security, Hardening & Boundary Testing Specification

> **Project**: Hospital Shared-Account Elimination & Accountable Action Attribution PoC  
> **Milestone**: Review 3 — Work Package R3.1: Security Hardening + Comprehensive API Testing  
> **Status**: Verified & Passing (81 Security Tests / 120 Total Tests)  
> **Scope**: Defensive API Security, Input Sanitization, Database Constraints, Error Containment, and Regressive Baseline Preservation  

---

## 1. Scope & Security Posture

This document establishes the security architecture audit, defensive test methodology, and verified empirical results for the Hospital Shared-Account Attribution Service API (`backend/app/api/routes.py`). 

As an academic Proof of Concept (PoC) designed for research evaluation and operational demonstration, the service operates with explicit boundaries:
- **Core Security Objective**: Guarantee that API request processing preserves audit record integrity, parameterizes inputs to prevent SQL injection, rejects unsupported HTTP methods with standard 405 status codes, bounds error disclosures to prevent information leakage, and maintains the Non-Forcing Fallback Principle across all attribution workflows.
- **Out of Scope / Non-Production Disclaimer**: This PoC does **not** implement enterprise OAuth2/OIDC token verification, SAML v2 single sign-on, hospital Active Directory integration, or production transport-layer mTLS. It is **not** certified under HIPAA Security Rule (45 CFR § 164.312), FDA 510(k) cybersecurity guidance, or independent penetration-testing standards.

---

## 2. API Inventory & Boundary Specification

The system exposes ten RESTful endpoints under the `/api` prefix, serving compliance dashboards, ingestion buffers, and forensic review workflows. Each endpoint has been audited directly against source code:

| # | Method | Path | Purpose | Parameters / Payload | Response Schema | Auth / RBAC Status |
|---|:---|:---|:---|:---|:---|:---|
| **1** | `GET` | `/api/health` | Service and database liveness verification | None | JSON status (`HEALTHY`, `CONNECTED`, counts) | Unauthenticated (Public healthcheck) |
| **2** | `GET` | `/api/users` | Clinical workforce roster retrieval | `department` (str), `workforce_type` (str), `active` (bool) | `List[UserResponse]` | Unauthenticated |
| **3** | `GET` | `/api/shared-accounts` | Departmental shared terminal inventory | None | `List[SharedAccountResponse]` | Unauthenticated |
| **4** | `GET` | `/api/delegations` | Clinical shift delegation authorizations | `shared_account_id` (int), `user_id` (int), `status` (str) | `List[AuthorizationResponse]` | Unauthenticated |
| **5** | `GET` | `/api/privileged-actions` | High-risk clinical action catalog | None | `List[PrivilegedActionResponse]` | Unauthenticated |
| **6** | `GET` | `/api/logs` | Ingested workstation event logs | `username` (str), `action` (str), `is_sensitive` (bool), `status` (str), `limit` (int $\le 500$), `offset` (int $\ge 0$) | `List[SystemLogResponse]` | Unauthenticated (Pagination bounds enforced) |
| **7** | `GET` | `/api/attribution/results` | Historical action attribution outcomes | `status` (str), `method` (str), `confidence_level` (str), `limit` (int $\le 500$), `offset` (int $\ge 0$) | `List[AttributionResultResponse]` | Unauthenticated (Pagination bounds enforced) |
| **8** | `GET` | `/api/attribution/metrics` | Comparative baseline vs prototype metrics | None | `MetricsBreakdown` | Unauthenticated |
| **9** | `GET` | `/api/attribution/{event_id}` | Full evidentiary dossier for single action | `event_id` (str path param) | `EventDetailResponse` | Unauthenticated (404 on missing event) |
| **10** | `POST` | `/api/process-events` | Attribution pipeline batch trigger | None (No body required) | Status JSON (`processed_count`, metrics) | Unauthenticated (POST-only; 405 on GET) |

---

## 3. Security Test Methodology

Defensive security testing was executed using automated test suites built on `pytest` and `fastapi.testclient.TestClient`. Tests are segregated into nine functional verification categories:

1. **Category A — Health & Availability**: Validates service connectivity, database responsiveness, and non-disclosure of internal server metadata.
2. **Category B — Valid Request Coverage**: Exercises all ten endpoints with legitimate parameters, validating Pydantic response contract conformance.
3. **Category C — Invalid Input & Schema Validation**: Injects type-mismatched parameters, boundary-violating query limits ($> 500$), negative offsets, and malformed structures to verify that FastAPI/Pydantic returns HTTP 422 Unprocessable Entity.
4. **Category D — Resource Not Found & Leakage Prevention**: Injects nonexistent resource identifiers and undefined routes, confirming HTTP 404 responses without Python tracebacks, file paths, or internal connection strings.
5. **Category E — HTTP Method Security (Verb Tampering)**: Submits disallowed HTTP verbs (e.g., `POST`, `PUT`, `DELETE` to GET-only routes, and `GET` to the POST-only batch pipeline), asserting standard HTTP 405 Method Not Allowed responses.
6. **Category F — Authentication & Authorization Boundary**: Empirically audits the authentication boundary, confirming that missing or dummy tokens do not crash the service, and verifies that dashboard personas are purely presentation concepts.
7. **Category G — Input Validation & Injection Resilience**: Injects SQL injection vectors (`' OR '1'='1`, `'; DROP TABLE users; --`), XSS tags (`<script>`, `<admin>`), path traversal patterns (`../../etc/passwd`), buffer-stress strings (10,000 characters), multibyte Unicode, and whitespace anomalies.
8. **Category H — Database Security & Integrity**: Exercises SQLAlchemy ORM schema constraints in an isolated database environment, validating unique index enforcement, not-null constraints, and transaction rollback recovery.
9. **Category I — Error Boundaries & Non-Forcing Fallback**: Validates that unmapped accounts, missing delegations, and ambiguous signals result in controlled `UNATTRIBUTED` or `AMBIGUOUS` states without algorithmic hallucination or crash.

---

## 4. Authentication Findings

### Source Code Audit
- **Backend Implementation**: `backend/app/main.py` and `backend/app/api/routes.py` contain **no HTTP authentication middleware**, OAuth2 dependencies, session cookie validators, or API key parsers.
- **Nomenclature Clarification**: The database entity `SharedAccountAuthorization` models **clinical shift delegations** (i.e. authorizing Dr. Smith to use `radiology_shared` between 08:00 and 16:00), not HTTP API client authorization.
- **Empirical Test Verification**: Requests lacking `Authorization` headers succeed normally across all read endpoints (`test_auth_boundary_unauthenticated_requests_succeed`). Supplying arbitrary Bearer tokens (`Authorization: Bearer mock.token`) does not alter endpoint execution or cause exceptions (`test_auth_boundary_arbitrary_bearer_token_ignored`).

### Hardening Recommendation for Future Milestones
- For production transition, implement FastAPI `OAuth2PasswordBearer` with JWT cryptographic validation (RS256) linked to a healthcare Identity Provider (IdP) supporting SMART-on-FHIR or OpenID Connect.

---

## 5. Authorization & RBAC Findings

### Source Code Audit
- **Dashboard Persona vs API RBAC**: The Streamlit compliance console (`dashboard/app.py`, lines 89-100) incorporates a sidebar persona selector ("Compliance Officer", "Security Analyst", "Auditor", "Supervisor", "Student / Reviewer"). The source code explicitly documents this as an illustrative UI inspection persona and **not** API-enforced RBAC.
- **API Role Enforcement**: The API endpoints do not inspect `X-User-Role` headers or JWT role claims. User records contain hospital job roles (`User.role` such as "Consultant" or "Radiologist"), but these govern clinical workflow attribution scoring rather than API access privileges.
- **Empirical Test Verification**: Submitting requests with varied `X-User-Role` headers produces uniform 200 OK responses (`test_auth_boundary_demo_roles_not_enforced_at_api_level`).

### Hardening Recommendation for Future Milestones
- Introduce role-based dependency guards (`Depends(require_role(["Auditor", "Compliance_Officer"]))`) to restrict privileged endpoints (such as `POST /api/process-events` or audit chain verification).

---

## 6. Input Validation & Injection Resilience Findings

### SQL Injection Resilience
- **Mechanism**: All database queries in `routes.py`, `baseline.py`, and `attribution.py` are constructed exclusively via the SQLAlchemy ORM (`db.query(Model).filter(...)`), which automatically employs parameterized SQL statements (`?` parameters in SQLite).
- **Test Findings**: Payloads including `' OR '1'='1`, `'; DROP TABLE users; --`, `' UNION SELECT ... --`, and `" OR ""="` injected into `department`, `username`, and `event_id` parameters were safely escaped. No database tables were dropped, no unearned records were leaked, and the database schema remained intact (`test_sql_injection_resilience_query_params`, `test_sql_injection_resilience_path_param`).

### Cross-Site Scripting (XSS) & Tag Injection
- **Mechanism**: Path and query parameters containing HTML/JavaScript tags (`<script>alert(1)</script>`, `<img src=x onerror=alert('xss')>`, `<admin>`) are handled as inert literal strings. Response payloads serialize these values as escaped JSON, preventing reflected script execution.
- **Test Findings**: Injection into query parameters yielded standard filtered JSON lists; injection into path parameters yielded controlled 404 responses with JSON error bodies (`test_xss_html_injection_resilience_query_params`, `test_xss_html_injection_resilience_path_param`).

### Path Traversal & Long Input Resilience
- **Path Traversal**: Relative traversal sequences (`../../etc/passwd`, `/etc/shadow`, URL-encoded `%2E%2E%2F`) were evaluated. Path traversal strings passed as path parameters returned 404 or 422; query parameters returned empty lists without accessing local host files.
- **Length & Unicode Stress**: Submitting a 10,000-character department string was handled cleanly without memory exhaustion or server crash (`test_extraordinarily_long_input_string`). Multibyte Unicode (Arabic, Chinese, Russian) and emoji strings (`🏥🏨💉🧪⚕️`) were handled cleanly via UTF-8 encoding (`test_unicode_and_multilingual_resilience`).

---

## 7. Database Security & Integrity Findings

The backend utilizes SQLite (`data/hospital_attribution.db`) as its local embedded data store, managed through six SQLAlchemy models:

1. **`users`**: Unique constraint on `employee_id`; non-nullable constraints on `full_name`, `role`, `department`, `workforce_type`. Duplicate employee insertions correctly raise `IntegrityError` (`test_db_unique_constraint_employee_id`).
2. **`shared_accounts`**: Unique constraint on `username`; non-nullable constraints on `system_name`, `department`, `account_type`. Duplicate account creation raises `IntegrityError` (`test_db_unique_constraint_shared_account_username`).
3. **`shared_account_authorization`**: Foreign keys to `shared_accounts.id` and `users.id`; non-nullable start/end shift bounds.
4. **`privileged_actions`**: Unique constraint on `action_name`; non-nullable `sensitivity_level`. Duplicate action catalog entry raises `IntegrityError` (`test_db_unique_constraint_privileged_action_name`).
5. **`system_logs`**: Unique constraint on `event_id`; non-nullable fields for audit immutability (`raw_event_hash`, `timestamp`, `username`, `action`). Duplicate event insertions raise `IntegrityError` (`test_db_unique_constraint_system_log_event_id`).
6. **`attribution_results`**: Foreign keys to `system_logs.event_id` and `users.id`; idempotently updated per event.
7. **Session Rollback**: Integrity violation tests confirmed that calling `session.rollback()` clears pending errors and restores the session for subsequent valid operations without transaction corruption (`test_db_rollback_recovery`).

*Academic PoC Note*: SQLite is utilized solely for reproducible offline demonstration and evaluation. A production hospital deployment would require an enterprise ACID relational engine (e.g., PostgreSQL) configured with row-level security, encrypted tablespaces, and pgAudit logging.

---

## 8. Error Boundary & Non-Forcing Fallback Findings

As mandated by `docs/error_handling.md`, error containment operates under the **Non-Forcing Fallback Principle**:

1. **Information Leakage Prevention**: In both 404 (Resource Not Found) and 422 (Unprocessable Entity) conditions, the API returns structured JSON error bodies (`{"detail": ...}`). Responses were verified to contain **no Python tracebacks** (`Traceback (most recent call last)`), no source code file paths, and no database connection URIs (`test_error_response_no_traceback_leakage`).
2. **Defensive Fix Applied**: An audit of `backend/app/main.py` identified that the catch-all SPA route `serve_frontend` returned `None` (HTTP 200 with `null` body) for unmatched `/api` paths. This was remediated with a minimal defensive patch that enforces HTTP 404 for nonexistent API routes and HTTP 405 for method-mismatched API routes.
3. **Non-Forcing Fallback Preservation**:
   - When a shared account action occurs outside any authorized delegation window, the engine returns `status="UNATTRIBUTED"`, `confidence_level="UNATTRIBUTED"`, and `user_id=None` (`test_non_forcing_fallback_when_no_delegation`).
   - When a log asserts an unknown username not present in the staff roster, the engine handles the record gracefully without crashing, classifying it as `UNATTRIBUTED` (`test_unknown_user_in_direct_log_does_not_crash`).
   - Event processing re-evaluation is strictly idempotent; re-processing an existing log updates the existing attribution record rather than creating duplicate database rows (`test_duplicate_event_processing_idempotence`).

---

## 9. Security Regression Findings

The entire test suite was executed to guarantee that security additions did not perturb existing Review 2 functionality:

- **Baseline Tests**: 39 / 39 passed (100% preservation)
- **New Review 3 Security Tests**: 81 / 81 passed (100% passing)
- **Total Suite**: 120 / 120 passed in 5.17 seconds
- **Attribution Invariants Verified**:
  - Staff: 18
  - Shared Accounts: 6
  - Delegations: 26
  - Privileged Actions: 10
  - Total Events: 364
  - Sensitive Events: 205
  - Baseline Attribution: 90 / 205 = 43.90%
  - Prototype Attribution: 203 / 205 = 99.02%
  - Percentage Point Improvement: +55.12 pp
  - Delayed Event Reconciliation: 15 / 15 = 100.0%
  - Escalation Rate: 2 / 205 = 0.98%

---

## 10. Comprehensive Test Matrix

The following matrix documents the full set of automated security tests implemented in `tests/test_api_security.py`:

| Test ID | Category | Endpoint / Module | Input / Scenario | Expected Behavior | Actual Behavior | Status |
|:---|:---|:---|:---|:---|:---|:---:|
| **SEC-A01** | Health | `GET /api/health` | Valid request | HTTP 200, status HEALTHY, db CONNECTED | HTTP 200, status HEALTHY, db CONNECTED | PASS |
| **SEC-A02** | Health | `GET /api/health` | Header inspection | Content-Type application/json | application/json | PASS |
| **SEC-B01** | Valid Request | `GET /api/users` | Valid request | HTTP 200, list of users with full schema | HTTP 200, 18 users returned | PASS |
| **SEC-B02** | Valid Request | `GET /api/users` | `department=Radiology` | HTTP 200, filtered users list | HTTP 200, only Radiology staff returned | PASS |
| **SEC-B03** | Valid Request | `GET /api/shared-accounts` | Valid request | HTTP 200, 6 shared accounts with counts | HTTP 200, 6 accounts returned | PASS |
| **SEC-B04** | Valid Request | `GET /api/delegations` | Valid request | HTTP 200, 26 delegations with schema | HTTP 200, 26 delegations returned | PASS |
| **SEC-B05** | Valid Request | `GET /api/delegations` | `status=ACTIVE` | HTTP 200, only active delegations | HTTP 200, active records returned | PASS |
| **SEC-B06** | Valid Request | `GET /api/privileged-actions`| Valid request | HTTP 200, 10 privileged action types | HTTP 200, 10 actions returned | PASS |
| **SEC-B07** | Valid Request | `GET /api/logs` | `limit=5, offset=0` | HTTP 200, exactly 5 log records | HTTP 200, 5 logs returned | PASS |
| **SEC-B08** | Valid Request | `GET /api/logs` | `is_sensitive=True` | HTTP 200, only sensitive logs | HTTP 200, sensitive logs returned | PASS |
| **SEC-B09** | Valid Request | `GET /api/attribution/results` | `limit=5` | HTTP 200, attribution outcome records | HTTP 200, 5 results returned | PASS |
| **SEC-B10** | Valid Request | `GET /api/attribution/metrics` | Valid request | HTTP 200, full metrics breakdown | HTTP 200, 99.02% vs 43.90% metrics | PASS |
| **SEC-B11** | Valid Request | `GET /api/attribution/EVT-00001` | Valid `event_id` | HTTP 200, complete dossier with checklist | HTTP 200, complete dossier returned | PASS |
| **SEC-B12** | Valid Request | `POST /api/process-events` | Valid trigger (isolated) | HTTP 200, status SUCCESS, count $\ge 0$ | HTTP 200, processed without error | PASS |
| **SEC-C01** | Invalid Input | `GET /api/users` | `active=invalid_bool` | HTTP 422 Unprocessable Entity | HTTP 422 with validation error | PASS |
| **SEC-C02** | Invalid Input | `GET /api/delegations` | `user_id=not_an_int` | HTTP 422 Unprocessable Entity | HTTP 422 with validation error | PASS |
| **SEC-C03** | Invalid Input | `GET /api/delegations` | `shared_account_id=alpha` | HTTP 422 Unprocessable Entity | HTTP 422 with validation error | PASS |
| **SEC-C04** | Invalid Input | `GET /api/logs` | `limit=99999` (le=500 bound)| HTTP 422 Unprocessable Entity | HTTP 422, limit validation triggered | PASS |
| **SEC-C05** | Invalid Input | `GET /api/logs` | `offset=-10` (ge=0 bound) | HTTP 422 Unprocessable Entity | HTTP 422, offset validation triggered | PASS |
| **SEC-C06** | Invalid Input | `GET /api/logs` | `is_sensitive=perhaps` | HTTP 422 Unprocessable Entity | HTTP 422 with validation error | PASS |
| **SEC-C07** | Invalid Input | `GET /api/attribution/results` | `limit=501` (le=500 bound) | HTTP 422 Unprocessable Entity | HTTP 422, limit bound enforced | PASS |
| **SEC-C08** | Invalid Input | `GET /api/attribution/results` | `offset=-1` (ge=0 bound) | HTTP 422 Unprocessable Entity | HTTP 422, offset bound enforced | PASS |
| **SEC-D01** | Resource Error| `GET /api/attribution/{id}` | `NON_EXISTENT_EVT_99999` | HTTP 404 with clean JSON error | HTTP 404, event not found detail | PASS |
| **SEC-D02** | Resource Error| `GET /api/nonexistent_path` | Undefined route | HTTP 404 Resource not found | HTTP 404 Resource not found | PASS |
| **SEC-D03** | Resource Error| `GET /api/users` | Nonexistent department | HTTP 200 with empty list `[]` | HTTP 200 with empty list `[]` | PASS |
| **SEC-D04** | Resource Error| `GET /api/delegations` | Nonexistent `user_id=999999` | HTTP 200 with empty list `[]` | HTTP 200 with empty list `[]` | PASS |
| **SEC-D05** | Leakage Audit | Error responses | 404 and 422 triggers | No Python traceback, no paths/secrets | Clean JSON response verified | PASS |
| **SEC-E01** | Method Sec | `POST/PUT/DELETE /api/health` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E02** | Method Sec | `POST/PUT/DELETE /api/users` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E03** | Method Sec | `POST/PUT/DEL /api/shared-acc` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E04** | Method Sec | `POST/PUT/DEL /api/delegations`| Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E05** | Method Sec | `POST/PUT/DEL /api/priv-act` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E06** | Method Sec | `POST/PUT/DELETE /api/logs` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E07** | Method Sec | `POST/PUT/DEL /api/attr/metrics`| Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E08** | Method Sec | `POST/PUT/DEL /api/attr/results`| Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E09** | Method Sec | `POST/PUT/DEL /api/attr/{id}` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-E10** | Method Sec | `GET/PUT/DEL /api/proc-events` | Disallowed verbs | HTTP 405 Method Not Allowed | HTTP 405 across all disallowed verbs | PASS |
| **SEC-F01** | Auth Audit | All read endpoints | Request with no auth header | Allowed (Academic PoC behavior) | HTTP 200 OK across read routes | PASS |
| **SEC-F02** | Auth Audit | `GET /api/health` | Dummy Bearer token header | Ignored gracefully without exception | HTTP 200 OK | PASS |
| **SEC-F03** | RBAC Audit | `GET /api/users` | Varied `X-User-Role` headers | Not enforced at API (demo personas) | HTTP 200 OK | PASS |
| **SEC-G01** | Injection | Query params | SQLi (`' OR '1'='1`, DROP TABLE) | Safe parameterization; no SQL exec | HTTP 200, tables intact | PASS |
| **SEC-G02** | Injection | Path param `event_id` | SQLi (`' OR '1'='1`, UNION SELECT) | Safe parameterization; returns 404 | HTTP 404, query safely parameterized | PASS |
| **SEC-G03** | Injection | Query params | XSS (`<script>`, `<img>`, `<admin>`) | Inert string treatment; no reflection | HTTP 200, safely escaped | PASS |
| **SEC-G04** | Injection | Path param `event_id` | XSS / tag injections | Inert string treatment; returns 404 | HTTP 404 clean JSON | PASS |
| **SEC-G05** | Injection | Query params | Traversal (`../../etc/passwd`) | Treated as literal string | HTTP 200, empty list `[]` | PASS |
| **SEC-G06** | Injection | Path param `event_id` | Encoded traversal (`%2E%2E%2F`) | Returns 404 without file access | HTTP 404 clean JSON | PASS |
| **SEC-G07** | Buffer Stress | `department` param | 10,000 character string | Handled without server crash | HTTP 200, empty list `[]` | PASS |
| **SEC-G08** | Encoding | `department` param | UTF-8 emoji and multilingual | Parsed cleanly without error | HTTP 200, clean response | PASS |
| **SEC-G09** | Whitespace | `department` param | Leading/trailing whitespace | Handled without error | HTTP 200, clean response | PASS |
| **SEC-H01** | DB Integrity | `User.employee_id` | Duplicate employee ID | `IntegrityError` raised | `IntegrityError` raised and rolled back | PASS |
| **SEC-H02** | DB Integrity | `SharedAccount.username` | Duplicate account username | `IntegrityError` raised | `IntegrityError` raised and rolled back | PASS |
| **SEC-H03** | DB Integrity | `SystemLog.event_id` | Duplicate event ID | `IntegrityError` raised | `IntegrityError` raised and rolled back | PASS |
| **SEC-H04** | DB Integrity | `PrivilegedAction.action_name`| Duplicate action name | `IntegrityError` raised | `IntegrityError` raised and rolled back | PASS |
| **SEC-H05** | DB Integrity | `User` required fields | `full_name=None` | `IntegrityError` raised | `IntegrityError` raised and rolled back | PASS |
| **SEC-H06** | DB Integrity | Session management | Rollback after integrity fault | Clean session restored | Verified healthy session reuse | PASS |
| **SEC-I01** | Fallback | `PrototypeAttributionEngine`| Event outside delegation window | Status UNATTRIBUTED (Non-Forcing) | Status UNATTRIBUTED, user_id=None | PASS |
| **SEC-I02** | Fallback | `BaselineAttributionEngine` | Unknown user not on staff roster | Graceful handling; UNATTRIBUTED | Status UNATTRIBUTED, user_id=None | PASS |
| **SEC-I03** | Fallback | `EventProcessor` | Duplicate event re-processing | Idempotent update; no duplicate rows | Exactly 1 attribution result record | PASS |

---

## 11. Known Limitations & Academic PoC Disclaimer

1. **Authentication & Transport Layer**: The API runs over plain HTTP without TLS termination, mTLS client certificates, or token-based authentication. In a real hospital environment, TLS 1.3 encryption and mutual certificate authentication are required.
2. **Local Embedded SQLite**: The persistence tier uses SQLite in single-writer mode. It lacks database user privilege separation, encrypted table storage, and audit log write-once-read-many (WORM) hardware storage.
3. **No Enterprise EHR Integration**: Telemetry logs are simulated synthetic clinical scenarios (`data/system_logs.csv`), not live HL7/FHIR feeds from commercial EHR vendors (Epic Systems, Cerner/Oracle Health).
4. **Academic PoC Status**: This software is an experimental academic prototype created to evaluate clinical multi-signal action attribution. It is **not** certified under HIPAA, HITECH, FDA SaMD, or ISO 27001 standards.
