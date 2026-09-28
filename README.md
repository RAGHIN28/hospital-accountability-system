# Hospital Shared-Account Elimination & Accountable Action Attribution

> **Milestone Status**: Project Review #2 (70% Completion Milestone) — **PASSED (91.15% Requirement Coverage)**  
> **Attribution Accuracy**: **99.02%** on sensitive clinical actions (Baseline: **43.90%**, Net Lift: **+55.12%**)  
> **Automated Test Suite**: **39 / 39 Passing (100.00% Pass Rate in 2.06s)**  
> **Environment**: Academic Cybersecurity Proof-of-Concept (Local Python 3.11 / Streamlit / SQLite / 100% Synthetic Data)

---

## ⚠️ Essential Separation of Metrics

To ensure strict academic and evaluative rigor, this project explicitly decouples five distinct metrics:
1. **Project Requirement Coverage**: **91.15%** (Evaluated from 25 requirements across 7 categories in `results/project_completion_matrix.csv`; Milestone Gate: $\ge 70.00\%$).
2. **Sensitive-Action Attribution Accuracy**: **99.02%** (203 / 205 sensitive clinical actions resolved to individual identities).
3. **Automated Test Suite Pass Rate**: **100.00%** (39 / 39 tests passing with zero regressions).
4. **Ingestion Peak Throughput**: **17,737 events/second** (Measured at 50,000 synthetic event scale).
5. **Data Quality & Resilience**: **100.00%** reconciliation rate for delayed shift authorizations; graceful degradation down to 0% telemetry (36.10% attribution maintained solely on strong direct tokens/delegations; 131 actions safely escalated to human review).

---

## 🌐 Quick Links & Local Services

The full-stack application and interactive compliance review console run locally on Windows / Unix:

- **Streamlit Compliance Review Console**: [http://localhost:8501](http://localhost:8501) (17 compliance views & audit tools)
- **FastAPI Backend Server**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive Swagger REST API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Attribution Metrics Endpoint**: [http://127.0.0.1:8000/api/attribution/metrics](http://127.0.0.1:8000/api/attribution/metrics)
- **Health Check Endpoint**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## 1. Problem Statement

Hospital environments frequently deploy shared departmental accounts on clinical workstations to facilitate rapid handoffs:
- `radiology_shared` (PACS / RIS)
- `er_triage_shared` (Emergency Department Intake)
- `icu_shared_ws` (Intensive Care Unit)
- `pharmacy_dispenser` (Automated Drug Dispensing)
- `lab_shared_ws` (Laboratory Information Systems)
- `oncology_shared` (Chemotherapy & Infusion)

When sensitive clinical actions occur (e.g., dispensing narcotics, altering medication orders, overriding dosage alerts, exporting patient EHR records), standard audit logs record only the generic shared account name. This creates an unacceptable accountability void.

Naive attribution methods (such as assigning actions to whoever was on shift) fail whenever multiple clinicians are active, achieving only **43.90%** attribution accuracy.

This project delivers an **Accountable Shift Delegation & Session Attribution Pipeline** that correlates multi-source telemetry, session bindings, and temporal authorization lifecycles to attribute sensitive actions to individual human identities with calibrated, explainable evidence dossiers.

---

## 2. Review #1 Evaluator Remediation Matrix

Review #1 identified three technical gaps. All three have been implemented, tested, and verified:

| Feedback ID | Evaluator Concern | Remediation Component | Test Suite | Measured Evidence | Status |
|---|---|---|---|---|---|
| **REV1-GAP-A** | Delayed & Out-of-Order Ingestion Buffer | `IngestionBuffer` priority queue & retroactive reconciliation (`src/ingestion_buffer.py`) | `tests/test_ingestion_buffer.py` | 100% reconciliation rate of delayed shifts; 15,766 events/s throughput | **VERIFIED** |
| **REV1-GAP-B** | Telemetry Stress Testing & Degradation Curves | `TelemetryStressEngine` degradation harness (`src/telemetry_stress.py`) | `tests/test_telemetry_degradation.py` | Evaluated 100% to 0% telemetry availability; zero false identities | **VERIFIED** |
| **REV1-GAP-C** | Human-in-the-Loop Escalation & Error Analysis | `EscalationService` & compliance review queue (`src/escalation_service.py`) | `tests/test_escalation.py` | 0.98% escalation rate; 13-category error taxonomy | **VERIFIED** |

*Full traceability matrix available at `results/review1_remediation_matrix.csv`.*

---

## 3. Technical Architecture

### Architectural Pipeline Flow

```
Input Events (EHR, PACS, Dispenser, Lab, Auth)
       │
       ▼
[ Normalization ] ──► 17-field canonical schema, raw hash preservation
       │
       ▼
[ Multi-Source Ingestion ] ──► 5 disparate log streams correlated
       │
       ▼
[ Duplicate Detection ] ──► SHA-256 event fingerprint hash deduplication
       │
       ▼
[ Event-Time Ordering & Buffering ] ──► Priority queue with configurable watermark
       │
       ▼
[ Delegation & Session Correlation ] ──► Lifecycle states & causal validity checks
       │
       ▼
[ Evidence Scoring ] ──► 5-tier signal weights: 40 / 30 / 15 / 10 / 5 (Max 100 pts)
       │
       ▼
[ Attribution Engine ] ──► Individual identity resolution with calibrated dossiers
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
[ High-Confidence Attributed ]    [ Ambiguous / Conflicted / Unlisted ]
  (203 sensitive actions)                │
                                         ▼
                                  [ Human Escalation Service ] ──► Compliance Review
                                         │
                                         ▼
                                  [ Tamper-Evident Audit Chain ] ──► SHA-256 Linked Blocks
                                         │
                                         ▼
                                  [ Compliance Dashboard & REST API ] ──► Streamlit (Port 8501) & FastAPI (Port 8000)
```

### Core Components

| Module File | Component Name | System Responsibility |
|---|---|---|
| `src/attribution_engine.py` | `AttributionEngine` | Multi-source evidence aggregation, scoring, confidence tiering, and non-forcing escalation fallback. |
| `src/ingestion_buffer.py` | `IngestionBuffer` | Event-time vs. arrival-time priority queue, deduplication index, and retroactive late-arriving authorization reconciliation. |
| `src/delegation_lifecycle.py` | `DelegationManager` | Temporal state machine (`CREATED` -> `ACTIVE` -> `EXPIRED`/`REVOKED`) with immutable history and boundary validation. |
| `src/session_lifecycle.py` | `SessionManager` | Workstation session state machine (`CREATED` -> `ACTIVE` -> `IDLE` -> `TERMINATED`/`EXPIRED`), tracking idle timeouts and active users. |
| `src/evidence_model.py` | `EvidenceDossier` | Calibrated 5-tier evidentiary model (Explicit, Temporal, Telemetry, Contextual, Negative) preserving full rationale. |
| `src/multi_source_ingestion.py` | `MultiSourceIngestor` | Ingestion and temporal collation across EHR, authentication, workstation session, badge/RFID, and network telemetry streams. |
| `src/normalization.py` | `EventNormalizer` | Schema unification into 17-field canonical model with forensic raw-payload SHA-256 hashing. |
| `src/audit_chain.py` | `TamperEvidentAuditChain` | SHA-256 cryptographically linked blocks for non-repudiation and tamper detection. |
| `src/escalation.py` | `EscalationService` | Human-in-the-loop compliance review queue for ambiguous, conflicting, or unlisted-user events. |
| `src/telemetry_stress.py` | `TelemetryStressEngine` | Stress harness simulating telemetry degradation (100% to 0%) and network context corruption. |
| `src/alerts.py` | `OperationalAlertManager` | SOC alert generation, key-based deduplication to prevent alarm fatigue, and analyst lifecycle tracking. |
| `backend/app/main.py` & `backend/app/api/routes.py` | FastAPI Application | RESTful API service exposing database queries, pipeline execution, and forensic audit endpoints. |
| `dashboard/app.py` | Streamlit Compliance Console | Multi-view compliance officer and reviewer interface featuring 17 audit sections and role perspectives. |

---

## 4. API / Application Interfaces

The proof-of-concept exposes three tiers of interfaces: a RESTful FastAPI service for programmatic queries and event processing, an interactive Streamlit Compliance Console for human review, and Python module APIs for integration into automated pipelines.

### REST API Endpoints (FastAPI)

The FastAPI server runs on `http://127.0.0.1:8000` with interactive OpenAPI documentation available at `/docs`.

| Method | Endpoint | Purpose | Input | Output | Error Cases |
|---|---|---|---|---|---|
| `GET` | `/api/health` | System health check and database connectivity check | None | JSON object with service status, database connectivity (`CONNECTED`), total users, and total logs | `500 Internal Server Error` if database connection fails |
| `GET` | `/api/users` | Query hospital clinician directory with filtering | Optional query params: `department` (str), `workforce_type` (str), `active` (bool) | Array of `UserResponse` objects (ID, employee ID, full name, role, workforce type, department, active status) | `500 Internal Server Error` on query failure |
| `GET` | `/api/shared-accounts` | Query shared account inventory with active authorization counts | None | Array of `SharedAccountResponse` objects (ID, username, system name, department, risk level, active authorized user count) | `500 Internal Server Error` on query failure |
| `GET` | `/api/delegations` | Query active, expired, or revoked delegation authorizations | Optional query params: `shared_account_id` (int), `user_id` (int), `status` (str) | Array of `AuthorizationResponse` objects (ID, user name, department, shared account, validity interval, approval notes, status) | `500 Internal Server Error` on query failure |
| `GET` | `/api/privileged-actions` | Retrieve catalog of sensitive clinical actions monitored by policy | None | Array of `PrivilegedActionResponse` objects (ID, action name, sensitivity level, description) | `500 Internal Server Error` on query failure |
| `GET` | `/api/logs` | Query ingested audit logs with pagination and sensitivity filters | Optional query params: `username` (str), `action` (str), `is_sensitive` (bool), `status` (str), `limit` (int, default 100, max 500), `offset` (int) | Array of `SystemLogResponse` objects (event ID, timestamp, username, source IP, device ID, action, sensitivity level, raw hash) | `500 Internal Server Error` on invalid query parameters |
| `GET` | `/api/attribution/results` | Query attribution results with confidence and status filters | Optional query params: `status` (str), `method` (str), `confidence_level` (str), `limit` (int, default 100, max 500), `offset` (int) | Array of `AttributionResultResponse` objects (baseline attribution, prototype attribution, confidence score, explanation, candidate scores) | `500 Internal Server Error` on query failure |
| `GET` | `/api/attribution/metrics` | Calculate and return comparative attribution metrics (baseline vs prototype) | None | `MetricsBreakdown` JSON object containing total sensitive events, baseline accuracy (43.90%), prototype accuracy (99.02%), net lift (+55.12%), and method distribution | `500 Internal Server Error` on metric calculation error |
| `GET` | `/api/attribution/{event_id}` | Retrieve comprehensive forensic dossier and candidate breakdown for a specific event | Path param: `event_id` (str) | `EventDetailResponse` JSON object with raw log, shared account context, privileged action metadata, baseline vs prototype comparison, candidate score array, and evidence checklist | `404 Not Found` if `event_id` does not exist; `500` on database error |
| `POST` | `/api/process-events` | Trigger end-to-end attribution processing on all unprocessed system logs | None (POST body optional) | JSON object: `{"status": "SUCCESS", "processed_count": N, "metrics": {...}}` | `500 Internal Server Error` if processing pipeline fails |

### Streamlit Compliance Console (Port 8501)

- **Entry Point**: `dashboard/app.py`
- **Purpose**: Interactive, human-in-the-loop compliance review console allowing auditors, compliance officers, and supervisors to inspect:
  1. Attribution Overview & Lift Metrics
  2. Baseline vs. Prototype Comparative Analysis
  3. Delegation & Session Lifecycle State Machines
  4. Ingestion Buffer & Delayed Reconciliation Inspector
  5. Multi-Source Evidence Correlation & Explainability Dossiers
  6. Telemetry Degradation Stress Testing Curves
  7. Human Escalation Queue & Adjudication Console
  8. SHA-256 Cryptographic Audit Chain Verification
  9. Project Requirement Completion Matrix (91.15% Gate Verification)
- **Role Perspectives**: Demonstration role selector (Compliance Officer, Security Analyst, Auditor, Supervisor, Reviewer) providing contextual views.

### Python Module Interfaces

For embedded workflows and headless evaluation, core services can be invoked directly:
- `AttributionEngine.attribute_event(event, delegations, sessions, context)`
- `IngestionBuffer.push(event)`, `IngestionBuffer.flush_ready(watermark)`, `IngestionBuffer.reconcile_late_delegation(delegation)`
- `DelegationManager.create_delegation(...)`, `DelegationManager.get_active_delegations(time, account)`
- `SessionManager.record_heartbeat(...)`, `SessionManager.get_active_session(...)`
- `TamperEvidentAuditChain.append_record(data)`, `TamperEvidentAuditChain.verify_chain()`
- `OperationalAlertManager.trigger_alert(...)`, `OperationalAlertManager.acknowledge_alert(...)`

---

## 5. Data & Database Schema

The repository maintains an active local **SQLite relational database** for transactional CRUD and API query serving, alongside **synthetic CSV dataset artifacts** for deterministic, reproducible offline benchmarking.

### SQLite Relational Database

- **Location**: `data/hospital_attribution.db`
- **ORM / Engine**: SQLAlchemy Declarative Models (`backend/app/models/`) over SQLite 3.
- **Connection**: Managed via `backend/app/database.py` with multi-threaded connection handling.

#### Entity Relationship & Table Specifications

| Table | Purpose | Key Fields | Relationships & Constraints |
|---|---|---|---|
| `users` | Hospital clinician roster and staff directory | `id` (PK, Integer, Index)<br>`employee_id` (Unique, String(50), Index)<br>`full_name` (String(100))<br>`role` (String(100))<br>`workforce_type` (String(50))<br>`department` (String(100))<br>`active` (Boolean)<br>`created_at` (DateTime) | One-to-many with `shared_account_authorization` (`user_id`).<br>One-to-many with `attribution_results` (`attributed_user_id`). |
| `shared_accounts` | Inventory of departmental shared workstations and generic service accounts | `id` (PK, Integer, Index)<br>`username` (Unique, String(50), Index)<br>`system_name` (String(100))<br>`department` (String(100))<br>`account_type` (String(50))<br>`status` (String(20))<br>`risk_level` (String(20))<br>`created_at` (DateTime) | One-to-many with `shared_account_authorization` (`shared_account_id`). |
| `shared_account_authorization` | Explicit temporal delegation grants authorizing a clinician to use a shared account | `id` (PK, Integer, Index)<br>`shared_account_id` (FK -> `shared_accounts.id`, Integer)<br>`user_id` (FK -> `users.id`, Integer)<br>`authorized_from` (DateTime)<br>`authorized_until` (DateTime)<br>`reason` (String(255))<br>`approved_by` (String(100))<br>`status` (String(20)) | Foreign key to `shared_accounts`.<br>Foreign key to `users`.<br>Status restricted to `ACTIVE`, `EXPIRED`, `REVOKED`. |
| `privileged_actions` | Governance catalog defining sensitive clinical actions and criticality tiers | `id` (PK, Integer, Index)<br>`action_name` (Unique, String(100), Index)<br>`sensitivity_level` (String(20): HIGH, CRITICAL, MEDIUM)<br>`description` (String(255)) | Referenced by log actions during sensitive-event classification. |
| `system_logs` | Ingested audit event records across clinical, authentication, and session streams | `id` (PK, Integer, Index)<br>`event_id` (Unique, String(64), Index)<br>`timestamp` (DateTime, Index)<br>`username` (String(50), Index)<br>`session_id` (String(64), Index, Nullable)<br>`source_system` (String(100))<br>`source_ip` (String(45))<br>`device_id` (String(50))<br>`action` (String(100), Index)<br>`target_type` (String(50))<br>`target_id` (String(100))<br>`success` (Boolean)<br>`raw_event_hash` (String(64), Index)<br>`received_at` (DateTime)<br>`processing_status` (String(20)) | One-to-one with `attribution_results` via `event_id`.<br>Status values: `NEW`, `PROCESSED`, `DUPLICATE`, `INVALID`. |
| `attribution_results` | Forensic identity attribution determinations, confidence scores, and candidate dossiers | `id` (PK, Integer, Index)<br>`event_id` (FK -> `system_logs.event_id`, Unique, Index)<br>`baseline_user_id` (FK -> `users.id`, Nullable)<br>`baseline_confidence` (Float)<br>`baseline_status` (String(20))<br>`baseline_explanation` (Text)<br>`attributed_user_id` (FK -> `users.id`, Nullable)<br>`attribution_method` (String(50))<br>`confidence_score` (Float)<br>`confidence_level` (String(20))<br>`attribution_status` (String(20))<br>`explanation` (Text)<br>`candidate_scores_json` (Text, Nullable)<br>`processed_at` (DateTime) | Foreign key to `system_logs` on `event_id`.<br>Foreign key to `users` for both baseline and prototype user resolution. |

### Synthetic Evaluation Datasets & Artifacts

For reproducible offline verification, statistical analysis, and stress benchmarking without running background SQLite servers, canonical CSV artifacts are maintained in `data/` and `results/`:
- `data/users.csv`: 18 synthetic hospital clinicians across 5 departments and 4 workforce categories.
- `data/shared_accounts.csv`: 6 departmental shared accounts (`radiology_shared`, `er_triage_shared`, etc.).
- `data/delegations.csv`: 26 temporal delegation records with planned, active, expired, and revoked states.
- `data/system_logs.csv`: 364 multi-source synthetic clinical log events.
- `data/privileged_actions.csv`: Policy catalog of 13 sensitive clinical actions.
- `results/metrics_v2.csv`: Canonical attribution accuracy benchmarks (203/205 = 99.02% vs 90/205 = 43.90%).
- `results/project_completion_matrix.csv`: 25-requirement weighted completion breakdown (103/113 = 91.15%).
- `results/performance_benchmark_v2.csv`: Multi-scale throughput benchmarks up to 50,000 events.
- `results/telemetry_degradation_v2.csv`: Telemetry stress testing degradation curves (100% to 0%).
- `results/escalation_queue.csv`: Audit log of escalated ambiguous actions.

---

## 6. Quick Start & Execution Commands

### Prerequisites
- Python 3.11+
- Windows PowerShell or Unix Shell

### Step 1: Virtual Environment Setup
```powershell
python -m venv backend/.venv
& "backend/.venv/Scripts/pip.exe" install -r backend/requirements.txt
```

### Step 2: Run Full Automated Regression Test Suite (39 Tests Passing)
```powershell
& "backend/.venv/Scripts/python.exe" -m pytest -v
```

### Step 3: Run Scaling Performance Benchmark (up to 50,000 Events)
```powershell
& "backend/.venv/Scripts/python.exe" src/performance_bench_v2.py
```

### Step 4: Run Clinical Scenario Validation Suite (8 Scenarios)
```powershell
& "backend/.venv/Scripts/python.exe" src/hospital_scenarios.py
```

### Step 5: Profile Data Quality Dimensions
```powershell
& "backend/.venv/Scripts/python.exe" src/data_quality.py
```

### Step 6: Launch Streamlit Compliance Review Console
```powershell
& "backend/.venv/Scripts/streamlit.exe" run dashboard/app.py
```
*Open [http://localhost:8501](http://localhost:8501) in your browser.*

---

## 7. Comparative Attribution Performance

Measured directly on 205 sensitive clinical actions across 6 shared hospital accounts:

| Evaluation Dimension | Naive Baseline (Shift Count) | Multi-Signal Prototype | Net Lift / Delta |
|---|---|---|---|
| **Total System Events** | 364 | 364 | — |
| **Sensitive Clinical Actions** | 205 | 205 | — |
| **Attributed Actions** | 90 | **203** | **+113 resolved** |
| **Ambiguous Actions** | 115 (Multiple staff active) | **1** (Overlapping shift) | **-114 resolved** |
| **Unattributed Actions** | 0 | **1** (Roster mismatch) | Safe triage |
| **Attribution Accuracy** | **43.90%** | **99.02%** | **+55.12% Net Lift** |
| **Escalation Rate** | 0.00% (Silent failure) | **0.98% (2 cases)** | Audit safe |

---

## 8. Project Requirement Coverage (Review #2 Gate)

| Requirement Group | Total Weight | Weighted Score | Requirement Coverage (%) |
|---|---|---|---|
| **Data Modeling** | 8.0 | 8.0 | 100.00% |
| **Delegation & Session** | 9.0 | 9.0 | 100.00% |
| **Ingestion & Normalization** | 13.0 | 13.0 | 100.00% |
| **Reconciliation & Resilience** | 12.0 | 12.0 | 100.00% |
| **Attribution & Correlation** | 22.0 | 22.0 | 100.00% |
| **Audit & Integrity** | 5.0 | 5.0 | 100.00% |
| **Alerts & Monitoring** | 4.0 | 4.0 | 100.00% |
| **Governance & Escalation** | 5.0 | 5.0 | 100.00% |
| **Validation & Benchmarking** | 14.0 | 14.0 | 100.00% |
| **User Interface & Usability** | 7.0 | 7.0 | 100.00% |
| **Ethics & Deployment** | 4.0 | 4.0 | 100.00% |
| **Future Enterprise Scope** | 10.0 | 0.0 (Deferred PoC) | 0.00% |
| **TOTAL** | **113.0** | **103.0** | **91.15% (GATE PASS)** |

*Requirement-by-requirement scoring recorded in `results/project_completion_matrix.csv`.*

---

## 9. Technical Documentation Index

For in-depth architectural and testing specifications, refer to the following documents in `docs/`:

| Document | File Path | Focus Area |
|---|---|---|
| **Unit Testing & Test Mapping** | [`docs/testing.md`](file:///r:/COE%20PROJECT/docs/testing.md) | Granular test suite overview (39/39 passing), module mapping, failure test cases, and execution logs |
| **Error Boundaries & Resilience** | [`docs/error_handling.md`](file:///r:/COE%20PROJECT/docs/error_handling.md) | 15-condition error matrix, error taxonomy, degradation boundaries, and non-forcing fallback principle |
| **System Architecture** | [`docs/architecture.md`](file:///r:/COE%20PROJECT/docs/architecture.md) | Architectural subsystems, data pipeline, cryptographic audit chaining, and state machines |
| **Attribution Methodology** | [`docs/methodology.md`](file:///r:/COE%20PROJECT/docs/methodology.md) | Multi-signal weighting formulation, baseline comparison, and confidence calibration |
| **Ethics & Limitations** | [`docs/ethics_and_limitations.md`](file:///r:/COE%20PROJECT/docs/ethics_and_limitations.md) | Ethical constraints, synthetic data boundaries, non-punitive governance, and legal considerations |
| **Deployment Checklist** | [`docs/deployment_checklist.md`](file:///r:/COE%20PROJECT/docs/deployment_checklist.md) | Pre-deployment verification, operational preconditions, and security baseline checklist |

---

## 10. Security, Ethics & Academic PoC Disclosures

> [!CAUTION]
> **Mandatory Ethical & Evidentiary Boundaries (docs/ethics_and_limitations.md):**
> 1. **Attribution is not proof of intent**: Machine attribution serves solely as an investigative support tool for hospital compliance officers and department heads. It must never trigger automated disciplinary actions.
> 2. **Telemetry is supporting context only**: IP addresses, subnet CIDRs, user-agents, and browser fingerprints do not independently prove identity.
> 3. **Mandatory human escalation**: Conflicting delegations or unlisted user rosters route directly to human compliance review.
> 4. **100% Synthetic Data**: All 18 clinician records, 6 shared accounts, 26 delegations, and 364 log events are deterministically synthesized. Zero real patient or employee PII is used.
> 5. **No Production Compliance Certification**: System metrics represent synthetic laboratory measurements and do not constitute HIPAA Security Rule or 21 CFR Part 11 certification.

---

## 11. Remaining Work Toward Final Submission

The remaining scope toward final project submission includes:
1. Exportable forensic compliance PDF audit packages for external hospital compliance auditors.
2. In-memory interactive case adjudication state persistence to disk within the Streamlit UI.
3. Expanded multi-ward patient transfer simulations across rotating shift boundaries.
