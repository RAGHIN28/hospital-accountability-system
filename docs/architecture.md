# System Architecture & Technical Specification

> **Hospital Accountability System — Project Review #2 (70% Completion Milestone)**  
> Accountable Shift Delegation, Session Attribution, Ingestion Buffering, and Compliance Escalation.

---

## 1. High-Level Architectural Overview

The Hospital Accountability System provides a deterministic, auditable multi-signal pipeline to resolve identity ambiguity created by shared departmental accounts (e.g. `radiology_shared`, `lab_shared`, `pharmacy_shared`, `billing_shared`, `ward_shared`, `admin_shared`).

```
                INCOMING SYSTEM LOG EVENT STREAM
                               ↓
       [ Ingestion Buffer & Event-Time Ordering ]
       - Separates Event Timestamp from Arrival Timestamp
       - SHA-256 Payload Hash Deduplication
       - Chronological Watermark & Grace Window (30s)
                               ↓
                [ Context Availability Check ]
                               ├── Context Missing → [ Pending Buffer ] ──(Late Delegation)──┐
                               ↓                                                               │
       [ Multi-Signal Attribution Engine (Prototype) ]                                         │
       - Signal 1: Active Shift Delegation Window (+40 pts)                                    │
       - Signal 2: Session Identity Binding        (+30 pts)                                    │
       - Signal 3: Device Workstation Match        (+15 pts)                                    │
       - Signal 4: IP Subnet Match                 (+10 pts)                                    │
       - Signal 5: Department Match                (+5 pts)                                     │
                               ↓                                                               │
             [ Confidence Tier & Ambiguity Gate ]                                              │
             ├── Confident (Score ≥ 60 & Margin > 10) ➔ ATTRIBUTED                             │
             │                                                                                 │
             └── Ambiguous / Insufficient Evidence ────┐                                       │
                                                       ↓                                       │
                                     [ Compliance Escalation Queue ] ◄─────────────────────────┘
                                     - Priority Assignment (HIGH / MED / LOW)
                                     - Primary Error Categorization (12 Classes)
                                     - Evidence Dossier Assembly
                                                       ↓
                                            [ Human-in-the-Loop ]
                                            - Compliance Officer Adjudication
                                            - States: Under Review, Resolved, Rejected
```

---

## 2. Ingestion Buffer and Late Event Reconciliation

### 2.1 Separation of Event Time from Arrival Time
Network latency, intermittent clinical workstation connectivity, and offline logging queues cause telemetry events to arrive disordered. The ingestion buffer implements a strict dichotomy:
- **Event Time (`event_timestamp`)**: The exact timestamp when the clinical action transpired on the workstation.
- **Arrival Time (`arrival_timestamp`)**: The ingestion receipt timestamp at the server buffer.

The system sorts and sequences events according to `event_timestamp`, preventing chronological inversion anomalies.

### 2.2 Deduplication Mechanism
Every event is fingerprinted using a deterministic SHA-256 digest computed over immutable payload components:
$$\text{Hash} = \text{SHA256}(\text{timestamp} \parallel \text{account\_id} \parallel \text{action\_id} \parallel \text{ip\_address} \parallel \text{device\_id} \parallel \text{session\_id})$$
Duplicate event IDs or matching hash signatures are rejected prior to pipeline scoring.

### 2.3 Watermark & Grace Period
A configurable grace window (`BUFFER_GRACE_PERIOD_SECONDS = 30`) holds pending events awaiting asynchronous shift delegation approvals or session sync feeds before final escalation.

### 2.4 Retroactive Reconciliation Protocol
When late delegation context arrives:
1. Pending events matching the shared account and temporal window are queried via `reconcile_pending_events()`.
2. The attribution scoring algorithm is re-executed.
3. The original event record is updated in place, preserving `event_id` and `event_timestamp`.
4. `initial_status` is retained as `PENDING`, `final_status` is updated to `ATTRIBUTED`, and `resolution_type` is recorded as `LATE_DELEGATION`.
5. No duplicate database or log entries are created.

---

## 3. Telemetry Degradation Resilience

Telemetry feeds (IP subnet CIDR, workstation device fingerprints, user-agent headers) are treated strictly as **supporting contextual evidence**:
- **Core Attribution Proof**: Active delegation window, session token binding, event timestamp, and user roster status.
- **Supporting Telemetry**: Increases or decreases confidence scores but **never independently proves identity**.
- **Anti-Spoofing Safety**: An inconsistent device fingerprint or foreign IP subnet does not switch attribution to an arbitrary individual; the system maintains attribution to authorized staff based on stronger evidence or escalates to compliance review.

---

## 4. Human-in-the-Loop Compliance Escalation

When automated attribution cannot reach an explainable, confident decision, the action is routed to the **Compliance Officer Escalation Queue** (`results/escalation_queue.csv`).

### Escalation Conditions:
1. Multiple valid users match the same event (competing scores within 10 pts).
2. Required attribution evidence is missing.
3. Delegation authorization is expired.
4. Session information is missing and unrecoverable.
5. User roster record is unavailable or inactive.
6. Telemetry conflict creates unresolved ambiguity.
7. Attribution engine score falls below the required threshold (< 60 pts).

### Human Review States:
- `PENDING_REVIEW`: Awaiting review assignment.
- `UNDER_REVIEW`: Actively investigated by compliance staff.
- `RESOLVED`: Authenticated following supplementary physical/managerial confirmation.
- `REJECTED`: Disallowed or confirmed unauthorized access incident.
- `NO_ACTION`: Recorded for audit history without disciplinary action.

---

## 5. Security & Ethics Statement

- **Attribution is not equivalent to intent**: The prototype functions as an accountability-support tool, not an automated disciplinary system.
- **No Automatic Accusation**: Ambiguous or conflicting signals mandate human oversight.
- **Synthetic Data**: All identities, patient records, and logs are 100% synthetic.
- **Explainability**: Every decision is auditable with transparent point breakdowns and missing-signal logs.
