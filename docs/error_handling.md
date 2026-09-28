# Error Handling, Boundaries & System Resilience

> **Hospital Shared-Account Elimination & Accountable Action Attribution**  
> **Milestone**: Project Review #2 (70% Completion Milestone)  
> **Architecture Level**: Resilience, Fault Tolerance & Exception Boundaries

---

## 1. Core Error-Handling Philosophy & Fallback Principle

In clinical environments, automated attribution operates under strict safety invariants:

> **The Non-Forcing Fallback Principle**:  
> *"Do not force an identity when evidence is insufficient; preserve the ambiguity and escalate for human review."*

The system adheres to the fundamental principle that **attribution is an accountability-support tool, not an automated accusation or disciplinary system**. When telemetry is missing, delegations overlap, or logs arrive out of sequence, the engine never relies on statistical guessing, machine learning hallucinations, or coin-flip heuristics. Instead, the engine transparently classifies the failure mode, grades the evidence dossier, and safely routes uncertain transactions to the **Human-in-the-Loop Compliance Escalation Queue** (`src/escalation.py`).

---

## 2. Taxonomy of System Error Classes

To guarantee precise operational handling and prevent category confusion, system issues are categorized into eight distinct error classes:

1. **Validation Error**: Payload syntax errors, missing mandatory schema fields, unparseable timestamps, or corrupted datatypes detected at the normalization boundary (`src/normalization.py`).
2. **Ingestion Error**: Disordered packet arrivals, out-of-sequence timestamps, or temporal inversions handled by the priority queue watermark buffer (`src/ingestion_buffer.py`).
3. **Data-Quality Issue**: Duplicate log submissions, redundant payload deliveries, or replay events filtered via deterministic SHA-256 intake hashing (`src/data_quality.py`).
4. **Attribution Ambiguity**: Situations where multiple authorized clinicians share active shifts on the same terminal with identical evidence scores (score margin < 10 points).
5. **Conflicting Evidence**: Inconsistencies between data sources (e.g., active delegation for User A, but active terminal session token assigned to User B).
6. **Telemetry Degradation**: Partial or total absence of network context (missing subnet CIDR, missing device fingerprint, spoofed user-agent headers).
7. **Operational Alert**: Critical security-relevant events (e.g., sensitive action executed under expired delegation) requiring automated notification (`src/alerts.py`).
8. **Human-Review Escalation**: Formal incident creation in `results/escalation_queue.csv` triggering compliance officer investigation.

---

## 3. Comprehensive Error Boundary Matrix (15 Specific Conditions)

The table below documents how the system detects, bounds, and responds to all fifteen operational fault conditions:

| # | Condition | Detection Mechanism | System Response | Attribution Impact | Human Review? |
|---|:---|:---|:---|:---|:---:|
| **1** | **Invalid or incomplete event data** | `EventNormalizer.normalize()` checks required fields (`timestamp`, `username`, `action`, `device_id`). | Rejects malformed payload; assigns processing status `INVALID`; logs normalization error; drops from attribution scoring pipeline. | Unattributed (`INVALID_PAYLOAD`). Does not corrupt database. | No (Logged for IT / ingestion debugging). |
| **2** | **Duplicate events received** | SHA-256 payload hash computed at boundary: `SHA256(ts \|\| acc \|\| act \|\| ip \|\| dev \|\| sess)`. Checked against `seen_hashes` set. | Intake filter drops duplicate immediately; increments duplicate counter in `data_quality_metrics.csv`; returns `DUPLICATE` status. | Zero impact on attribution stats; prevents inflation of action counts. | No (Automated suppression; 100% boundary defense). |
| **3** | **Events arrive out of order** | `IngestionBuffer.ingest()` compares incoming `event_timestamp` against previous watermark and arrival queue. | In-memory priority queue (`heapq`) orders events chronologically by `event_timestamp`, separating event time from arrival time. | Preserves causal chronological ordering; ensures state machines process in temporal order. | No (Resolved automatically by ingestion buffer). |
| **4** | **Events arrive late** | `IngestionBuffer` compares `arrival_timestamp - event_timestamp` against 30s grace window. | Event is ingested and sequenced into its correct historical time slot within the priority queue. | Causal sequence reconstructed; historical state evaluated accurately. | No (Handled within 30s grace window). |
| **5** | **Delegation information arrives after action** | At arrival time, no active delegation exists in database for the event's `event_timestamp`. | Engine holds transaction in `PENDING` buffer state. Upon late delegation arrival, `reconcile_pending_events()` re-evaluates the event in-place. | Reconciled from `PENDING` to `ATTRIBUTED` without duplicate database records (15/15 reconciled = 100%). | Only if late delegation still does not cover the timestamp. |
| **6** | **Delegation is expired or revoked** | `DelegationLifecycleManager.is_valid_for_action()` checks delegation status (`EXPIRED` or `REVOKED`) against event timestamp. | Blocks authorization match; triggers `EXPIRED_DELEGATION_USED` operational alert (`src/alerts.py`); dispatches incident. | Disqualifies user from delegation score (+0 pts); results in `UNATTRIBUTED` status. | **Yes** (Dispatched to compliance queue for policy violation). |
| **7** | **Session information is missing or expired** | `SessionLifecycleManager.is_session_valid()` checks session presence and verifies inactivity gap $\le 30$ minutes. | If missing: session signal = 0 pts. If expired: transitions session to `EXPIRED` state and rejects session binding (+0 pts). | Session score dropped (+0 pts). Action may still be attributed if strong delegation + telemetry exist ($\ge 60$ pts). | Only if overall score falls below 60 pts. |
| **8** | **Device/network telemetry missing** | Null, empty, or unresolvable IP subnet CIDR, device ID, or user-agent strings. | Graceful fallback in `TelemetryStressEngine`: sets telemetry component scores to 0; does not raise exceptions. | Reduces score by up to 25 pts (+15 device, +10 subnet). Strong credential/delegation matches ($\ge 70$ pts) remain attributed. | Only if remaining evidence score < 60 pts. |
| **9** | **Telemetry degraded to 0%** | All network/device context missing or suppressed across the workstation fleet. | Engine evaluates actions strictly on core direct evidence: shift delegation (+40 pts) and session tokens (+30 pts). | 36.10% attribution maintained solely on strong credentials (74 actions). 131 uncertain actions safely escalated. | **Yes** (63.90% escalation rate; zero false identities invented). |
| **10** | **Evidence conflicts** | Competing signals point to different clinicians (e.g., User A holds delegation, User B holds active session). | Evidence classifier tags dossier as `CONFLICTING`; calculates candidate margins. If margin < 10 pts, refuses resolution. | Status marked `AMBIGUOUS`; prevents incorrect attribution or coin-flip guesswork. | **Yes** (High-priority compliance incident created). |
| **11** | **User identity cannot be established** | No candidate achieves $\ge 60$ points, or candidate pool is empty. | Engine flags event as `UNATTRIBUTED`; records explanation in `AttributionResult`; assembles partial evidence dossier. | Status: `UNATTRIBUTED`. Confidence: 0.0. Explanatory audit trail preserved. | **Yes** (Logged to escalation queue for investigation). |
| **12** | **Action remains ambiguous** | Multiple candidates score within 10 points of each other (e.g. 100 vs 100). | `AttributionEngine` refuses to resolve; classifies status as `AMBIGUOUS`; generates structured error taxonomy code. | Ambiguity explicitly preserved; score breakdown for all candidates exported to dossier. | **Yes** (Routes to compliance officer with candidate score breakdown). |
| **13** | **User absent from staff roster** | Session or log asserts employee ID not found in `users` table / active staff roster (e.g., `U999`). | `EscalationManager` flags primary error as `UNKNOWN_USER_ROSTER` / `MISSING_ROSTER`; creates high-priority incident. | Action marked `UNATTRIBUTED`; unmapped user cannot be awarded credentials. | **Yes** (Immediate investigation of potential rogue or de-provisioned account). |
| **14** | **Audit-chain integrity violated** | `TamperEvidentAuditTrail.verify_chain()` detects mismatch in `record_hash` or broken `previous_hash` pointer. | Verification halts immediately; returns `(False, error_reason, bad_index)`; alerts security operations center (SOC). | Audit trail flagged as compromised; prevents reliance on tampered historical records. | **Yes** (Critical security escalation for digital forensics). |
| **15** | **Operational alert generated** | `OperationalAlertManager.trigger_alert()` invoked by security rule (e.g. unauthorized shared-account usage). | Generates alert record; applies deduplication key to suppress flood; sets status `OPEN`; dispatches to console. | Alert logged alongside attribution result; links alert ID to underlying event ID. | **Yes** (Reviewed by SOC analyst or compliance reviewer). |

---

## 4. Resilience Architecture: Component Error Handlers

### 4.1 Ingestion Boundary (`src/normalization.py` & `src/ingestion_buffer.py`)
- **Strict Invariant**: Corrupted or unparseable input streams must never crash the ingestion daemon.
- **Implementation**: Try-except wrappers validate input types against the 17-field canonical specification. Malformed records are diverted to a dead-letter quarantine structure, while valid records are ingested without latency impact.
- **Deduplication Boundary**: Deterministic SHA-256 hashing across `timestamp`, `username`, `action`, `source_ip`, `device_id`, and `session_id` guarantees that network retries or log-shipper replays are rejected before database insertion.

### 4.2 Lifecycle State Machines (`src/delegation_lifecycle.py` & `src/session_lifecycle.py`)
- **State Immutability**: Terminal states (`REVOKED`, `CANCELLED`, `EXPIRED`, `TERMINATED`) are final. A temporal update cannot resurrect a cancelled delegation or reactivate an administratively terminated session.
- **Boundary Clamping**: Time comparison logic uses inclusive boundaries (`start_time <= event_time <= end_time`) and strict nanosecond-safe comparisons to prevent temporal boundary leakage.

### 4.3 Evidence Dossier & Confidence Grading (`src/evidence_model.py`)
- Every attribution decision is accompanied by a transparent evidentiary dossier:
  - `STRONG`: Primary signals (delegation + session) fully verified ($\ge 70$ pts).
  - `SUPPORTING`: Contextual network signals corroborate identity.
  - `MISSING`: One or more optional signals absent (score degraded, not invalidated).
  - `CONFLICTING`: Competing authorized users detected (escalation triggered).
  - `INSUFFICIENT`: Total score $< 60$ points (automated resolution refused).

### 4.4 Human-in-the-Loop Triage (`src/escalation.py`)
- **Deterministic Error Taxonomy**: Unresolved actions are categorized under one of 13 mutually exclusive error codes (`CONFLICTING_DELEGATION`, `MISSING_ROSTER`, `EXPIRED_DELEGATION`, `INCONSISTENT_TELEMETRY`, etc.) to prevent subjective ambiguity.
- **Adjudication States**: Compliance officers interact with cases via five formal actions (`CONFIRM_IDENTITY`, `MARK_UNATTRIBUTED`, `REQUEST_MORE_EVIDENCE`, `DISMISS`, `ESCALATE`), with each decision recorded in the append-only cryptographic audit chain.
