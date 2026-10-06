# Persistent Human Adjudication State Specification

> **Project**: Hospital Shared-Account Elimination & Accountable Action Attribution PoC  
> **Milestone**: Review 3 — Work Package R3.3: Persistent Human Adjudication State  
> **Modules**: `src/adjudication_persistence.py`, `backend/app/models/adjudication.py`, `dashboard/app.py`  
> **Storage Layer**: SQLite / SQLAlchemy (`human_adjudications` table)  
> **Status**: Verified & Passing (20/20 Persistence Tests / 156 Total Suite Tests)  

---

## 1. Problem Statement & Motivation

### Previous In-Memory State Limitations
In earlier iterations of the Streamlit dashboard, human compliance review decisions were ephemeral:
- Decisions submitted via the Compliance Forensic Inspector UI resided purely in Streamlit temporary widgets or mock success notifications.
- When an analyst switched dashboard tabs, refreshed the browser, initiated a Streamlit rerun, or restarted the application server, all recorded human review judgments, assigned reviewers, and compliance notes were completely wiped.
- Post-incident forensic investigations could not rely on unpersisted compliance determinations, creating a critical gap between automated machine attribution and formal human-in-the-loop governance.

### Architectural Solution: R3.3 Persistent Human Adjudication
Review 3 Work Package R3.3 replaces ephemeral UI states with an **ACID-compliant persistent application layer** directly integrated into the SQLite database architecture:
1. **Persistent SQLite Storage**: Dedicated `human_adjudications` table with relational foreign-key integrity to clinical events.
2. **Survives All UI & Server Lifecycles**: Survives Streamlit widget reruns, browser refreshes, cross-tab navigation, and full application restarts.
3. **Audit Trail Linkage**: Every adjudication creation or amendment is automatically appended to the SHA-256 tamper-evident cryptographic hash chain (`src/audit_chain.py`).
4. **Forensic Package Auto-Resolution**: The Forensic Compliance Audit Package Generator (`src/forensic_package.py`) automatically queries and embeds authoritative persisted adjudication state into generated JSON and PDF packages.

---

## 2. Database Model & Schema Architecture

The persistent state is modeled in SQLAlchemy via `backend/app/models/adjudication.py` and mapped to the `human_adjudications` SQLite table:

```sql
CREATE TABLE human_adjudications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id VARCHAR(50) NOT NULL UNIQUE,
    event_id VARCHAR(50) NOT NULL,
    decision VARCHAR(50) NOT NULL,
    reviewer VARCHAR(100) NOT NULL,
    findings TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'SUBMITTED',
    evidence_reference VARCHAR(255),
    version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(event_id) REFERENCES system_logs(event_id)
);

CREATE INDEX ix_human_adjudications_case_id ON human_adjudications(case_id);
CREATE INDEX ix_human_adjudications_event_id ON human_adjudications(event_id);
```

### Field Descriptions & Constraints

| Field | Type | Constraint | Description |
|---|---|---|---|
| `id` | `INTEGER` | Primary Key, Indexed | Auto-incrementing internal record ID |
| `case_id` | `VARCHAR(50)` | Unique, Not Null, Indexed | Unique incident case identifier (e.g. `ESC-2026-0001`) |
| `event_id` | `VARCHAR(50)` | Not Null, Indexed, FK | References clinical event in `system_logs.event_id` |
| `decision` | `VARCHAR(50)` | Not Null | Approved adjudication decision enum |
| `reviewer` | `VARCHAR(100)` | Not Null | Authorized reviewer persona/identity |
| `findings` | `TEXT` | Not Null, Max 5000 chars | Compliance findings, rationale, and physical audit notes |
| `status` | `VARCHAR(30)` | Not Null | Lifecycle state (`SUBMITTED`, `AMENDED`, `RESOLVED`, `UNDER_REVIEW`, `REOPENED`) |
| `evidence_reference` | `VARCHAR(255)` | Nullable | Pointer to physical evidence (badge log tap, sign-in sheet, camera timestamp) |
| `version` | `INTEGER` | Not Null, Default 1 | Monotonically increasing revision counter for amendments |
| `created_at` | `DATETIME` | Not Null | UTC timestamp of initial adjudication creation |
| `updated_at` | `DATETIME` | Not Null | UTC timestamp of most recent amendment |

---

## 3. Decision Taxonomy & Business Rules

Allowed decisions preserve and enforce the canonical compliance review taxonomy defined in `docs/error_handling.md`:

| Decision | Intended Operational Meaning | Machine Impact |
|---|---|---|
| `CONFIRM_IDENTITY` | Compliance officer has verified identity via out-of-band evidence (badge tap, witness log, supervisor roster). | Confirms candidate identity for downstream compliance records. |
| `MARK_UNATTRIBUTED` | Compliance officer concludes insufficient corroboration exists to reliably identify an individual. | Preserves un-attributed state; prevents speculative blame. |
| `REQUEST_MORE_EVIDENCE` | Preliminary review requires additional department records, supervisor statements, or physical access logs. | Retains case in compliance queue for supplementary evidence intake. |
| `DISMISS` | Incident investigated and determined to be an authorized anomaly or administrative false positive. | Resolves escalation case as non-actionable administrative event. |
| `ESCALATE` | High-risk pattern detected; escalated to hospital legal/privacy committee. | Transferred to senior compliance authority. |

---

## 4. Input Validation & Defense-in-Depth

The persistence service (`src/adjudication_persistence.py`) enforces strict validation prior to executing any database operation:

1. **Non-Empty Case ID**: Rejects empty strings, whitespace-only, or `None`.
2. **Clinical Event Verification**: Validates that `event_id` exists in `system_logs`. Non-existent event references raise an explicit `ValueError`.
3. **Decision Whitelist**: Unrecognized decision strings are strictly rejected with an explicit error listing allowed values.
4. **Reviewer Identification**: Empty reviewer strings are rejected; anonymous or unsigned adjudications are forbidden.
5. **Findings Length Cap**: Notes exceeding 5,000 characters are rejected to prevent buffer bloat and denial-of-service conditions.
6. **Transaction Atomicity**: All writes execute within explicit try/except blocks. On failure, `session.rollback()` is invoked, ensuring zero partial or corrupt states.
7. **Single Authoritative Record Invariant**: Re-adjudicating an existing `case_id` updates the existing record and increments `version`, preventing conflicting duplicate rows.

---

## 5. Audit Trail Integration

Human adjudication represents a sensitive administrative and compliance action. To ensure non-repudiation and traceability:
- Every successful call to `AdjudicationPersistenceService.save_adjudication()` automatically logs to the SHA-256 tamper-evident cryptographic audit chain (`src/audit_chain.py`).
- Logged actions use `action="HUMAN_REVIEW_CREATE_ADJUDICATION"` or `action="HUMAN_REVIEW_AMEND_ADJUDICATION"`.
- Recorded details capture case ID, decision, version, and reviewer identity.
- Tamper verification (`verify_chain()`) continues to validate with mathematical certainty across all entries.

---

## 6. Streamlit UI Integration (`dashboard/app.py`)

Section 13 (`13. Human Review`) of the Streamlit dashboard provides seamless end-to-end integration:

1. **Authoritative Loading**: On case selection, the console queries `AdjudicationPersistenceService.get_adjudication_by_case(selected_case_id)`.
2. **Visual Status Banner**:
   - If persisted: Renders a green verification banner displaying the current decision, reviewer, version (`v2`), status, and UTC timestamp.
   - If unadjudicated: Displays an informational notice indicating initial review is pending.
3. **Form Pre-Population**: The decision selector and findings text area automatically pre-populate with the persisted state.
4. **Persistence Trigger**: Clicking **Submit & Persist Adjudication** saves the record to SQLite, logs to the cryptographic audit trail, and triggers an immediate `st.rerun()`.
5. **Forensic Package Sync**: The Forensic Package Export buttons immediately produce JSON and PDF packages containing the newly persisted adjudication.
6. **Facility-Wide Ledger View**: A dedicated table displays all persisted adjudication records currently held in SQLite across all hospital incidents.

---

## 7. Security, Privacy & Non-Overclaiming

### Secret Exclusion Guarantee
- Adjudication records store only compliance metadata, review findings, and synthetic staff references.
- No passwords, API keys, bearer tokens, or cryptographic private keys are accepted, stored, or exposed.

### PoC Limitations & Scope Boundary
> **Academic Proof-of-Concept Boundary**:
> - This implementation runs on local SQLite and is designed for academic demonstration and research benchmarking.
> - This system is **not** certified under HIPAA Security Rule (45 CFR § 164.312), FDA 21 CFR Part 11, or ISO 27001.
> - Human adjudication represents simulated administrative review in an academic prototype and does not constitute legally binding identity certification.
