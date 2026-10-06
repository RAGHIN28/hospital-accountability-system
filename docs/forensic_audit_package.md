# Forensic Compliance Audit Package Specification

> **Project**: Hospital Shared-Account Elimination & Accountable Action Attribution PoC  
> **Milestone**: Review 3 — Work Package R3.2: Exportable Forensic Compliance Audit Packages  
> **Module**: `src/forensic_package.py`  
> **Export Formats**: Structured JSON (`.json`) & Compliance-Grade PDF (`.pdf`)  
> **Status**: Verified & Passing (16/16 Package Tests / 136 Total Tests)  

---

## 1. Architecture & Design Rationale

In clinical security environments, post-incident forensic reviews and regulatory compliance audits require transparent, explainable evidence packages. Automated probability scores and opaque decision labels are insufficient when investigating sensitive clinical actions (such as electronic medical record exports, prescription modifications, or patient chart alterations) performed under shared departmental workstation credentials.

The **Forensic Compliance Audit Package Generator** (`src/forensic_package.py`) bridges machine attribution analysis and human compliance adjudication by assembling an immutable, multi-source evidentiary dossier for any specific clinical event or escalation case.

### Core Architectural Invariants:
1. **Evidence-Bounded Assembly**: Only evidence and telemetry actually recorded for the transaction are included. Missing telemetry (e.g. unparsed user-agents or unmapped terminals) is explicitly flagged as `MISSING` rather than hallucinated or inferred.
2. **Deterministic Evidence Scoring**: Scoring reflects the exact weights implemented by the prototype engine:
   - Active Shift Delegation: up to +40 pts
   - Terminal Session Binding: up to +30 pts
   - Workstation Device Station Match: up to +15 pts
   - Network IP Subnet CIDR Compatibility: up to +10 pts
   - Department Roster Alignment: up to +5 pts
   - Total Maximum: 100.0 pts (Decision threshold: 60.0 pts)
3. **Non-Forcing Ambiguity Preservation**: Ambiguous events with close candidate scores ($\le 5$ pts) preserve all candidate dossiers and route to compliance escalation without forced identity selection.
4. **Append-Only Tamper-Evident Verification**: Every audit package integrates with the SHA-256 cryptographic hash chain (`src/audit_chain.py`), verifying that the recorded event has not undergone historical database tampering.
5. **Zero-Secret Export Guarantee**: Output packages are purged of database connection strings, passwords, private cryptographic keys, and internal filesystem paths.

---

## 2. Package Schema & 12 Mandatory Sections

The forensic audit package schema consists of twelve mutually exclusive sections designed to satisfy forensic auditability:

```json
{
  "metadata": { ... },
  "event_details": { ... },
  "candidate_identity": { ... },
  "evidence_breakdown": { ... },
  "delegation_evidence": { ... },
  "session_evidence": { ... },
  "telemetry_evidence": { ... },
  "chronological_timeline": [ ... ],
  "escalation_details": { ... },
  "audit_chain_verification": { ... },
  "human_review": { ... },
  "limitations_and_disclaimer": { ... }
}
```

### Section Breakdown:

| Section # | Section Name | Description & Key Attributes |
|:---:|:---|:---|
| **1** | **Metadata** | `package_version`, `case_id`, `event_id`, `generated_at` (ISO timestamp), classification level. |
| **2** | **Event Details** | Host timestamp, central arrival watermark, account name, privileged action type, sensitivity tier (`HIGH`, `CRITICAL`), source application, SHA-256 event fingerprint (`raw_event_hash`). |
| **3** | **Candidate Identity** | Attribution status (`ATTRIBUTED`, `AMBIGUOUS`, `UNATTRIBUTED`), method, confidence score (0-100), ranked candidates list, baseline comparison rule outcome. |
| **4** | **Evidence Breakdown** | Granular 5-signal scoring table with maximum weights, achieved points, and qualitative signal strength (`STRONG`, `SUPPORTING`, `MISSING`, `EXPIRED`). |
| **5** | **Delegation Evidence** | Active clinical delegation ID, authorized clinician name/ID, start/end shift bounds, clinical reason, supervisor approver, and revocation/expiry status. |
| **6** | **Session Evidence** | Workstation session token, binding state (`ACTIVE`, `EXPIRED`, `MISSING`), and idle timeout indicators. |
| **7** | **Telemetry Evidence** | Physical workstation terminal ID, source IPv4 address, departmental subnet CIDR, and explicit `MISSING` markings for unparsed telemetry. |
| **8** | **Chronological Timeline** | Strictly ordered chronological event list spanning delegation activation, session logon, action execution, log ingestion, attribution scoring, delegation expiry, and human adjudication. |
| **9** | **Escalation Details** | Escalation case ID, priority tier (`HIGH`, `MEDIUM`), error taxonomy code (`CONFLICTING_DELEGATION`, `EXPIRED_DELEGATION`), queue status, and recommended investigation action. |
| **10** | **Audit Chain Verification**| Linkage into `TamperEvidentAuditTrail`, record ID, previous hash, current block SHA-256 hash, and mathematical tamper validation status (`VERIFIED_VALID`). |
| **11** | **Human Review** | Compliance reviewer persona, formal adjudication decision (`CONFIRM_IDENTITY`, `MARK_UNATTRIBUTED`, `REQUEST_MORE_EVIDENCE`), review timestamp, and investigator notes. |
| **12** | **Limitations & Disclosures**| Mandatory ethical governance notices: synthetic academic data disclosure, non-punitive intent statement, telemetry limits, and non-certification notice. |

---

## 3. Export Formats

### 3.1 Structured JSON Export (`.json`)
- **Default Location**: `results/forensic_packages/<case_id>_forensic_package.json`
- **Encoding**: UTF-8 formatted, two-space indentation (`indent=2`), deterministic key serialization.
- **Consumption Target**: Machine-to-machine SIEM ingestors, external compliance archives, automated verification harnesses.

### 3.2 Publication-Grade PDF Export (`.pdf`)
- **Default Location**: `results/forensic_packages/<case_id>_forensic_package.pdf`
- **Engine**: ReportLab Document Generation Library (`reportlab.platypus.SimpleDocTemplate`).
- **Formatting Standards**:
  - Two-pass `NumberedCanvas` delivering running headers and dynamic `"Page X of Y"` footers.
  - Color-coded compliance status badges (Green for `ATTRIBUTED`, Red for `UNATTRIBUTED` / `ESCALATED`, Amber for `AMBIGUOUS`).
  - Structured, bordered evidence tables for clinical events, candidate rankings, signal breakdowns, and timeline sequences.
  - Formal italicized ethical disclosure and regulatory disclaimer banner on closing page.

---

## 4. Security & Privacy Safeguards

1. **Synthetic Data Hygiene**: All 18 hospital staff members, 6 shared workstation accounts, 26 shift delegations, and 364 system events are synthetically generated. Zero real patient Protected Health Information (PHI) or staff Personally Identifiable Information (PII) is processed or exported.
2. **Credential Sanitization**: The export pipeline explicitly excludes database passwords, private keys, bearer tokens, and session secrets (`test_secret_and_credential_exclusion`).
3. **Read-Only Non-Destructive Execution**: Package generation is strictly read-only; database query counts before and after generation are guaranteed identical (`test_package_generation_leaves_database_state_intact`).

---

## 5. Dashboard Integration Workflow

The forensic package export functionality is integrated directly into the Streamlit compliance console (`dashboard/app.py`):

1. **Navigation**: User navigates to **Section 13: Human Review**.
2. **Case Selection**: In the **Compliance Forensic Inspector**, the officer selects an active incident (e.g., `ESC-2026-0001` corresponding to `EVT-00019`).
3. **Adjudication Input**: The officer selects a simulated decision (`CONFIRM_IDENTITY`, `MARK_UNATTRIBUTED`, etc.) and records compliance review findings.
4. **Export Buttons**:
   - `⬇️ Export JSON Package`: Triggers download of the machine-readable JSON dossier.
   - `⬇️ Export PDF Package`: Triggers download of the multi-page compliance PDF audit report.

---

## 6. Representative Example Use Cases

### Case 1: Unattributed Action with Expired Delegation (`EVT-00019`)
- **Context**: Bulk patient records exported (`EXPORT_PATIENT_RECORD`) on `radiology_shared` workstation at 03:15 AM.
- **Finding**: Top candidate Dr. Priya Menon achieved only 30.0/100 points due to shift delegation expiry at 16:00 previous day.
- **Resolution**: Classified as `UNATTRIBUTED` / `EXPIRED_DELEGATION`, escalated to High-Priority Compliance Queue. PDF package documents missing delegation and recommends shift supervisor interview.

### Case 2: Ambiguous Clinical Action with Competing Staff (`EVT-00115`)
- **Context**: Sensitive laboratory result viewed (`VIEW_PATIENT_RECORD`) on `lab_shared` terminal at 14:15.
- **Finding**: Candidates Meena Joseph and Dinesh Chandran both hold active shift delegations and identical terminal affinity (70.0 pts vs 70.0 pts; margin = 0.0 pts).
- **Resolution**: Engine halts automated assignment; classified as `AMBIGUOUS` / `CONFLICTING_DELEGATION`. Audit package preserves candidate scores and recommends workstation physical sign-in sheet inspection.

### Case 3: High-Confidence Accountable Attribution (`EVT-00001`)
- **Context**: Clinical chart view on `radiology_shared` workstation during day shift.
- **Finding**: Technologist Ravi Kumar matched on active shift delegation (+40), active desktop session (+30), hardware station (+15), subnet (+10), and department (+5) = 100.0 pts.
- **Resolution**: `ATTRIBUTED` (`HIGH` confidence); package records full evidentiary dossier with zero human escalation required.
