const state = { data: null, selected: new Set(), filter: "all" };
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[character]));

async function request(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2800);
}

function render(data) {
  state.data = data;
  const validIds = new Set(data.leads.map((lead) => lead.id));
  state.selected.forEach((id) => { if (!validIds.has(id)) state.selected.delete(id); });
  $("event-brief").textContent = data.event_brief;
  $("mode").textContent = `${data.mode} MODE`;
  $("stat-leads").textContent = data.stats.leads;
  $("stat-qualified").textContent = data.stats.qualified;
  $("stat-drafts").textContent = data.stats.drafts;
  $("stat-contacted").textContent = data.stats.contacted;
  $("nav-lead-count").textContent = data.stats.leads;
  $("nav-draft-count").textContent = data.stats.drafts;
  const visibleLeads = data.leads.filter((lead) => state.filter === "all" || (state.filter === "review" ? lead.status !== "contacted" : lead.status === "contacted"));
  const rows = visibleLeads.map((lead) => `
    <tr>
      <td class="check-col"><input type="checkbox" class="lead-check" data-id="${lead.id}" ${state.selected.has(lead.id) ? "checked" : ""}></td>
      <td><span class="company">${escapeHtml(lead.company)}</span><span class="sub">${escapeHtml(lead.industry)} · ${escapeHtml(lead.location)}</span></td>
      <td><span class="contact">${escapeHtml(lead.contact)}</span><span class="sub">${escapeHtml(lead.email)}</span></td>
      <td><span class="score ${lead.fit_score < 60 ? "low" : ""}">${lead.fit_score || "—"}${lead.fit_score ? "/100" : ""}</span></td>
      <td class="reason">${escapeHtml(lead.fit_reason || "Run the lead finder to score this lead.")}</td>
      <td><span class="status ${escapeHtml(lead.status)}">${escapeHtml(lead.status)}</span></td>
    </tr>`).join("");
  $("leads-body").innerHTML = rows || `<tr><td colspan="6">No leads in this section yet.</td></tr>`;
  document.querySelectorAll(".lead-check").forEach((box) => box.addEventListener("change", (event) => {
    const id = Number(event.target.dataset.id);
    event.target.checked ? state.selected.add(id) : state.selected.delete(id);
    updateSelection();
  }));
  updateSelection();
  $("drafts-list").innerHTML = data.drafts.slice(0, 5).map((draft) => `
    <div class="draft"><div class="channel">${draft.channel === "linkedin" ? "in" : draft.channel === "email" ? "@" : "☎"}</div>
      <div class="draft-info"><div class="draft-title">${escapeHtml(draft.company)} · ${escapeHtml(draft.channel)}</div><div class="draft-meta">${draft.status === "pending" ? "Awaiting approval" : "Approved"} · ${escapeHtml(draft.contact)}</div></div>
      ${draft.status === "pending" ? `<button class="approve" data-draft="${draft.id}">Approve</button>` : `<span class="draft-meta">Done</span>`}
    </div>`).join("") || `<div class="empty">No drafts yet. Select qualified leads above.</div>`;
  $("activity-list").innerHTML = data.activities.slice(0, 5).map((item) => `
    <div class="activity" data-activity="${item.id}"><div class="channel">${item.kind === "sent" ? "✓" : item.kind === "agent" ? "✦" : "i"}</div><div class="activity-info"><div class="activity-message">${escapeHtml(item.message)}</div><div class="activity-time">${new Date(item.created_at).toLocaleString()}</div></div></div>`).join("");
  document.querySelectorAll("[data-activity]").forEach((element) => element.addEventListener("click", () => showActivity(Number(element.dataset.activity))));
  document.querySelectorAll(".approve").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await request("/api/outreach/approve", { method: "POST", body: JSON.stringify({ draft_id: Number(button.dataset.draft) }) }); toast("Approved and recorded in the activity feed."); await load(); } catch (error) { toast(error.message); button.disabled = false; }
  }));
}

function showActivity(activityId) {
  const item = state.data.activities.find((activity) => activity.id === activityId);
  if (!item) return;
  $("activity-modal-title").textContent = item.company ? `${item.company} — ${item.kind}` : item.kind;
  $("activity-modal-meta").textContent = new Date(item.created_at).toLocaleString();
  $("activity-modal-summary").textContent = item.message;
  $("activity-modal-details").textContent = item.details || "No message body was recorded for this activity.";
  $("activity-modal").hidden = false;
}

function updateSelection() {
  $("selection-note").textContent = `${state.selected.size} selected`;
  const reviewable = state.data ? state.data.leads.some((lead) => lead.status !== "contacted") : false;
  $("draft-btn").disabled = !reviewable;
  $("draft-btn").textContent = state.selected.size ? "Create outreach drafts" : "Create drafts for all review leads";
  const boxes = [...document.querySelectorAll(".lead-check")];
  $("select-all").checked = boxes.length > 0 && boxes.every((box) => box.checked);
}

async function load() {
  try { render(await request("/api/dashboard")); } catch (error) { toast(error.message); }
}

$("find-btn").addEventListener("click", async () => {
  const button = $("find-btn");
  button.disabled = true; button.textContent = "Finding leads…";
  try { const result = await request("/api/agents/find-leads", { method: "POST", body: "{}" }); toast(`Lead finder scored ${result.count} candidates.`); await load(); } catch (error) { toast(error.message); } finally { button.disabled = false; button.innerHTML = "<span>✦</span> Run lead finder"; }
});
$("draft-btn").addEventListener("click", async () => {
  try { const result = await request("/api/outreach/drafts", { method: "POST", body: JSON.stringify({ lead_ids: [...state.selected] }) }); toast(`Created ${result.count * 3} channel drafts for review.`); state.selected.clear(); await load(); } catch (error) { toast(error.message); }
});
$("reset-btn").addEventListener("click", async () => { await request("/api/reset", { method: "POST", body: "{}" }); state.selected.clear(); toast("Demo workspace reset."); await load(); });
document.querySelectorAll("[data-section]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.section === button.dataset.section));
  document.querySelector(".panel").scrollIntoView({ behavior: "smooth" });
}));
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
  state.filter = button.dataset.filter;
  document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
  render(state.data);
}));
$("select-all").addEventListener("change", (event) => {
  document.querySelectorAll(".lead-check").forEach((box) => {
    box.checked = event.target.checked;
    const id = Number(box.dataset.id);
    event.target.checked ? state.selected.add(id) : state.selected.delete(id);
  });
  updateSelection();
});
$("activity-modal-close").addEventListener("click", () => { $("activity-modal").hidden = true; });
$("activity-modal").addEventListener("click", (event) => {
  if (event.target === $("activity-modal")) $("activity-modal").hidden = true;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") $("activity-modal").hidden = true;
});
load();
