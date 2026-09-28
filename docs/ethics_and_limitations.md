# Ethics, Evidentiary Boundaries & System Limitations
**Project**: Hospital Shared-Account Elimination & Accountable Action Attribution  
**Milestone**: Project Review #2 — 70% Completion Milestone  
**Authors**: Academic Research & Development Team  
**System Purpose**: Technical Proof-of-Concept for Shared-Account Auditing

---

## 1. Core Ethical Tenets & Evidentiary Declarations

This system is an academic proof-of-concept designed to investigate methods for eliminating accountability voids on shared clinical workstations. The operation and evaluation of this system are strictly bounded by the following ten mandatory ethical principles:

1. **Attribution Is Not Proof of Intent**:
   The attribution of a sensitive action to a specific clinician establishes only that the clinician's credentials, active shift delegation, and workstation session were temporally correlated with the event. It does not establish clinical malice, criminal culpability, or intentional misconduct.

2. **Investigative Support, Not Automated Adjudication or Punishment**:
   Machine attribution outputs must serve solely as investigative aids for human compliance officers and clinical department heads. The software is strictly forbidden from triggering automatic disciplinary actions, employment sanctions, or professional credential revocations.

3. **Total Evidentiary Transparency (No Concealment)**:
   Missing, degraded, or conflicting evidence must remain explicitly exposed in the evidence dossier (`src/evidence_model.py`) and compliance dashboard. The engine never conceals uncertainty to artificially inflate attribution statistics.

4. **Mandatory Human-in-the-Loop Review for Ambiguous Transactions**:
   Any action featuring conflicting active delegations, overlapping workstation sessions, or absent personnel records must halt automated resolution and route directly to the human escalation queue (`src/escalation_service.py`).

5. **Telemetry Is Supporting Context, Not Identity Proof**:
   Workstation IP addresses, subnet CIDRs, user-agent headers, and browser fingerprints constitute supporting network telemetry. They are susceptible to DHCP re-assignments, proxying, and client spoofing. Telemetry alone must **never** be used to assert or alter clinician identity.

6. **100% Synthetic Data Architecture**:
   All 18 clinician records, 6 department accounts, 26 shift delegations, and 364 system log entries are deterministically generated synthetic constructs. No real hospital staff members are referenced or represented.

7. **Zero Protected Health Information (PHI)**:
   No real patient data, medical records, diagnoses, prescription records, or demographic data are utilized or stored within this repository.

8. **Zero Live Hospital Integration**:
   The system operates entirely in local Python/SQLite memory. It is not connected to any clinical hospital EHR/EMR (e.g., Epic, Cerner), PACS network, pharmacy dispensing cabinet (e.g., Pyxis), or active directory service.

9. **No Production Compliance Certification**:
   The metrics and results documented in this project (including the 99.02% attribution rate and 91.15% requirement coverage) represent empirical measurements within a synthetic laboratory environment. They must not be interpreted as HIPAA Security Rule certification, 21 CFR Part 11 validation, or clinical SOC 2 attestation.

10. **Human Oversight Required for All Consequential Decisions**:
    Any consequential action impacting clinician rights, legal liability, patient care reviews, or institutional audit findings requires rigorous independent investigation and formal human officer sign-off.

---

## 2. Technical & Architectural Limitations

### 2.1 Scope of the Proof of Concept
- **Synthetic Clock Simulation**: Clinical shift times and event arrival sequences are modeled using simulated datetime offsets rather than real-time hardware clocks.
- **Local Single-Node Execution**: Ingestion buffers, priority queues, and audit chains run locally in Python 3.11. Distributed clustering, consensus protocols (Raft/Paxos), and multi-datacenter replication are omitted by design.
- **Simulated Human Adjudication**: Compliance officer reviews in the demonstration console simulate the workflow of hospital risk managers; they do not represent real hospital staff user experience testing.

### 2.2 Telemetry Vulnerabilities
While the multi-signal attribution pipeline dramatically improves attribution over naive baselines (+55.12% lift), the following telemetry failure states remain documented:
- **Fast Physical Relays**: If Clinician A walks away from an unlocked terminal without badge logout and Clinician B performs an action within the 30-minute idle window, automated attribution will initially assign the action to Clinician A. Resolving this physical shoulder-surfing vulnerability requires physical smartcard lanyards or biometrics, which are outside the software scope of this PoC.
- **NAT / Shared Subnet Collocation**: When multiple workstations operate behind a shared clinical departmental NAT gateway, IP-based corroboration drops to subnet-level precision.
