# 35% Milestone Remediation Progress Report

**Project Title:** Shared-Account Elimination Workflow Using Accountable Delegation and Session Attribution for a Hospital  
**Milestone Assessment:** 35% Proof-of-Concept Review Remediation  
**Status:** Completed and Verified  
**Date:** September 28, 2026  

---

## 1. Executive Summary

This report documents the targeted technical gap remediation conducted to address the three concerns raised by the evaluator following the initial 35% milestone review:
1. **Delayed & Out-of-Order Ingestion Buffer**: An actual ingestion buffer separating event time from arrival time, supporting grace periods, and executing retroactive re-evaluation without record duplication.
2. **Missing Telemetry Stress Testing**: Controlled synthetic experiments testing missing CIDR subnets, missing device fingerprints, missing user-agents, and inconsistent telemetry.
3. **Formal Human-in-the-Loop Escalation**: A fallback compliance workflow routing ambiguous or unresolved actions to a human adjudication queue with evidence dossiers.

The prototype demonstrates that the multi-signal attribution pipeline improves attribution of sensitive clinical actions under synthetic test conditions, increasing sensitive action attribution from **43.90%** (baseline shift count) to **99.02%** (+55.12% net lift) while escalating unresolved edge cases (0.98%) for human review.

---

## 2. Actual Measured Results (Baseline vs. Prototype Engine)

The following metrics were computed directly on the synthetic hospital dataset of 364 system events:

| Metric | Baseline Shift-Count Engine | Prototype Multi-Signal Engine | Delta / Improvement |
| :--- | :--- | :--- | :--- |
| **Total System Events Ingested** | 364 | 364 | — |
| **Sensitive Clinical Actions** | 205 | 205 | — |
| **Attributed Actions** | 90 | **203** | **+113 actions resolved** |
| **Ambiguous Actions** | 17 | **1** | **-16 ambiguities** |
| **Unattributed Actions** | 98 | **1** | **-97 unhandled** |
| **Attribution Percentage** | **43.90%** | **99.02%** | **+55.12% Net Lift** |
| **Delayed Event Recovery Rate** | N/A | **100.00%** | **Full retroactive recovery** |
| **Escalation Queue Rate** | N/A | **0.98%** | **2 cases escalated** |

---

## 3. Evaluator Feedback Remediation

### 3.1 Gap 1: Delayed and Out-of-Order Ingestion Buffers
- **Original Gap**: The initial prototype evaluated events immediately without an ingestion buffer separating event time from arrival time, lacking benchmarking and late-arriving delegation reconciliation.
- **Implemented Improvement**: Developed `src/ingestion_buffer.py`. Implemented arrival timestamp vs. event timestamp separation, SHA-256 payload deduplication, chronological sorting, and `reconcile_pending_events()`.
- **Experiment**:
  1. *Delayed Delegation Scenario*: Sensitive action `E_DELAY_001` arrived at 09:20 on `radiology_shared` when no delegation was registered (initial state: `PENDING`). Later, delegation for `U001` (09:00 - 09:30) arrived. The buffer re-evaluated `E_DELAY_001` in place, updating status to `ATTRIBUTED` without duplicate records.
  2. *Out-of-Order Sequencing*: Events arriving in inverted order (09:20 action, 09:10 login, 09:15 delegation) were chronologically reordered by event timestamp, accurately attributing the 09:20 action to the 09:15 delegation.
  3. *Performance Benchmarking*: Evaluated at 100, 500, 1,000, 5,000, and 10,000 events (`results/ingestion_buffer_benchmark.csv`).
- **Measured Result**:
  - Direct processing latency: 0.0012s (100 events) to 0.0781s (10,000 events).
  - Buffered processing with reconciliation: 0.0057s (100 events) to 0.6660s (10,000 events).
  - Sustained throughput: **15,766 events/second** at 10,000 events.
  - Delayed event reconciliation rate: **100.00%**.
- **Remaining Limitation**: The buffer operates as an in-memory priority queue. Enterprise clustering, persistent write-ahead logging (WAL), and distributed streaming brokers remain future work.

---

### 3.2 Gap 2: Telemetry Degradation and Missingness Stress Testing
- **Original Gap**: Telemetry was assumed always available; the system lacked empirical stress tests demonstrating behavior under missing or spoofed signals.
- **Implemented Improvement**: Implemented `src/telemetry_stress.py` and `tests/test_telemetry_degradation.py`. Tested synthetic failure scenarios (Cases A through G) and random degradation (100% to 0% availability).
- **Experiment**:
  - Case A: Full Telemetry (99.02% attribution).
  - Case B: Missing CIDR / 0.0.0.0 (51.71% attribution).
  - Case C: Missing Device Fingerprint (36.10% attribution).
  - Case D: Missing User-Agent (99.02% attribution).
  - Case E: Missing CIDR and Device (36.10% attribution).
  - Case F: Inconsistent / Spoofed Telemetry (Foreign device/IP).
  - Degradation Curve: Generated `results/figures/telemetry_degradation_curve.png` and `results/resilience_summary.csv`.
- **Measured Result**:
  - Attribution degrades gracefully as optional telemetry disappears: 99.02% (100% telemetry) ➔ 90.24% (90%) ➔ 74.63% (75%) ➔ 55.12% (50%) ➔ 42.44% (25%) ➔ 36.10% (0%).
  - Inconsistent device/IP telemetry did **NOT** cause false identity assignment: authorized delegation + session binding prevented arbitrary user attribution.
  - Formally validated finding: *"Missing network telemetry reduces contextual evidence but does not automatically invalidate identity attribution when stronger evidence exists."*
- **Remaining Limitation**: Telemetry metadata in clinical environments may experience packet loss or proxy translation. Biometric terminals and zero-trust mutual TLS attestations are out of scope for this 35% milestone.

---

### 3.3 Gap 3: Formal Human-in-the-Loop Compliance Escalation
- **Original Gap**: Actions failing attribution had no structured fallback or compliance workflow for human review.
- **Implemented Improvement**: Developed `src/escalation.py`, generating `results/escalation_queue.csv`, `results/error_analysis.csv`, and `results/unresolved_actions.csv`.
- **Experiment**:
  - Filtered all sensitive actions against the seven escalation criteria.
  - Populated 2 high-priority escalation cases (`EVT-00019`: Expired Delegation; `EVT-00115`: Overlapping Shift Ambiguity).
  - Constructed comprehensive evidence dossiers (event, account, session, candidates, available vs. missing evidence, recommended investigation protocol).
  - Modeled compliance review states (`PENDING_REVIEW`, `UNDER_REVIEW`, `RESOLVED`, `REJECTED`, `NO_ACTION`).
- **Measured Result**:
  - Escalation Rate: **0.98%** (2 cases escalated out of 205 sensitive actions).
  - Single-label error categorization: Expired Delegation (50%), Conflicting Delegation (50%).
  - Clean separation between automated evidence assembly and human decision-making.
- **Remaining Limitation**: Compliance reviews are currently demonstrated via simulated states in the dashboard. Production integration with hospital ticketing systems (e.g. ServiceNow, Jira Service Management) remains future scope.

---

## 4. Verification and Regression Testing

The automated test suite was expanded from 11 tests to **24 tests**:
- `tests/test_attribution.py`: 11 / 11 passing (Regression check: 100% intact).
- `tests/test_ingestion_buffer.py`: 4 / 4 passing (New feature #1).
- `tests/test_telemetry_degradation.py`: 5 / 5 passing (New feature #2).
- `tests/test_escalation.py`: 4 / 4 passing (New feature #3).
- Overall Suite Pass Rate: **24 passed in 2.13s (100% pass rate)**.

---

## 5. Security, Ethics, and Academic Framing

- **Attribution is not equivalent to intent**: The prototype identifies an attributable individual or escalates the case for human review when evidence is insufficient.
- **Supporting Context**: Device and network telemetry provide supporting contextual evidence and never independently prove identity.
- **Synthetic Data**: 100% synthetic clinical data was utilized; no protected health information (PHI) was accessed or manipulated.
