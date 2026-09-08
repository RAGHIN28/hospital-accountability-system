// Hospital SOC Shared-Account Attribution Dashboard Logic
const API_BASE = "/api";

// State
let appMetrics = null;
let currentTab = "dashboard";

// Initialize on DOM Load
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupEventListeners();
  loadAllData();
});

// Setup Navigation Tabs
function setupNavigation() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const tabId = btn.getAttribute("data-tab");
      currentTab = tabId;
      const targetPane = document.getElementById(`tab-${tabId}`);
      if (targetPane) targetPane.classList.add("active");

      // Reload specific data if needed
      if (tabId === "shared-accounts") loadSharedAccounts();
      if (tabId === "events") loadEvents();
      if (tabId === "comparison") loadComparisonData();
      if (tabId === "users") loadUsersAndDelegations();
    });
  });
}

// Setup Event Listeners
function setupEventListeners() {
  document.getElementById("btn-reprocess")?.addEventListener("click", reprocessEvents);
  document.getElementById("btn-apply-filters")?.addEventListener("click", loadEvents);
  document.getElementById("btn-close-modal")?.addEventListener("click", closeModal);
  document.getElementById("event-detail-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "event-detail-modal") closeModal();
  });
}

// Initial Data Load
async function loadAllData() {
  await loadMetrics();
  await loadSharedAccounts();
  await loadEvents();
}

// 1. Fetch & Render Metrics
async function loadMetrics() {
  try {
    const res = await fetch(`${API_BASE}/attribution/metrics`);
    if (!res.ok) throw new Error("Failed to load metrics");
    const data = await res.json();
    appMetrics = data;

    // Fetch total users and shared accounts count
    const healthRes = await fetch(`${API_BASE}/health`);
    const health = await healthRes.json();

    document.getElementById("metric-users").innerText = health.total_users || 18;
    document.getElementById("metric-total-events").innerText = data.total_events;
    document.getElementById("metric-sensitive-actions").innerText = data.total_sensitive_actions;
    document.getElementById("metric-baseline-pct").innerText = `${data.baseline_attribution_percentage}%`;
    document.getElementById("metric-prototype-pct").innerText = `${data.prototype_attribution_percentage}%`;
    document.getElementById("metric-improvement-pct").innerText = `+${data.improvement_percentage}%`;

    // Progress Bars
    document.getElementById("bar-base-text").innerText = `${data.baseline_attribution_percentage}%`;
    document.getElementById("bar-base-fill").style.width = `${data.baseline_attribution_percentage}%`;
    document.getElementById("base-attr-cnt").innerText = data.baseline_attributed;
    document.getElementById("base-amb-cnt").innerText = data.baseline_ambiguous;
    document.getElementById("base-unattr-cnt").innerText = data.baseline_unattributed;

    document.getElementById("bar-proto-text").innerText = `${data.prototype_attribution_percentage}%`;
    document.getElementById("bar-proto-fill").style.width = `${data.prototype_attribution_percentage}%`;
    document.getElementById("proto-attr-cnt").innerText = data.prototype_attributed;
    document.getElementById("proto-amb-cnt").innerText = data.prototype_ambiguous;
    document.getElementById("proto-unattr-cnt").innerText = data.prototype_unattributed;

    // Render Failure Reasons
    const failureContainer = document.getElementById("failure-reasons-container");
    failureContainer.innerHTML = "";
    const reasons = Object.entries(data.failure_reasons || {});
    if (reasons.length === 0) {
      failureContainer.innerHTML = `<div class="text-dim">No attribution failures recorded.</div>`;
    } else {
      reasons.forEach(([reason, count]) => {
        const item = document.createElement("div");
        item.className = "failure-item";
        item.innerHTML = `
          <span>${reason}</span>
          <span class="failure-count">${count} events</span>
        `;
        failureContainer.appendChild(item);
      });
    }

    // Render Confidence Chips
    const confContainer = document.getElementById("confidence-chips-container");
    confContainer.innerHTML = "";
    Object.entries(data.confidence_distribution || {}).forEach(([lvl, count]) => {
      const chip = document.createElement("div");
      chip.className = "conf-chip";
      const colorClass = lvl === "HIGH" ? "text-green" : (lvl === "MEDIUM" ? "text-emerald" : (lvl === "LOW" ? "text-amber" : "text-red"));
      chip.innerHTML = `
        <span class="font-mono ${colorClass}">● ${lvl}</span>
        <strong>${count}</strong>
      `;
      confContainer.appendChild(chip);
    });

  } catch (err) {
    console.error("Error loading metrics:", err);
  }
}

// 2. Fetch & Render Shared Accounts
async function loadSharedAccounts() {
  try {
    const res = await fetch(`${API_BASE}/shared-accounts`);
    const accounts = await res.json();
    document.getElementById("metric-shared-accounts").innerText = accounts.length;

    const grid = document.getElementById("shared-accounts-grid");
    grid.innerHTML = "";

    accounts.forEach(acc => {
      const riskClass = `badge-risk-${acc.risk_level.toLowerCase()}`;
      const card = document.createElement("div");
      card.className = "account-card";

      const usersList = acc.active_authorized_users && acc.active_authorized_users.length > 0
        ? acc.active_authorized_users.map(u => `<li>&bull; ${u}</li>`).join("")
        : `<li class="text-dim">No active authorized users right now</li>`;

      card.innerHTML = `
        <div class="account-card-header">
          <div>
            <div class="account-name">${acc.username}</div>
            <div class="account-system">${acc.system_name} &bull; ${acc.department}</div>
          </div>
          <span class="badge ${riskClass}">${acc.risk_level} RISK</span>
        </div>

        <div class="account-auth-users">
          <div class="meta-key">Active Delegated Staff (${acc.authorized_users_count})</div>
          <ul>${usersList}</ul>
        </div>

        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-dim);">
          <span>Type: ${acc.account_type}</span>
          <span>Status: <b style="color: var(--green);">${acc.status}</b></span>
        </div>
      `;
      grid.appendChild(card);
    });
  } catch (err) {
    console.error("Error loading shared accounts:", err);
  }
}

// 3. Fetch & Render Events Table
async function loadEvents() {
  try {
    const account = document.getElementById("filter-account")?.value || "";
    const sensitivity = document.getElementById("filter-sensitivity")?.value || "";
    const search = document.getElementById("filter-search")?.value || "";

    let url = `${API_BASE}/logs?limit=100`;
    if (account) url += `&username=${account}`;
    if (search) url += `&action=${search}`;
    if (sensitivity === "sensitive") url += `&is_sensitive=true`;
    if (sensitivity === "non-sensitive") url += `&is_sensitive=false`;

    const [logsRes, resultsRes] = await Promise.all([
      fetch(url),
      fetch(`${API_BASE}/attribution/results?limit=150`)
    ]);

    const logs = await logsRes.json();
    const results = await resultsRes.json();
    const resultMap = {};
    results.forEach(r => { resultMap[r.event_id] = r; });

    const tbody = document.getElementById("events-table-body");
    tbody.innerHTML = "";

    if (logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center text-dim">No events match filter criteria.</td></tr>`;
      return;
    }

    logs.forEach(log => {
      const attr = resultMap[log.event_id];
      const tr = document.createElement("tr");

      const sensBadge = log.is_sensitive
        ? `<span class="badge-sensitive" title="${log.sensitivity_level}">SENSITIVE</span>`
        : "";

      const statusBadge = attr
        ? `<span class="badge badge-${attr.attribution_status.toLowerCase()}">${attr.attribution_status}</span>`
        : `<span class="badge badge-unattributed">PENDING</span>`;

      const confBadge = attr
        ? `<span class="badge-conf-${attr.confidence_level.toLowerCase().substring(0,3)}">${attr.confidence_score.toFixed(0)}% (${attr.confidence_level})</span>`
        : "--";

      const attributedUser = attr?.attributed_user_name
        ? `<b style="color: #38bdf8;">${attr.attributed_user_name}</b>`
        : `<span class="text-dim">Unresolved</span>`;

      const tsFormatted = new Date(log.timestamp).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit"
      });

      tr.innerHTML = `
        <td class="font-mono" style="color: #94a3b8;">${log.event_id}</td>
        <td style="white-space: nowrap;">${tsFormatted}</td>
        <td><strong class="font-mono">${log.username}</strong></td>
        <td>
          <div style="display:flex; align-items:center; gap: 0.4rem;">
            <span>${log.action}</span>
            ${sensBadge}
          </div>
        </td>
        <td class="font-mono text-dim" style="font-size: 0.75rem;">${log.source_ip} / ${log.device_id}</td>
        <td>${attributedUser}</td>
        <td>${confBadge}</td>
        <td><span style="font-size: 0.75rem; color: var(--text-dim);">${attr?.attribution_method || "N/A"}</span></td>
        <td>
          <button class="btn btn-secondary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="openEventDetail('${log.event_id}')">
            Inspect
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error("Error loading events:", err);
  }
}

// 4. Fetch & Render Comparison Table
async function loadComparisonData() {
  try {
    const res = await fetch(`${API_BASE}/logs?is_sensitive=true&limit=100`);
    const logs = await res.json();
    const resultsRes = await fetch(`${API_BASE}/attribution/results?limit=150`);
    const results = await resultsRes.json();
    const resultMap = {};
    results.forEach(r => { resultMap[r.event_id] = r; });

    const tbody = document.getElementById("comparison-table-body");
    tbody.innerHTML = "";

    logs.forEach(log => {
      const attr = resultMap[log.event_id];
      if (!attr) return;

      const tr = document.createElement("tr");
      const tsFormatted = new Date(log.timestamp).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
      });

      // Highlight rows where prototype resolved an ambiguity or unattributed case
      const isImprovement = attr.baseline_status !== "ATTRIBUTED" && attr.attribution_status === "ATTRIBUTED";

      const baseText = attr.baseline_user_name
        ? `<b style="color: var(--green);">${attr.baseline_user_name}</b> (${attr.baseline_confidence.toFixed(0)}%)`
        : `<span class="badge badge-${attr.baseline_status.toLowerCase()}">${attr.baseline_status}</span>`;

      const protoText = attr.attributed_user_name
        ? `<b style="color: #38bdf8;">${attr.attributed_user_name}</b>`
        : `<span class="badge badge-${attr.attribution_status.toLowerCase()}">${attr.attribution_status}</span>`;

      let evidenceSummary = "";
      if (attr.explanation) {
        const lines = attr.explanation.split("\n");
        const evidenceLines = lines.filter(l => l.includes("•"));
        evidenceSummary = evidenceLines.slice(0, 2).map(l => l.trim()).join(", ");
        if (!evidenceSummary && lines[0]) evidenceSummary = lines[0].substring(0, 80);
      }

      tr.innerHTML = `
        <td class="font-mono">${log.event_id}</td>
        <td>${tsFormatted}</td>
        <td><strong class="font-mono">${log.username}</strong></td>
        <td><strong>${log.action}</strong></td>
        <td>${baseText}</td>
        <td>${protoText} ${isImprovement ? '<span class="badge badge-attributed" style="font-size:0.65rem;">RESOLVED</span>' : ''}</td>
        <td><span class="badge-conf-${attr.confidence_level.toLowerCase().substring(0,3)}">${attr.confidence_score.toFixed(0)}%</span></td>
        <td style="font-size: 0.75rem; color: var(--text-muted);">${evidenceSummary || "Direct Match"}</td>
      `;
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error("Error loading comparison table:", err);
  }
}

// 5. Fetch & Render Users & Delegations
async function loadUsersAndDelegations() {
  try {
    const [usersRes, delRes] = await Promise.all([
      fetch(`${API_BASE}/users`),
      fetch(`${API_BASE}/delegations`)
    ]);

    const users = await usersRes.json();
    const delegations = await delRes.json();

    const uTbody = document.getElementById("users-table-body");
    uTbody.innerHTML = "";
    users.forEach(u => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="font-mono" style="color: #38bdf8;">${u.employee_id}</td>
        <td><strong>${u.full_name}</strong></td>
        <td>${u.role}</td>
        <td><span class="badge" style="background:#1e293b;">${u.workforce_type}</span></td>
        <td>${u.department}</td>
        <td><span class="badge ${u.active ? 'badge-attributed' : 'badge-unattributed'}">${u.active ? 'ACTIVE' : 'INACTIVE'}</span></td>
      `;
      uTbody.appendChild(tr);
    });

    const dTbody = document.getElementById("delegations-table-body");
    dTbody.innerHTML = "";
    delegations.forEach(d => {
      const tr = document.createElement("tr");
      const fromStr = new Date(d.authorized_from).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const toStr = new Date(d.authorized_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const dateStr = new Date(d.authorized_from).toLocaleDateString([], { month: 'short', day: 'numeric' });

      tr.innerHTML = `
        <td class="font-mono"><strong>${d.shared_account_name}</strong></td>
        <td><b>${d.user_name}</b> <span class="text-dim">(${d.user_employee_id})</span></td>
        <td style="white-space:nowrap;">${dateStr} &bull; ${fromStr} - ${toStr}</td>
        <td style="font-size:0.8rem; color:var(--text-muted);">${d.reason}</td>
        <td><span class="badge ${d.status === 'ACTIVE' ? 'badge-attributed' : 'badge-unattributed'}">${d.status}</span></td>
      `;
      dTbody.appendChild(tr);
    });

  } catch (err) {
    console.error("Error loading roster and delegations:", err);
  }
}

// 6. Inspect Event Detail Modal
window.openEventDetail = async function(eventId) {
  const modal = document.getElementById("event-detail-modal");
  const modalContent = document.getElementById("modal-content");
  modal.classList.add("active");
  modalContent.innerHTML = `<div class="loading-spinner">Loading audit trail for ${eventId}...</div>`;

  try {
    const res = await fetch(`${API_BASE}/attribution/${eventId}`);
    if (!res.ok) throw new Error("Event not found");
    const data = await res.json();

    document.getElementById("modal-event-id").innerText = `Event Inspection: ${data.event.event_id}`;
    document.getElementById("modal-timestamp").innerText = new Date(data.event.timestamp).toLocaleString();

    // Candidate scores table
    let candidateRows = "";
    if (data.candidate_scores && data.candidate_scores.length > 0) {
      candidateRows = data.candidate_scores.map(c => `
        <tr>
          <td><b>${c.full_name}</b> <span class="text-dim font-mono">(${c.employee_id})</span></td>
          <td>${c.role} &bull; ${c.department}</td>
          <td class="font-mono text-center">+${c.delegation_score}</td>
          <td class="font-mono text-center">+${c.session_score}</td>
          <td class="font-mono text-center">+${c.device_score}</td>
          <td class="font-mono text-center">+${c.ip_score}</td>
          <td class="font-mono text-center">+${c.department_score}</td>
          <td class="font-mono text-center"><strong style="color: ${c.total_score >= 60 ? 'var(--green)' : 'var(--amber)'};">${c.total_score.toFixed(0)}</strong></td>
        </tr>
      `).join("");
    } else {
      candidateRows = `<tr><td colspan="8" class="text-center text-dim">Direct user account or no candidate scores needed.</td></tr>`;
    }

    modalContent.innerHTML = `
      <!-- Metadata Grid -->
      <div class="modal-section">
        <div class="modal-section-title">Log Event Metadata</div>
        <div class="meta-grid">
          <div class="meta-item"><span class="meta-key">Account Username</span><span class="meta-val font-mono">${data.event.username}</span></div>
          <div class="meta-item"><span class="meta-key">Clinical Action</span><span class="meta-val">${data.event.action} ${data.event.is_sensitive ? '<span class="badge-sensitive">SENSITIVE</span>' : ''}</span></div>
          <div class="meta-item"><span class="meta-key">Target Patient / Asset</span><span class="meta-val font-mono">${data.event.target_type}: ${data.event.target_id}</span></div>
          <div class="meta-item"><span class="meta-key">Session ID</span><span class="meta-val font-mono">${data.event.session_id || '<span class="text-red">None (Missing)</span>'}</span></div>
          <div class="meta-item"><span class="meta-key">Source IP</span><span class="meta-val font-mono">${data.event.source_ip}</span></div>
          <div class="meta-item"><span class="meta-key">Device Station</span><span class="meta-val font-mono">${data.event.device_id}</span></div>
        </div>
      </div>

      <!-- Verdict Comparison Box -->
      <div class="verdict-box">
        <div class="verdict-card">
          <div class="verdict-title">Baseline Verdict (Shift Count)</div>
          <div style="font-size: 1.1rem; margin-bottom: 0.4rem;">
            ${data.baseline_attribution.user ? `<b style="color: var(--green);">${data.baseline_attribution.user}</b>` : `<span class="badge badge-${data.baseline_attribution.status.toLowerCase()}">${data.baseline_attribution.status}</span>`}
          </div>
          <div class="text-dim" style="font-size: 0.8rem;">Confidence: <b>${data.baseline_attribution.confidence}%</b></div>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem;">${data.baseline_attribution.explanation}</div>
        </div>

        <div class="verdict-card proto-card">
          <div class="verdict-title" style="color: var(--green);">Prototype Attribution Verdict</div>
          <div style="font-size: 1.1rem; margin-bottom: 0.4rem;">
            ${data.prototype_attribution.user ? `<b style="color: #38bdf8;">${data.prototype_attribution.user}</b>` : `<span class="badge badge-${data.prototype_attribution.status.toLowerCase()}">${data.prototype_attribution.status}</span>`}
          </div>
          <div style="font-size: 0.8rem;">
            Confidence: <b class="badge-conf-${data.prototype_attribution.level.toLowerCase().substring(0,3)}">${data.prototype_attribution.score}% (${data.prototype_attribution.level})</b>
            &bull; Method: <b>${data.prototype_attribution.method}</b>
          </div>
        </div>
      </div>

      <!-- Candidate Scoring Table -->
      <div class="modal-section">
        <div class="modal-section-title">Identity Candidate Evidence Matrix (Max 100)</div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Role / Dept</th>
                <th class="text-center">Delegation (40)</th>
                <th class="text-center">Session (30)</th>
                <th class="text-center">Device (15)</th>
                <th class="text-center">IP (10)</th>
                <th class="text-center">Dept (5)</th>
                <th class="text-center">Total Score</th>
              </tr>
            </thead>
            <tbody>
              ${candidateRows}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Audit Explanation -->
      <div class="modal-section">
        <div class="modal-section-title">Auditable Attribution Explanation</div>
        <div class="audit-explanation-text">${data.attribution?.explanation || 'No explanation available.'}</div>
      </div>
    `;

  } catch (err) {
    modalContent.innerHTML = `<div class="text-red">Error loading event detail: ${err.message}</div>`;
  }
};

function closeModal() {
  document.getElementById("event-detail-modal")?.classList.remove("active");
}

// 7. Reprocess Events Pipeline Trigger
async function reprocessEvents() {
  const btn = document.getElementById("btn-reprocess");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>Processing Pipeline...</span>`;
  }

  try {
    const res = await fetch(`${API_BASE}/process-events`, { method: "POST" });
    const result = await res.json();
    alert(`Pipeline executed successfully! Reprocessed ${result.processed_count} events.`);
    await loadAllData();
  } catch (err) {
    alert(`Error reprocessing events: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
        </svg>
        <span>Reprocess Events</span>
      `;
    }
  }
}
