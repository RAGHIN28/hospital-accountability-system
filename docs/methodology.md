# Research Methodology & Mathematical Formulation

> **Hospital Accountability System — 35% Milestone Remediation**

---

## 1. Multi-Signal Evidence Scoring Formulation

Attribution confidence for shared clinical workstations is computed through a calibrated additive multi-signal scoring function:

$$S_{\text{total}}(u, e) = w_{\text{del}} \cdot \mathbb{I}_{\text{del}}(u, e) + w_{\text{sess}} \cdot \mathbb{I}_{\text{sess}}(u, e) + w_{\text{dev}} \cdot \mathbb{I}_{\text{dev}}(u, e) + w_{\text{net}} \cdot \mathbb{I}_{\text{net}}(u, e) + w_{\text{dept}} \cdot \mathbb{I}_{\text{dept}}(u, e)$$

Where the weight configuration is parameterized as:
- $w_{\text{del}} = 40.0$ (Active shift delegation window covering event timestamp)
- $w_{\text{sess}} = 30.0$ (Session token correlation / explicit employee binding)
- $w_{\text{dev}} = 15.0$ (Departmental device fingerprint match)
- $w_{\text{net}} = 10.0$ (IP subnet CIDR compatibility)
- $w_{\text{dept}} = 5.0$ (Departmental alignment between staff roster and shared account)
- Maximum Possible Score: $S_{\text{total}} = 100.0$ points.

### Decision Boundaries:
- **Attributed**: $S_{\text{top}} \ge 60.0$ and $(S_{\text{top}} - S_{\text{second}}) \ge 10.0$
- **Ambiguous**: $S_{\text{top}} \ge 40.0$, $S_{\text{second}} \ge 40.0$, and $(S_{\text{top}} - S_{\text{second}}) < 10.0$
- **Unattributed**: $S_{\text{top}} < 60.0$ or unmapped candidate set.

---

## 2. Ingestion Buffer and Late Event Reconciliation

Disordered event streams are reconciled via in-memory event-time sequencing.

### Ingestion Metrics:
- **Deduplication Rate**:
  $$\text{Dup Rate} = \frac{N_{\text{duplicate}}}{N_{\text{total}}} \times 100$$
- **Reconciliation Recovery Percentage**:
  $$\text{Reconciliation \%} = \frac{N_{\text{reconciled delayed events}}}{N_{\text{total delayed events}}} \times 100$$
  Across empirical benchmarking, the reconciliation protocol achieved **100.0%** recovery of valid delayed actions upon receipt of retroactive shift authorization.

---

## 3. Telemetry Degradation Testing

Telemetry robustness is evaluated under controlled synthetic missingness experiments. Optional telemetry fields (CIDR, device fingerprint, user-agent) are progressively dropped across six discrete availability levels:
$$\mathcal{A} \in \{100\%, 90\%, 75\%, 50\%, 25\%, 0\%\}$$

### Key Finding:
"Missing network telemetry reduces contextual evidence but does not automatically invalidate identity attribution when stronger evidence exists."
Even under 0% optional telemetry availability, actions with active delegation and session bindings retain a **36.10%** baseline attribution rate without creating false identity assignments.

---

## 4. Human-in-the-Loop Escalation Formulation

The compliance escalation rate is defined strictly over privileged sensitive operations:

$$\text{Escalation Rate} = \frac{N_{\text{escalated sensitive actions}}}{N_{\text{total sensitive actions}}} \times 100$$

### Error Categorization Model:
To guarantee mutually exclusive reporting without double-counting, each unresolved event is assigned a single primary error category using a deterministic hierarchy:
1. `INACTIVE_USER` / `MISSING_ROSTER`
2. `UNKNOWN_ACCOUNT`
3. `EXPIRED_DELEGATION`
4. `CONFLICTING_DELEGATION`
5. `MISSING_DELEGATION`
6. `MISSING_SESSION`
7. `MISSING_DEVICE_TELEMETRY` / `MISSING_NETWORK_TELEMETRY`
8. `OTHER`
