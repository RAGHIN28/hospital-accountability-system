# Usability Walkthrough & Operator Inspection Guide
**Project Milestone**: Review #2 — 70% Completion Milestone  
**Protocol Type**: Developer Walkthrough / Simulated Usability Validation  
**Disclaimer**: This validation was conducted by system developers using simulated hospital compliance officer personas and 100% synthetic hospital data. No real human subjects, patients, or hospital staff were involved; no fabricated user satisfaction scores are reported.

---

## 1. Start Application
Launch the compliance review dashboard locally from the project root using the designated virtual environment:
```powershell
& "backend/.venv/Scripts/streamlit.exe" run dashboard/app.py --server.port 8501
```
Navigate in any modern web browser to `http://localhost:8501`. Verify that the dashboard header reads:
> **🏥 Hospital Accountability System — Shared-Account Attribution & Compliance Review Console (Review #2 — 70% Milestone)**

Select the operational persona in the left sidebar:
- Select **Compliance Officer** or **Student / Reviewer**.

---

## 2. Open Attribution Overview (Section 1)
1. Select **1. Attribution Overview** from the left navigation panel.
2. Confirm the top-level KPIs:
   - **Total System Events**: `364`
   - **Sensitive Actions**: `205`
   - **Baseline Attribution**: `43.9%`
   - **Prototype Attribution**: `99.02%`
   - **Net Lift**: `+55.12%`
3. Inspect the **Formal Compliance Officer Workflow** diagram illustrating the deterministic separation between automated high-confidence attributions (203 actions) and the human-in-the-loop escalation queue (2 actions).
4. Review the live adjudication breakdown table at the bottom of the section.

---

## 3. Select a Sensitive Action & Baseline Comparison (Section 2)
1. Navigate to **2. Baseline vs Prototype**.
2. Examine the comparative table contrasting the naive shift-assignment rule with the prototype multi-signal engine.
3. Observe why the simple baseline drops to 43.90%: whenever multiple clinicians share a shift on a department terminal, the baseline marks the transaction ambiguous.
4. Review the bar chart detailing attribution lift across high-risk clinical action categories (e.g., `DISPENSE_NARCOTICS`, `ADMINISTER_MEDICATION`, `OVERRIDE_DOSAGE_ALERT`).

---

## 4. Inspect Evidentiary Dossier (Section 9)
1. Navigate to **9. Evidence / Explainability**.
2. Review the structured **Explainable Evidence Dossier** schema.
3. Verify that the dossier explicitly categorizes evidence into 5 distinct tiers:
   - `STRONG`: Temporal validity window match against an active delegation + user roster active status.
   - `SUPPORTING`: Terminal session state within 30-minute idle threshold, subnet CIDR match, device fingerprint match.
   - `MISSING`: Optional network telemetry absent or unrecorded.
   - `CONFLICTING`: Concurrent active delegations or overlapping sessions on the same account.
   - `INSUFFICIENT`: Candidate not present in hospital personnel directory.
4. Note that attribution confidence is rule-based and deterministic—never opaque ML weights or uncalibrated probabilities.

---

## 5. Inspect Delegation Lifecycle (Section 3)
1. Select **3. Delegation Lifecycle**.
2. Examine the state transition diagram: `CREATED -> ACTIVE -> EXPIRED / REVOKED / CANCELLED`.
3. Verify the temporal boundary rules:
   - An event occurring at `08:59:59` against a delegation starting at `09:00:00` is rejected with `EXPIRED_DELEGATION` / `NOT_YET_ACTIVE`.
   - Actions occurring during an active window retain full attribution history even after the shift later expires.

---

## 6. Inspect Session Lifecycle (Section 4)
1. Navigate to **4. Session Lifecycle**.
2. Inspect the workstation session state machine: `CREATED -> ACTIVE -> IDLE -> EXPIRED / TERMINATED`.
3. Confirm the default prototype timeout parameter:
   - Inactivity timeout is set to `30 minutes`.
   - Any sensitive transaction resets the rolling activity timestamp.
   - Transactions recorded >30 minutes after last activity without a re-authentication badge trigger an operational alert.

---

## 7. Inspect Supporting Telemetry & Stress Degradation (Section 10)
1. Navigate to **10. Telemetry Stress**.
2. Examine the measured degradation curve (`results/figures/telemetry_degradation_curve.png`).
3. Note that as telemetry availability degrades from 100% to 0%:
   - Attribution drops from 99.02% (203 actions) to 36.10% (74 unambiguous actions with strong tokens/delegations).
   - The remaining 131 actions (63.90%) that required telemetry corroboration are safely escalated to human review.
   - Identity is **never fabricated** or guessed based on missing telemetry.
   - Zero false-positive identities are assigned.

---

## 8. Inspect Ambiguity & Delegation Conflicts (Section 16 & Section 11)
1. Navigate to **16. Scenario Validation**.
2. Review **Scenario 5**: Conflicting Overlapping Delegations (`SCENARIO-05`).
   - Input: Dr. Sarah Lin (`U002`) and Dr. Mark Reed (`U007`) both hold active delegations on `er_triage_shared` from 14:00 to 18:00. An emergency order is executed at 15:30 with identical telemetry.
   - Engine Action: Identifies candidate set `[U002, U007]`. Refuses to guess. Classifies state as `AMBIGUOUS` with conflict flag. Emits `ALT-002` and opens `CASE_2026_002` in the escalation queue.

---

## 9. Open Escalation Queue & Incident Triage (Section 13)
1. Navigate to **13. Human Review**.
2. Inspect the **Active Escalation Queue** showing 2 unresolved incidents.
3. Select `CASE_2026_001` or `CASE_2026_002` in the **Compliance Forensic Inspector** dropdown.
4. Review the candidate users, root cause category, and automated recommendation (e.g., `"Interview shift supervisor or inspect physical floor badge logs"`).

---

## 10. Inspect Human-Review Adjudication
1. In the **Compliance Forensic Inspector** for the selected case:
   - Select the simulated adjudication decision: `CONFIRM_IDENTITY`, `MARK_UNATTRIBUTED`, `REQUEST_MORE_EVIDENCE`, `DISMISS`, or `ESCALATE`.
   - Enter compliance officer review notes (e.g., `"Physical sign-in log verified Dr. Sarah Lin was stationed at ER bed 3 at 15:30"`).
   - Click **Submit Adjudication**.
2. Confirm the success notification: the adjudication decision is recorded and committed to the tamper-evident audit trail.

---

## 11. Verify Tamper-Evident Audit Chain (Section 14)
1. Navigate to **14. Audit Chain Verification**.
2. Review the live cryptographic audit chain.
3. Observe the SHA-256 previous-hash and record-hash linkage across all events.
4. Click **Simulate Tamper on Block #1** to observe tamper detection:
   - The chain verification engine immediately detects the modified payload and reports a broken hash mismatch at Block #1.

---

## 12. Inspect Scaled Performance & Data Quality (Sections 15 & 17)
1. Navigate to **15. Performance**.
   - Review the empirical throughput benchmarks across workloads from 1,000 to 50,000 events.
   - Confirm peak ingestion throughput of **17,737 events/second**.
2. Navigate to **17. Project Completion**.
   - Verify the transparent requirement completion matrix:
     - **Verified Requirement Coverage**: **91.15%** (Requirement Gate: $\ge 70.00\%$, Status: **PASS**).
     - Confirms explicit separation between requirement coverage (91.15%) and attribution accuracy (99.02%).
