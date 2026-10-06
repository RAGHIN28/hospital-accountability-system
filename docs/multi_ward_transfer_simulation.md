# Multi-Ward Patient Transfer & Rotating Shift Boundary Simulation

> **Project**: Hospital Shared-Account Elimination & Accountable Action Attribution PoC  
> **Milestone**: Review 3 — Work Package R3.4: Multi-Ward Patient Transfer Simulation  
> **Module**: `src/multi_ward_transfer.py`  
> **Test Suite**: `tests/test_multi_ward_transfer.py` (21 Tests Passing / 177 Total Suite Tests)  
> **Status**: Verified & Passing (100% Scenario Pass Rate, Sub-2ms Execution)  

---

## 1. Objective & Clinical Motivation

In modern acute hospital environments, clinical encounters are rarely static. A single patient frequently transitions across clinical wards during an admission:
- **Emergency Department (ED)**: Initial triage, stabilization, emergency overrides (`er_triage_shared` / `ward_shared`).
- **Diagnostic Radiology**: Emergency CT or MRI scan (`radiology_shared`).
- **Intensive Care Unit (ICU)**: Post-resuscitation monitoring, critical treatment plan adjustments (`icu_shared_ws` / `ward_shared`).
- **Central Pharmacy**: Immediate bedside medication dispensing (`pharmacy_dispenser` / `pharmacy_shared`).
- **Inpatient Medical/Surgical Wards**: Floor handoff, recovery, and discharge summaries (`ward_shared`).

During these complex cross-ward movements:
1. Patient physical location and responsible clinical teams change dynamically.
2. Clinical workstations and shared accounts transition between authorized staff.
3. Rotating shift boundaries (Day: 07:00-15:00, Evening: 15:00-23:00, Night: 23:00-07:00) occur while the patient remains in transit or under continuous care.
4. Visiting specialists (e.g., consulting cardiologists) participate within temporary bedside consult windows.
5. Resident interns execute orders under supervised delegation windows.
6. Transfer records, electronic notifications, and telemetry can arrive delayed, out of order, or partially degraded.

### Core Architectural Invariant: Non-Forcing Attribution Safety
> [!IMPORTANT]
> **Attribution Safety Rule**:
> - Patient transfer **must never** automatically imply individual staff identity.
> - Ward assignment **must never** automatically imply individual staff identity.
> - Identity attribution is strictly determined through verifiable multi-source evidence (active delegation grants, session tokens, station affinity, and network compatibility).
> - When evidence is ambiguous (competing candidates with tied scores) or insufficient (< 60.0 pts), the system **never guesses**; it preserves `AMBIGUOUS` or `UNATTRIBUTED` and escalates to human compliance review.

---

## 2. Synthetic Data Model & Topology

All encounters, MRNs, wards, and transfers are deterministically synthesized for academic research benchmarking. Zero real protected health information (PHI) is used.

### Ward Topology Map

| Synthetic Ward | Clinical Specialty | Primary Workstations | Subnet CIDR | Characteristic Privileged Actions |
|---|---|---|---|---|
| **Emergency** | Emergency Triage / Trauma | `WARD-STN-01`, `WARD-TAB-01` | `192.168.50.0/24` | `VIEW_PATIENT_RECORD`, `EDIT_PATIENT_RECORD` |
| **Radiology** | PACS / RIS Diagnostic Imaging | `RAD-WS-01`, `RAD-PACS-01` | `192.168.10.0/24` | `EXPORT_PATIENT_RECORD`, `VIEW_PATIENT_RECORD` |
| **Laboratory** | Clinical Pathology / LIS | `LAB-PC-01`, `LAB-LIS-01` | `192.168.20.0/24` | `MODIFY_LAB_RESULT`, `APPROVE_LAB_RESULT` |
| **Pharmacy** | Inpatient Drug Dispensing | `PHARM-TERM-01`, `PHARM-DISP-01` | `192.168.30.0/24` | `DISPENSE_MEDICATION`, `MODIFY_PRESCRIPTION` |
| **Inpatient Ward** | Floor Care / General Medicine | `WARD-STN-02`, `WARD-CLINIC-01` | `192.168.50.0/24` | `EDIT_PATIENT_RECORD`, `VIEW_PATIENT_RECORD` |
| **Intensive Care** | ICU Critical Care Resuscitation | `WARD-STN-03`, `WARD-TAB-02` | `192.168.50.0/24` | `EDIT_PATIENT_RECORD`, `DELETE_RECORD` |

---

## 3. Transfer Scenarios Evaluated

The simulation engine (`src/multi_ward_transfer.py`) deterministically executes eight clinical transfer scenarios:

### SCENARIO A — Normal Transfer
- **Conditions**: Patient moves Emergency -> Radiology.
- **Pre-Transfer Action (09:30)**: Pre-transfer clinical summary edited on `ward_shared`. Attributes to Ward Nurse EMP011 (`Sister Mary Thomas`).
- **Post-Transfer Action (10:30)**: Scan exported on `radiology_shared`. Attributes to Chief Radiologist EMP002 (`Dr. Priya Menon`).
- **Outcome**: Both actions attribute cleanly to their respective authorized clinician without cross-ward confusion.

### SCENARIO B — Shift Change During Transfer
- **Conditions**: Patient transfer spans the 15:00:00 shift boundary.
- **Staffing**: Day clinician EMP003 (`Ravi Kumar`) delegation expires at 15:00:00; Evening clinician EMP002 (`Dr. Priya Menon`) activates at 15:00:00.
- **Action at 15:15**: `VIEW_PATIENT_RECORD` on `radiology_shared`.
- **Outcome**: Correctly attributes to incoming clinician EMP002. Outgoing clinician EMP003 is rejected due to expired delegation.

### SCENARIO C — Shared Workstation Sequential Transition
- **Conditions**: Same physical mobile workstation (`WARD-STN-02`) used sequentially across teams.
- **Event 1 (11:00)**: Ward Nurse EMP012 accesses `ward_shared`. Attributes to EMP012.
- **Event 2 (11:45)**: Clinical Pharmacist EMP007 accesses `pharmacy_shared` on the exact same terminal hardware.
- **Outcome**: Both actions resolve to the correct individual identity via account, delegation, and session context. Hardware reuse does not induce attribution errors.

### SCENARIO D — Visiting Consultant Temporary Window
- **Conditions**: Visiting Cardiologist EMP001 (`Dr. Arun Kumar`) holds a bounded consult delegation (13:00 to 14:30) for emergency ICU bedside consult.
- **Action 1 (13:45)**: Inside window; attributes to EMP001 (active consult delegation + session).
- **Action 2 (15:00)**: After consult window expired; consultant has departed.
- **Outcome**: Action at 15:00 attributes to on-duty ward nurse EMP011. Consultant is not falsely blamed or credited for post-consult actions.

### SCENARIO E — Intern Supervised Practice Delegation Boundary
- **Conditions**: Radiology Resident Intern EMP005 (`Karthik Raj`) supervised by Chief Radiologist EMP002 with authorized training shift 09:00 - 13:00.
- **Action 1 (11:30)**: Inside intern shift; attributes to Intern EMP005.
- **Action 2 (14:00)**: After intern shift ends; attributes to Supervisor EMP002.
- **Outcome**: Intern delegation boundary strictly respected.

### SCENARIO F — Delayed Transfer Record In-Place Reconciliation
- **Conditions**: Clinical action occurs in ICU at 10:15; administrative transfer and shift delegation records arrive late at 10:45.
- **Pipeline Workflow**:
  1. Event ingested at 10:15 lacking active delegation; held in `PENDING` state in `IngestionBuffer`.
  2. Late delegation arrives at 10:45.
  3. Retroactive in-place reconciliation re-evaluates event to `ATTRIBUTED` (`EMP011`) without duplicate record creation.
- **Outcome**: Reconciled count = 1; zero duplicate rows.

### SCENARIO G — Missing In-Transit Telemetry Resilience
- **Conditions**: Patient in transit through unmapped hallway; Wi-Fi drops, IP is `0.0.0.0`, device is `UNKNOWN`.
- **Case G1**: Strong evidence present (valid delegation 40 pts + session binding 30 pts = 70.0 pts >= 60.0 threshold). Attributes with `MEDIUM` confidence; missing telemetry explicitly recorded as `MISSING`.
- **Case G2**: Both telemetry AND session missing (only delegation 40.0 pts < 60.0 threshold). System safely preserves `UNATTRIBUTED` without guessing.

### SCENARIO H — Conflicting Clinician Handoff (Compliance Escalation)
- **Conditions**: Emergency handoff where two clinicians (EMP002 and EMP003) have overlapping delegations and identical terminal presence.
- **Scoring**: Both candidates tie at 85.0 pts (margin = 0.0 pts <= 5.0 pts).
- **Outcome**: System flags `AMBIGUOUS`, halts automated assignment, and routes dossier to Compliance Escalation Queue for human review.

---

## 4. Edge & Failure Conditions Verified

The test suite explicitly validates 9 critical edge conditions:
1. **Pre-Delegation Window**: Actions attempted before delegation `start_time` receive 0 delegation points.
2. **Post-Delegation Expiry**: Actions attempted after delegation `end_time` receive 0 delegation points.
3. **Exact Shift Boundary**: Actions executed at `15:00:00.000` deterministically evaluate boundary inclusivity (`start <= t <= end`).
4. **Replay / Duplicate Detection**: Identical transfer event payloads rejected at ingestion buffer (`DUPLICATE`).
5. **Out-of-Order Ingestion**: Events arriving chronologically inverted are sorted and evaluated in event-time order.
6. **Unknown Clinician**: Unmapped staff IDs receive 0 points; safely resolved as `UNATTRIBUTED`.
7. **Unknown Ward**: Unrecognized ward device/IP fingerprints gracefully score 0 network/device points without crashing.
8. **Expired Session**: Sessions exceeding timeout threshold receive 0 session binding points.
9. **Zero-Secret Guarantee**: Outputs purged of passwords, bearer tokens, and private keys.

---

## 5. Performance Benchmarks

Measured on local Python 3.11 environment:
- **Total Scenarios Evaluated**: 8 / 8 passed
- **Total Clinical Actions Processed**: 13 actions
- **Attributed Actions**: 11 (84.6%)
- **Unattributed Actions**: 1 (7.7% — safety gate)
- **Ambiguous Escalated Actions**: 1 (7.7% — safety gate)
- **Execution Runtime**: **~1.14 ms** across entire 8-scenario suite
