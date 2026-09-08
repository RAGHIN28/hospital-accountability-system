# Shared-Account Elimination Workflow Using Accountable Delegation and Session Attribution for a Hospital

> **Milestone 1 (35% Proof-of-Concept)**  
> A working cybersecurity proof of concept designed to eliminate identity ambiguity caused by shared hospital accounts (e.g. `radiology_shared`, `lab_shared`, `pharmacy_shared`, `billing_shared`, `ward_shared`, `admin_shared`) through accountable shift delegation, session attribution, and multi-signal network evidence correlation.

---

## 🌐 Localhost Access Links

The full-stack application (FastAPI backend + Interactive Security Operations Center UI) is currently running locally:

- **Dashboard UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000) or [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Attribution Metrics Endpoint**: [http://127.0.0.1:8000/api/attribution/metrics](http://127.0.0.1:8000/api/attribution/metrics)
- **Health Check Endpoint**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## 1. Problem Statement

Hospital environments frequently deploy shared departmental accounts on clinical workstations to facilitate rapid handoffs:
- `radiology_shared` (PACS / RIS)
- `lab_shared` (Laboratory Information System)
- `pharmacy_shared` (Drug Dispensing)
- `billing_shared` (Revenue & Settlement)
- `ward_shared` (Inpatient Nursing EMR)
- `admin_shared` (Systems Infrastructure)

When sensitive actions occur (e.g. viewing electronic Protected Health Information [ePHI], altering medical records, modifying lab values, or altering prescriptions), audit logs record only the shared account name, leaving no legal or administrative proof of which human identity performed the action.

This project introduces an **Accountable Delegation and Session Attribution Pipeline** that correlates shift delegation windows, session bindings, device fingerprints, and network subnets to attribute privileged actions to individual human identities with calibrated confidence and full audit explainability.

---

## 2. Actual Measured Results (35% Prototype)

The following metrics were computed directly on the synthetic hospital dataset of 364 system events:

| Metric | Baseline Method | Prototype Multi-Signal Engine | Delta / Improvement |
| :--- | :--- | :--- | :--- |
| **Total System Events** | 364 | 364 | — |
| **Sensitive Clinical Actions** | 205 | 205 | — |
| **Attributed Actions** | 90 | **203** | **+113 actions resolved** |
| **Ambiguous Actions** | 17 | **1** | **-16 ambiguities** |
| **Unattributed Actions** | 98 | **1** | **-97 unhandled** |
| **Attribution Percentage** | **43.90%** | **99.02%** | **+55.12% Net Lift** |

### Failure / Ambiguity Breakdown
- **Multiple Authorized Users (Equal Evidence)**: 1 event (e.g. overlapping shift without biometric/distinct device confirmation).
- **Expired Authorization**: 1 event (rogue/off-shift access attempt at 03:15 AM outside authorized shift).

---

## 3. Architecture & Attribution Logic

```
SYSTEM LOG EVENT
       ↓
[Event Validation & SHA-256 Fingerprint]
       ↓
[Duplicate Event Detection]
       ↓
[Candidate User Generation]
       ↓
   ┌───────────────────────┴───────────────────────┐
   ↓                                               ↓
[Baseline Method]                      [Prototype Multi-Signal Engine]
- Shift-count only                     - Delegation Match (+40 pts)
- Exactly 1 user -> Attributed         - Session Token Binding (+30 pts)
- >1 user -> AMBIGUOUS                 - Device Station Match (+15 pts)
- 0 users -> UNATTRIBUTED              - IP Subnet Match (+10 pts)
                                       - Department Match (+5 pts)
   └───────────────────────┬───────────────────────┘
                           ↓
              [Calibrated Confidence Tier]
              - High: 80 - 100
              - Medium: 60 - 79
              - Low: 40 - 59
              - Unattributed/Ambiguous: < 40 or close tie (< 10 pts)
                           ↓
              [Auditable Database Persistence]
                           ↓
          [FastAPI REST API & SOC Web Dashboard]
```

---

## 4. Quick Start Guide

### Prerequisites
- Python 3.11+
- Windows PowerShell or Unix Shell

### Step 1: Clone / Navigate to Project Directory
```powershell
cd "r:/COE PROJECT"
```

### Step 2: Set Up Python Virtual Environment & Dependencies
```powershell
python -m venv backend/.venv
& "backend/.venv/Scripts/pip.exe" install -r backend/requirements.txt
```

### Step 3: Initialize Database & Generate Synthetic Hospital Data
```powershell
& "backend/.venv/Scripts/python.exe" scripts/generate_data.py
```
*This command creates the SQLite database `data/hospital_attribution.db`, populates 18 users, 6 shared accounts, 10 privileged action types, 25+ shift delegations, and ingests 364 system log events through the attribution pipeline. It also exports CSV backups to `data/`.*

### Step 4: Run the Automated Test Suite (11/11 Passing)
```powershell
& "backend/.venv/Scripts/pytest.exe" tests/test_attribution.py -v
```

### Step 5: Start the Local Server
```powershell
& "backend/.venv/Scripts/uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000
```
*Open your browser and navigate to **[http://127.0.0.1:8000](http://127.0.0.1:8000)** to view the Security Operations Center dashboard.*

---

## 5. Core REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | GET | Healthcheck and system counts (users, logs) |
| `/api/users` | GET | Hospital user roster with role and department filters |
| `/api/shared-accounts`| GET | Inventory of shared clinical accounts with risk levels and active staff |
| `/api/delegations` | GET | Shift delegation authorizations |
| `/api/privileged-actions` | GET | Catalog of sensitive ePHI actions |
| `/api/logs` | GET | Filterable system logs with pagination and sensitivity flags |
| `/api/attribution/results` | GET | Query attribution results with method and confidence filters |
| `/api/attribution/metrics` | GET | Comparative metrics (Baseline vs Prototype, failure reasons) |
| `/api/attribution/{event_id}`| GET | Deep inspection: candidate scores, evidence matrix, explanation |
| `/api/process-events` | POST | Trigger execution of attribution pipeline on unhandled events |

---

## 6. Security and Ethics Notice

> [!CAUTION]
> **Important Ethical and Clinical Safety Context:**
> - **100% Synthetic Data**: All employee identities, patient identifiers (`SYN-PAT-xxxx`), and clinical logs are entirely synthetic. No real employee PII, patient records, or credentials were used or gathered.
> - **No Password Interception**: The system works on audit metadata, delegation schedules, and session headers. It does not harvest passwords or bypass clinical safety controls.
> - **No Medical Decision-Making**: This prototype functions exclusively as an access governance and audit traceability system. It does not make medical diagnoses or clinical treatment decisions.
> - **Probabilistic Attribution Disclaimer**: Attribution results are evidence-based forensic indicators and do not constitute absolute proof of intentional misconduct.
> - **Production Requirements**: Enterprise deployment would require integration with certified Identity Providers (e.g. SAML/OIDC, Active Directory/LDAP), zero-trust network brokers, encryption at rest/in-transit (FIPS 140-3), and institutional IRB/HIPAA compliance review.

---

## 7. What Remains for the Next 65%

- [ ] Real-time SIEM event streaming via Syslog / Kafka / Webhook receivers.
- [ ] Enterprise SSO & SAML 2.0 / OIDC identity federation.
- [ ] Automated delegation request and manager sign-off workflow (Self-Service Portal).
- [ ] Behavioral anomaly detection (e.g. unusual access hours, sudden volume spike).
- [ ] Direct EHR integration (HL7 FHIR / SMART-on-FHIR clinical event hooks).
- [ ] Role-based access control (RBAC) with granular security officer permissions.
- [ ] Exportable forensic compliance PDF audit reports (HIPAA § 164.312(b) compliance).
