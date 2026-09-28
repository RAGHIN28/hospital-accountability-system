# Project Review #2 Report: Hospital Shared-Account Elimination & Accountable Action Attribution
**Milestone**: Project Review #2 (70% Completion Milestone)  
**System Designation**: Hospital Shared-Account Elimination & Accountable Action Attribution Engine  
**Target Coverage Gate**: $\ge 70.00\%$ Requirement Coverage  
**Measured Project Requirement Coverage**: **91.15%** (Requirement Gate: **PASS**)  
**Sensitive-Action Attribution Accuracy**: **99.02%** (Baseline: 43.90%, Net Lift: +55.12%)  
**Regression Test Status**: **39/39 Tests Passing (100.00% Pass Rate)**  
**Environment**: Academic Proof-of-Concept, Python 3.11, SQLite, Streamlit, 100% Synthetic Data  

---

## 1. Executive Summary

Healthcare environments depend heavily on shared clinical workstation accounts (e.g., `radiology_shared`, `er_triage_shared`, `icu_shared_ws`) to minimize terminal friction during critical patient care. However, when sensitive actions occur—such as narcotics dispensation, dosage alert overrides, or EHR export—shared credentials create an accountability void. Naive attribution methods (such as assigning actions to whoever was on shift) fail whenever multiple clinicians are active, achieving only **43.90%** attribution accuracy.

This project delivers a resilient, explainable, and multi-source attribution prototype designed to eliminate this accountability void. For Project Review #2, the system was expanded from its Review #1 baseline through a rigorous **Inspect → Verify → Implement → Test → Benchmark → Document → Acceptance Gate** methodology:
- **Verified Requirement Coverage**: **91.15%** across 25 granular requirements spanning 7 functional categories, surpassing the $\ge 70\%$ milestone gate.
- **Zero Regressions**: All 24 pre-existing Review #1 tests were preserved and passed, augmented by 15 new test cases (39 total tests passing in 2.06 seconds).
- **Review #1 Evaluator Concerns Remediated & Verified**:
  - *Gap A (Ingestion Buffers & Retroactive Re-evaluation)*: Ingestion buffer with time separation achieves a **100.00%** reconciliation rate for late shift authorizations without creating duplicate records.
  - *Gap B (Telemetry Stress Testing)*: Evaluated across 6 levels of telemetry loss (100% down to 0%), proving graceful degradation without identity fabrication.
  - *Gap C (Human Escalation Workflow)*: Compliance escalation queue implemented for ambiguous and conflicting actions with full cryptographic audit trail logging.

---

## 2. Original Problem Statement

The clinical environment encompasses four distinct personnel roles:
1. **Permanent Staff**: Attending physicians, staff nurses.
2. **Visiting Consultants**: Specialists on scheduled clinical rounds.
3. **Interns & Residents**: Trainees on rotating supervisory shifts.
4. **Outsourced Technicians**: Third-party radiological and laboratory operators.

Because all four groups access shared departmental terminals, the system must ingest five diverse telemetry streams:
- Shared account inventory (`data/raw/synthetic_hospital_data.csv`)
- User rosters and role status
- System and application logs (`data/system_logs.csv`)
- Shift delegations and authorizations
- Network and device telemetry (IP address, subnet CIDR, user-agent, device fingerprint)

The system must remain operational and resilient when telemetry streams are missing, delayed, duplicated, or received out-of-order, providing traceable evidence rather than opaque assumptions.

---

## 3. Review #1 Evaluator Feedback

Project Review #1 identified three technical areas requiring concrete remediation:
- **Gap A**: Implement and benchmark delayed and out-of-order event ingestion buffers, showing that late-arriving shift authorizations retroactively re-evaluate previously ambiguous records without data corruption.
- **Gap B**: Stress-test missing telemetry scenarios (dropped subnet CIDR, missing/spoofed user-agent, missing device fingerprints) and document resilience degradation curves.
- **Gap C**: Expand error analysis on unresolved actions and establish a formal fallback / human-in-the-loop escalation workflow for hospital compliance officers.

---

## 4. Review #1 Remediation Evidence

All three Review #1 gaps have been implemented, tested, and cataloged in `results/review1_remediation_matrix.csv`:

| Feedback ID | Evaluator Gap | Implemented Component | Source File | Test Suite | Result Artifact | Measured Result | Status |
|---|---|---|---|---|---|---|---|
| **REV1-GAP-A** | Delayed & Out-of-Order Ingestion Buffer | `IngestionBuffer` priority queue & retroactive reconciliation | `src/ingestion_buffer.py` | `tests/test_ingestion_buffer.py` | `results/ingestion_buffer_benchmark.csv` | 100% reconciliation rate; 15,766 events/sec throughput | **VERIFIED** |
| **REV1-GAP-B** | Telemetry Stress Testing & Degradation Curves | `TelemetryStressEngine` degradation harness | `src/telemetry_stress.py` | `tests/test_telemetry_degradation.py` | `results/telemetry_degradation_v2.csv` | Zero false identities assigned; 36.10% high-confidence attribution maintained; 131 actions safely escalated at 0% telemetry | **VERIFIED** |
| **REV1-GAP-C** | Human-in-the-Loop Escalation & Error Analysis | `EscalationService` & case review console | `src/escalation_service.py` | `tests/test_escalation.py` | `results/escalation_queue.csv`, `results/error_analysis_v2.csv` | 0.98% escalation rate (2 high-priority cases triaged) | **VERIFIED** |

---

## 5. Current Architecture

The Phase 2 architecture enforces a clean unidirectional ingestion pipeline:
```
Raw Synthetic Data Sources
 (App Logs, Auth Logs, Session Logs, Delegation Logs, Telemetry Logs)
                   │
                   ▼
       [ EventNormalizer ] ──► NormalizedEvent Schema (17 fields)
                   │
                   ▼
       [ IngestionBuffer ] ──► Priority Queue (Event-Time vs Arrival-Time)
                   │           SHA-256 Deduplication Table
                   ▼
  [ CrossSourceCorrelator & AttributionEngine ]
   ├── Delegation Lifecycle Validation (src/delegation_lifecycle.py)
   ├── Session Lifecycle Validation    (src/session_lifecycle.py)
   └── Deterministic Rules Engine
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
[ High Confidence ]   [ Ambiguous / Conflicted ]
   Attributed                │
   (203 events)              ▼
                    [ EscalationService ] ──► Compliance Review
                             │
                             ▼
              [ TamperEvidentAuditTrail ] ──► SHA-256 Linked Blocks
                             │
                             ▼
             [ Streamlit Compliance Console ] ──► 17 Live Sections
```

---

## 6. Data Model

The data layer models realistic clinical workflows using synthetic entities:
- **Staff Roster**: 18 individuals across 4 roles (Permanent Physicians, Nurses, Visiting Consultants, Interns, Technicians).
- **Shared Workstations**: 6 department accounts (`radiology_shared`, `er_triage_shared`, `icu_shared_ws`, `pharmacy_dispenser`, `lab_shared_ws`, `oncology_shared`).
- **Clinical Actions**: 10 sensitive action types (`ADMINISTER_MEDICATION`, `DISPENSE_NARCOTICS`, `MODIFY_PATIENT_RECORD`, `OVERRIDE_DOSAGE_ALERT`, `VIEW_PATIENT_RECORD`, `EXPORT_PATIENT_DATA`, `CHANGE_TREATMENT_PLAN`, `SIGN_OFF_DISCHARGE`, `EMERGENCY_ACCESS_OVERRIDE`, `ORDER_LAB_TEST`).
- **System Events**: 364 total system events; 205 sensitive clinical actions.

---

## 7. Delegation Lifecycle

Implemented in `src/delegation_lifecycle.py` and validated by `tests/test_delegation_lifecycle.py` (4 tests passing).
- **Supported States**: `CREATED`, `ACTIVE`, `EXPIRED`, `REVOKED`, `CANCELLED`.
- **Temporal Enforcement**:
  - `CREATED`: Pre-shift registration; cannot authorize actions prior to `start_time`.
  - `ACTIVE`: Current time inside `[start_time, end_time]`.
  - `EXPIRED`: Time exceeds `end_time`; authorization lapses.
  - `REVOKED`: Explicitly rescinded by department head prior to expiry; subsequent actions rejected.
  - `CANCELLED`: Shift voided prior to activation.
- **Historical Invariant**: Historical transactions executed during a valid delegation window retain their attribution integrity even after subsequent expiration or revocation.

---

## 8. Session Lifecycle

Implemented in `src/session_lifecycle.py` and validated by `tests/test_session_lifecycle.py` (5 tests passing).
- **Supported States**: `CREATED`, `ACTIVE`, `IDLE`, `ENDED`, `EXPIRED`, `TERMINATED`.
- **Configurable Idle Timeout**: Default set to 30 minutes of inactivity.
- **Activity Refresh**: Any authenticated action automatically updates the rolling activity timestamp.
- **Explicit Termination**: Terminal logout immediately moves state to `TERMINATED`.

---

## 9. Multi-Source Ingestion Layer

Implemented in `src/multi_source_ingestion.py`. Ingests five distinct log streams:
1. `APPLICATION_LOG`: Primary clinical events.
2. `AUTH_LOG`: User workstation login / smartcard assertion.
3. `SESSION_LOG`: Terminal lock/unlock and activity refresh.
4. `DELEGATION_LOG`: Shift assignment and authorization windows.
5. `TELEMETRY_LOG`: IP, subnet CIDR, user-agent, device hardware fingerprint.

---

## 10. Common Normalized Event Schema

Implemented in `src/normalization.py`. Defines `NormalizedEvent` with 17 canonical attributes:
`event_id`, `source`, `event_type`, `event_time`, `arrival_time`, `shared_account`, `user_id`, `session_id`, `action_type`, `resource`, `ip_address`, `device_id`, `user_agent`, `subnet_cidr`, `delegation_id`, `raw_reference`, `ingestion_id`.
Malformed payloads produce structured validation errors rather than crashing the pipeline.

---

## 11. Cross-Source Correlation

Implemented in `src/evidence_model.py`. Performs deterministic multi-dimensional correlation:
```
Clinical Application Action
   + Active Delegation Window Match
   + Active Workstation Session Match
   + Subnet CIDR & Device Fingerprint Corroboration
   ─────────────────────────────────────────────────
   = Adjudicated Identity with Transparent Dossier
```
No opaque machine learning models or black-box neural networks are used.

---

## 12. Explainable Evidence Model

Every sensitive clinical action produces an `ExplainableEvidenceDossier` containing:
- `identity_candidate`: Primary clinician candidate.
- `confidence_tier`: `STRONG`, `SUPPORTING`, `MISSING`, `CONFLICTING`, `INSUFFICIENT`.
- `signal_breakdown`: Explicit justification for each telemetry dimension.
- `conflicting_signals`: Concurrent authorizations or overlapping sessions.
- `final_status`: `ATTRIBUTED`, `PARTIAL`, `AMBIGUOUS`, `UNATTRIBUTED`, or `PENDING`.

---

## 13. Attribution Logic

The attribution engine evaluates events sequentially:
1. Direct named user in event payload $\rightarrow$ `ATTRIBUTED` (`DIRECT_USER`).
2. Shared account $\rightarrow$ Query delegations valid at `event_time`.
3. If no delegation exists $\rightarrow$ Hold in buffer as `PENDING` (`WAITING_FOR_DELEGATION`).
4. If exactly one active delegation matches active session $\rightarrow$ `ATTRIBUTED`.
5. If multiple delegations overlap with identical telemetry $\rightarrow$ `AMBIGUOUS` $\rightarrow$ Escalation Queue.
6. If delegation is revoked or expired $\rightarrow$ `UNATTRIBUTED` $\rightarrow$ Security Alert.

---

## 14. Baseline Implementation

The baseline engine (`src/baseline.py`) implements a naive shift-count heuristic:
- If zero clinicians are scheduled: `UNATTRIBUTED`.
- If exactly one clinician is scheduled: `ATTRIBUTED`.
- If two or more clinicians are scheduled: `AMBIGUOUS`.

---

## 15. Target Attribution Benchmark

- **Pre-Registered Baseline**: 43.90% attribution rate.
- **Design Target**: $>90.00\%$ attribution rate on synthetic clinical workloads.
- **Milestone Gate Target**: $\ge 70.00\%$ project requirement coverage.

---

## 16. Measured Attribution Results

| Evaluation Metric | Baseline Rule | Prototype Engine | Absolute Improvement |
|---|---|---|---|
| Total Sensitive Actions | 205 | 205 | — |
| Attributed Actions | 90 | 203 | +113 actions |
| Ambiguous Actions | 115 | 1 | -114 actions |
| Unattributed Actions | 0 | 1 | +1 action |
| **Attribution Percentage** | **43.90%** | **99.02%** | **+55.12% Net Lift** |
| Human Escalation Rate | 0.00% (Silent Failure) | 0.98% (2 cases) | Safe Triage |

---

## 17. Error Analysis

Unresolved events are categorized using a 13-point taxonomy (`results/error_analysis_v2.csv`):
- `EVT_SYNTH_0199`: `CHANGE_TREATMENT_PLAN` on `radiology_shared`. Root cause: `CONFLICTING_DELEGATION` (Overlapping shifts for `U002` and `U007`). Machine result: `AMBIGUOUS`. Escalated as `CASE_2026_001`.
- `EVT_SYNTH_0245`: `EMERGENCY_ACCESS_OVERRIDE` on `er_triage_shared`. Root cause: `UNKNOWN_USER` (User `U999` not present in hospital personnel directory). Machine result: `UNATTRIBUTED`. Escalated as `CASE_2026_002`.

---

## 18. Delayed Event Experiment (Review #1 Gap A)

- **Total Delayed Events Ingested**: 15 sensitive actions arrived before their shift delegation records.
- **Initial Buffer State**: 15 events marked `PENDING` (`WAITING_FOR_DELEGATION`).
- **Retroactive Reconciliation**: Shift delegation records arrived 15 minutes later. The engine executed `reconcile_pending_events()`.
- **Measured Reconciliation Rate**: **100.00%** (15 / 15 reconciled to `ATTRIBUTED`).
- **Integrity Guarantee**: The existing event record was updated in-place; zero duplicate event records were generated.

---

## 19. Out-of-Order Event Experiment

Evaluated in `tests/test_ingestion_buffer.py`:
- Event Stream: Action at `09:20`, Login at `09:10`, Delegation at `09:15`.
- Buffer Ordering: Priority queue correctly reconstructed chronological sequence (`09:10` $\rightarrow$ `09:15` $\rightarrow$ `09:20`).
- Result: Action evaluated with full authorization context; zero state distortion.

---

## 20. Duplicate Event Experiment

Evaluated in `tests/test_ingestion_buffer.py`:
- Identical payload hashes submitted twice within the buffer window.
- Result: Duplicate ingestion rejected with `DUPLICATE_EVENT_REJECTED` code; zero duplicate metrics counted.

---

## 21. Telemetry Degradation Experiment (Review #1 Gap B)

Evaluated in `src/telemetry_stress.py` and recorded in `results/telemetry_degradation_v2.csv`:

| Telemetry Availability | Total Sensitive | Attributed | Partial | Ambiguous | Unattributed | Escalated | Attribution Rate | Degradation | Anti-Spoofing Status |
|---|---|---|---|---|---|---|---|---|---|
| **100% (Full Telemetry)** | 205 | 203 | 0 | 1 | 1 | 2 | **99.02%** | 0.00% | VERIFIED_RESILIENT |
| **90% Availability** | 205 | 185 | 0 | 1 | 19 | 20 | **90.24%** | 8.78% | VERIFIED_RESILIENT |
| **75% Availability** | 205 | 153 | 0 | 1 | 51 | 52 | **74.63%** | 24.39% | VERIFIED_RESILIENT |
| **50% Availability** | 205 | 113 | 0 | 1 | 91 | 92 | **55.12%** | 43.90% | VERIFIED_RESILIENT |
| **25% Availability** | 205 | 87 | 0 | 1 | 117 | 118 | **42.44%** | 56.58% | VERIFIED_RESILIENT |
| **0% (Zero Telemetry)** | 205 | 74 | 0 | 1 | 130 | 131 | **36.10%** | 62.92% | VERIFIED_RESILIENT |

**Resilience Principle**: When optional telemetry is absent, the engine falls back strictly to verifiable delegation windows and session bounds. It maintains 36.10% attribution on unambiguous high-confidence events (74 actions), safely escalating all 131 telemetry-dependent actions (63.90%) to compliance review rather than guessing or fabricating identity. Zero false-positive identities are assigned.

---

## 22. Human-in-the-Loop Escalation (Review #1 Gap C)

Implemented in `src/escalation_service.py`:
- **Escalation Queue**: 2 high-priority incidents triaged (`CASE_2026_001` and `CASE_2026_002`).
- **Simulated Roles**: `Compliance Officer`, `Security Analyst`, `Department Supervisor`.
- **Supported Decisions**: `CONFIRM_IDENTITY`, `MARK_UNATTRIBUTED`, `REQUEST_MORE_EVIDENCE`, `DISMISS`, `ESCALATE`.
- **Audit Integration**: All adjudication decisions append an immutable entry to the cryptographic audit trail.

---

## 23. Tamper-Evident Audit Trail

Implemented in `src/audit_chain.py` and validated by `tests/test_audit_chain.py` (4 tests passing):
- SHA-256 cryptographic linkage: `record_hash = SHA256(index + timestamp + actor + action + details + previous_hash)`.
- Verification engine detects modified records, deleted blocks, and broken previous hashes with 100% accuracy.

---

## 24. Operational Alerting

Implemented in `src/alerts.py` and validated by `tests/test_alerts.py` (2 tests passing):
- 9 Alert Types: `EXPIRED_DELEGATION_USAGE`, `REVOKED_DELEGATION_USAGE`, `CONFLICTING_DELEGATION`, `EXPIRED_SESSION_ACTION`, `UNKNOWN_USER_ROSTER`, `AFTER_HOURS_ACCESS`, `REPEATED_ATTRIBUTION_FAILURE`, `SUSPICIOUS_SHARED_USAGE`, `TAMPER_DETECTED`.
- Deduplication: Keyed by `(alert_type, event_id, account)` to avoid SOC fatigue.

---

## 25. Scenario Validation

Implemented in `src/hospital_scenarios.py` and saved to `results/scenario_validation.csv`:
- All 8 end-to-end clinical scenarios passed (100% scenario pass rate).
- Validated normal delegation, late arrivals, out-of-order logs, expired/revoked shifts, overlapping conflicts, degraded telemetry, off-hours access, and duplicate streams.

---

## 26. Performance Benchmarking

Extended benchmark results up to 50,000 synthetic events (`results/performance_benchmark_v2.csv`):

| Target Workload | Total Ingested Events | Rejected Duplicates | Sequenced Out-of-Order | Buffered Late | Reconciled Events | Duration (s) | Measured Throughput | Errors |
|---|---|---|---|---|---|---|---|---|
| **1,000** | 1,050 | 50 | 981 | 143 | 143 | 0.0982s | **10,694 evt/s** | 0 |
| **5,000** | 5,250 | 250 | 4,977 | 715 | 715 | 0.3350s | **15,670 evt/s** | 0 |
| **10,000** | 10,500 | 500 | 9,971 | 1,429 | 1,429 | 0.7004s | **14,992 evt/s** | 0 |
| **25,000** | 26,250 | 3,972 | 22,231 | 3,572 | 3,572 | 1.7659s | **14,865 evt/s** | 0 |
| **50,000** | 52,500 | 19,713 | 32,710 | 7,143 | 7,143 | 2.9599s | **17,737 evt/s** | 0 |

---

## 27. Data Quality Metrics

Quantified across quality dimensions (`results/data_quality_metrics.csv`):
- Total System Events Audited: 364 events (100.0% coverage)
- Synthetic Duplicate Presentation Rate: 4.76% (50 duplicate arrivals presented in synthetic intake benchmark)
- Duplicate Events Rejected at Boundary: 100.0% (50/50 duplicates dropped via SHA-256 hash table)
- Post-Deduplication Duplicate Rate: 0.00% (0 duplicate records stored in persistent database)
- Malformed Event Rate: 0.00%
- Missing Optional Field Rate: 0.55% (2 records with missing/generic telemetry)
- Unknown Session ID Rate: 0.27% (1 record with unassigned session)
- Simulated Late Event Rate: 14.29% (15 delayed events recovered)
- Simulated Out-of-Order Rate: 80.95% (85 arrival-jittered events sequenced)
- Conflicting Delegation Rate: 0.49% (1 clinical action with overlapping shifts)
- Unresolved Attribution Rate: 0.98% (2 actions escalated to human review)

---

## 28. Dashboard Walkthrough

The Streamlit dashboard (`dashboard/app.py`) was expanded to provide 17 dedicated compliance views:
1. Attribution Overview
2. Baseline vs Prototype
3. Delegation Lifecycle
4. Session Lifecycle
5. Ingestion Buffer
6. Delayed Reconciliation
7. Out-of-Order Events
8. Multi-Source Correlation
9. Evidence / Explainability
10. Telemetry Stress
11. Error Analysis
12. Alerts
13. Human Review
14. Audit Chain Verification
15. Performance
16. Scenario Validation
17. Project Completion

---

## 29. Usability Walkthrough

Documented in `docs/usability_walkthrough.md`. Provides a 12-step operator guide covering workstation triage, evidentiary inspection, compliance adjudication, and audit verification.

---

## 30. Ethics Scoping

Documented in `docs/ethics_and_limitations.md`. Formally disclaims automated punishment, establishes telemetry as non-identity evidence, and affirms 100% synthetic data boundaries.

---

## 31. Deployment Checklist

Documented in `docs/deployment_checklist.md`. Covers Data, Security, Operations, Governance, and explicitly delineates enterprise production gaps.

---

## 32. Limitations

- Academic proof-of-concept operating locally in Python/SQLite.
- Does not integrate with live clinical hospital EHR/EMRs (Epic, Cerner) or PACS.
- Physical relay/shoulder-surfing attacks require biometric or physical badge lanyards outside software scope.

---

## 33. Project Completion Matrix

Full matrix recorded in `results/project_completion_matrix.csv`:
- Total Requirements: 25
- Implemented and Evidenced: 24 (Score: 1.0)
- Appropriately Deferred Enterprise Integration: 1 (Score: 0.0, Weight: 10.0)
- Total Weight: 113.0
- Weighted Score: 103.0
- **Verified Project Requirement Coverage: 91.15%** (Surpasses $\ge 70.00\%$ gate).

---

## 34. Remaining Work Toward Final Submission

Scope for the remaining final-stage milestone includes:
1. Interactive case adjudication persistence directly to disk in the Streamlit UI.
2. Exportable PDF/CSV forensic audit reports for external hospital compliance auditors.
3. Expanded synthetic scenario generator supporting custom multi-ward ward-transfer simulations.

---

## 35. Review #2 Acceptance Summary

- **Project Requirement Coverage**: **91.15%** ($\ge 70.00\%$ target met)
- **Review #1 Gaps Remediated**: **3 / 3 (100% Verified)**
- **Regression Test Suite**: **39 / 39 Passing (100% Pass Rate)**
- **Deterministic Lift over Baseline**: **+55.12%**
- **Milestone Determination**: **PASS**
