// Casebook cases (a BAIN sub-tab): browse the casebook cases the knowledge pack was built from, convert one
// into a full case, then open it or give it live like any generated case.
// Needs case_view.js (h, api, LEVEL, openCase, startLive) and app.js (go, sessionJobs, refreshSpend).
"use strict";

let cbCases = null;
let cbLevel = "";

const CB_TYPES = {
  profitability: "Profitability", market_entry: "Market entry", growth_strategy: "Growth strategy",
  investment_decision: "Investment decision", m_and_a: "M&A", new_product_launch: "New product launch",
  cost_reduction: "Cost reduction", operations: "Operations", private_equity_due_diligence: "PE due diligence",
  public_sector_or_nonprofit: "Public sector / nonprofit", pricing: "Pricing", market_sizing: "Market sizing",
  competitive_response: "Competitive response", turnaround: "Turnaround", organization_or_people: "Organization",
  other: "Other",
};

// Which folder the casebook cases come from, with a way to point it somewhere else.
function renderFolder(info, editing = false, error = "") {
  const box = $("#cb-folder");
  if (editing) {
    const input = h("input", { type: "text", value: info.folder, "aria-label": "Casebook folder path", spellcheck: "false" });
    const save = async () => {
      try {
        await api("/api/casebook/folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: input.value }) });
        cbCases = null;
        loadCasebook();
      } catch (err) { renderFolder({ ...info, folder: input.value }, true, err.message); }
    };
    input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") save(); if (ev.key === "Escape") renderFolder(info); });
    box.replaceChildren(h("div.cb-folder-edit", null,
      h("label", null, "Folder of case PDFs (subfolders count too)", input),
      h("div.cb-folder-btns", null,
        h("button.btn.btn-primary.btn-inline", { type: "button", onclick: save }, "Use this folder"),
        h("button.btn.btn-ghost", { type: "button", onclick: () => renderFolder(info) }, "Cancel"))),
      ...(error ? [h("p.form-error", null, error)] : []), // replaceChildren would print a literal "null"
      h("p.muted.small", null, "Paste the full path from File Explorer's address bar, e.g. C:\\Users\\you\\Documents\\Casebooks. The files stay on this computer."));
    input.focus();
    input.select();
    return;
  }
  box.replaceChildren(h("div.cb-folder-row", null,
    h("span", null, "Casebook folder: ", h("code", null, info.folder),
      info.available && cbCases ? ` · ${cbCases.length} cases` : ""),
    h("button.link-btn", { type: "button", onclick: () => renderFolder(info, true) }, "Change folder"),
    info.custom ? h("button.link-btn", { type: "button", onclick: async () => {
      await api("/api/casebook/folder", { method: "DELETE" });
      cbCases = null;
      loadCasebook();
    } }, "Use the default") : null));
}

async function loadCasebook() {
  pollBatch();
  if (!cbCases) {
    try {
      const data = await api("/api/casebook");
      if (!data.available) {
        cbCases = null;
        renderFolder(data);
        $("#cb-count").textContent = "";
        $("#cb-list").replaceChildren(h("p.muted", null, `No case PDFs found in ${data.folder}. The casebooks are copyrighted and aren't part of this repo: click “Change folder” above and point it at a folder of case PDFs on this computer.`));
        return;
      }
      cbCases = data.cases;
      renderFolder(data);
      const schools = [...new Set(cbCases.map((c) => c.school))].sort();
      $("#cb-school").replaceChildren(h("option", { value: "" }, "All casebooks"), ...schools.map((s) => h("option", { value: s }, s)));
      const types = [...new Set(cbCases.map((c) => c.case_type).filter(Boolean))].sort((a, b) => (CB_TYPES[a] || a).localeCompare(CB_TYPES[b] || b));
      $("#cb-type").replaceChildren(h("option", { value: "" }, "Any case type"), ...types.map((t) => h("option", { value: t }, CB_TYPES[t] || t)));
    } catch (err) {
      $("#cb-list").replaceChildren(h("p.form-error", null, `Couldn't load the casebook: ${err.message}`));
      return;
    }
  }
  renderCasebookList();
}

function renderCasebookList() {
  const shown = shownCases();
  $("#cb-count").textContent = `${shown.length} of ${cbCases.length} cases`;
  updateConvertAllButton();
  $("#cb-list").replaceChildren(...(shown.length ? shown.map((c) => h("article.lib-card.cb-card", null,
    h("div.badges", null,
      c.level ? h("span.pill.pill-" + c.level, null, LEVEL[c.level]) : h("span.badge", null, "Unrated"),
      c.case_type ? h("span.badge", null, CB_TYPES[c.case_type] || c.case_type) : null,
      c.exhibits ? h("span.badge", null, `${c.exhibits} exhibit${c.exhibits === 1 ? "" : "s"}`) : null),
    h("h3", null, c.title),
    h("div.meta", null, c.year ? `${c.school} casebook · ${c.year}` : `${c.school} casebook`),
    c.industry ? h("p.summary", null, c.industry) : null,
    h("div.actions", null,
      ...(c.converted
        ? [h("button.btn.btn-ghost.cb-open-full", { type: "button", title: "The converted case: guide, handouts, quality check, live and practice", onclick: () => openCase(c.converted) }, "Open full case"),
          h("button.btn.btn-ghost", { type: "button", title: "Opens the full case with the candidate's screen ready to share", onclick: () => giveConvertedLive(c.converted) }, "Give Case")]
        : [h("button.btn.btn-ghost", { type: "button", title: "Turn it into a full case like the generated ones (about 1-2¢ on Luna); then you can give it", onclick: () => convertCasebook(c.id) }, "Convert")]),
      h("a.btn.btn-ghost", { href: `/api/casebook/${c.id}/file`, target: "_blank", rel: "noopener", title: "The casebook's own PDF" }, "Raw PDF")),
    h("p.cb-convert-status.muted.small", { id: `cbconv-${c.id}` }, cbConverting[c.id] ? convertText(cbConverting[c.id]) : "")))
    : [h("p.muted", null, "No cases match.")]));
}

function wireCasebook() {
  $("#cb-search").addEventListener("input", () => cbCases && renderCasebookList());
  $("#cb-school").addEventListener("change", () => cbCases && renderCasebookList());
  $("#cb-type").addEventListener("change", () => cbCases && renderCasebookList());
  $("#cb-converted").addEventListener("change", () => cbCases && renderCasebookList());
  $("#cb-convert-all").addEventListener("click", confirmConvertAll);
  document.querySelectorAll("#cb-level .chip").forEach((c) => c.addEventListener("click", () => {
    cbLevel = c.dataset.level;
    document.querySelectorAll("#cb-level .chip").forEach((x) => x.classList.toggle("active", x === c));
    if (cbCases) renderCasebookList();
  }));
}

// ------------------------------------------------------------------ converting a casebook case into a full case

const cbConverting = {}; // casebook id -> {stage, usd, error, case_id}

function convertText(st) {
  if (st.error) return `Couldn't convert it: ${st.error}`;
  if (st.case_id) return "Converted: it's in BAIN now.";
  return `Converting… ${st.stage || "starting"}${st.usd ? ` · $${st.usd.toFixed(3)} so far` : ""}`;
}

function showConvertStatus(cid) {
  const line = $(`#cbconv-${cid}`);
  if (line) line.textContent = cbConverting[cid] ? convertText(cbConverting[cid]) : "";
}

async function convertCasebook(cid) {
  cbConverting[cid] = { stage: "starting" };
  showConvertStatus(cid);
  let started;
  try {
    started = await api(`/api/casebook/${cid}/convert`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  } catch (err) {
    cbConverting[cid] = { error: err.message };
    showConvertStatus(cid);
    return;
  }
  if (started.case_id) return finishConvert(cid, started.case_id);
  sessionJobs.add(started.job_id);
  for (;;) { // follow the job until it's done
    await new Promise((r) => setTimeout(r, 1500));
    let j;
    try { j = await api(`/api/jobs/${started.job_id}`); } catch { continue; }
    if (j.status === "done") return finishConvert(cid, j.case_id);
    if (j.status === "error" || j.status === "interrupted") {
      cbConverting[cid] = { error: j.error || "it failed" };
      showConvertStatus(cid);
      return;
    }
    cbConverting[cid] = { stage: j.current ? j.current.step : (j.stages.at(-1) || {}).stage, usd: j.usd };
    showConvertStatus(cid);
  }
}

function finishConvert(cid, caseId) {
  const c = (cbCases || []).find((x) => x.id === cid);
  if (c) c.converted = caseId;
  cbConverting[cid] = { case_id: caseId };
  showConvertStatus(cid);
  refreshSpend();
  if (!$("#view-casebook").hidden) renderCasebookList();
}

// A converted case runs live from its full interviewer guide, like any generated case.
async function giveConvertedLive(caseId) {
  await openCase(caseId);
  if (!$("#view-case").hidden) await startLive(caseId);
}

// ------------------------------------------------------------------ converting many cases at once

const CONVERT_USD = [0.01, 0.025]; // per case, measured (finding exhibits included)
let cbBatchTimer = null;

function shownCases() {
  const q = $("#cb-search").value.trim().toLowerCase();
  const school = $("#cb-school").value;
  const type = $("#cb-type").value;
  const converted = $("#cb-converted").value;
  return (cbCases || []).filter((c) => (!cbLevel || c.level === cbLevel) && (!school || c.school === school)
    && (!type || c.case_type === type)
    && (!converted || (converted === "yes") === Boolean(c.converted))
    && (!q || `${c.title} ${c.school} ${c.year} ${c.industry || ""}`.toLowerCase().includes(q)));
}

function updateConvertAllButton() {
  const btn = $("#cb-convert-all");
  if (!btn || !cbCases) return;
  const n = shownCases().filter((c) => !c.converted).length;
  btn.hidden = n === 0;
  btn.textContent = `Convert all shown (${n})`;
}

const money2 = (x) => `$${x.toFixed(2)}`;

// The confirmation pop-up: how many, what it costs, how long, and what happens at the daily cap.
async function confirmConvertAll() {
  const ids = shownCases().filter((c) => !c.converted).map((c) => c.id);
  if (!ids.length) return;
  let budget = { spent_today_usd: 0, daily_budget_usd: 10 };
  try { budget = await api("/api/budget"); } catch { /* show the estimate anyway */ }
  const left = Math.max(0, budget.daily_budget_usd - budget.spent_today_usd);
  const [lo, hi] = CONVERT_USD.map((u) => u * ids.length);
  const fitsToday = Math.floor(left / ((CONVERT_USD[0] + CONVERT_USD[1]) / 2));
  const minutes = Math.ceil((ids.length * 2) / 3); // about 2 minutes each, 3 at a time
  const close = () => { box.remove(); document.body.classList.remove("viewer-open"); };
  const yes = h("button.btn.btn-primary.btn-inline", { type: "button" }, `Yes, convert ${ids.length} case${ids.length === 1 ? "" : "s"}`);
  const box = h("div.ex-viewer.flag-dialog", { role: "dialog", "aria-modal": "true", "aria-label": "Convert all shown" },
    h("div.flag-panel.card", null,
      h("h3.card-title", null, `Convert ${ids.length} casebook case${ids.length === 1 ? "" : "s"}?`),
      h("ul.confirm-list", null,
        h("li", null, h("b", null, "Cost: "), `about ${money2(lo)}–${money2(hi)} on Luna (1–2.5¢ a case).`),
        h("li", null, h("b", null, "Time: "), `about ${minutes < 90 ? `${minutes} minutes` : `${Math.round(minutes / 6) / 10} hours`}, three at a time. You can keep using the app.`),
        h("li", null, h("b", null, "Today's budget: "), `${money2(left)} of ${money2(budget.daily_budget_usd)} left.`,
          hi > left ? h("span.warn-text", null, ` That covers roughly ${fitsToday} cases; the batch stops by itself at the cap, and you can resume it tomorrow.`) : null),
        h("li", null, "Cases already converted are skipped. You can stop the batch at any time; cases already converting finish.")),
      h("div.job-actions", null, h("button.btn.btn-ghost", { type: "button", onclick: close }, "Cancel"), yes)));
  yes.addEventListener("click", async () => {
    yes.disabled = true;
    try {
      await api("/api/casebook/convert-batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
      close();
      pollBatch();
    } catch (err) {
      yes.disabled = false;
      alert(`Couldn't start: ${err.message}`);
    }
  });
  box.addEventListener("click", (ev) => { if (ev.target === box) close(); });
  box.addEventListener("keydown", (ev) => { if (ev.key === "Escape") close(); });
  document.body.append(box);
  document.body.classList.add("viewer-open");
  yes.focus();
}

function renderBatch(b) {
  const box = $("#cb-batch");
  if (!box) return;
  if (!b || b.status === "none" || (b.status === "done" && box.dataset.dismissed === b.id)) { box.hidden = true; return; }
  box.hidden = false;
  const finished = b.converted + b.failed + b.skipped;
  const pct = b.total ? Math.round((100 * finished) / b.total) : 0;
  const head = b.status === "running" ? `Converting ${b.total} casebook cases`
    : b.status === "done" ? `Batch finished: ${b.converted} converted` : `Batch stopped: ${b.converted} converted`;
  box.replaceChildren(...[
    h("div.cb-batch-head", null, h("b", null, head),
      h("span.muted.small", null, ` · ${b.converted} done, ${b.converting} converting, ${b.waiting} waiting`
        + (b.failed ? `, ${b.failed} failed` : "") + (b.skipped ? `, ${b.skipped} already converted` : "") + ` · ${money2(b.usd)} so far`),
      b.status === "running"
        ? h("button.link-btn", { type: "button", onclick: async () => { renderBatch(await api("/api/casebook/convert-batch/stop", { method: "POST" })); } }, "Stop")
        : b.waiting
          ? h("button.link-btn", { type: "button", onclick: () => resumeBatch(b.remaining) }, `Resume (${b.waiting} left)`)
          : h("button.link-btn", { type: "button", onclick: () => { box.dataset.dismissed = b.id; box.hidden = true; } }, "Dismiss")),
    h("div.job-bar", null, h("i", { style: `width:${pct}%` })),
    b.reason && b.status !== "running" ? h("p.muted.small", null, b.reason) : null].filter(Boolean));
}

async function resumeBatch(ids) {
  try {
    await api("/api/casebook/convert-batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
  } catch (err) {
    alert(`Couldn't resume: ${err.message}`);
  }
  pollBatch();
}

async function pollBatch() {
  clearTimeout(cbBatchTimer);
  let b;
  try { b = await api("/api/casebook/convert-batch"); } catch { cbBatchTimer = setTimeout(pollBatch, 5000); return; }
  renderBatch(b);
  if (b.status === "running") {
    if (b.converted !== pollBatch.lastConverted) { // a case finished: refresh the list so its card shows Give Case
      pollBatch.lastConverted = b.converted;
      try { cbCases = (await api("/api/casebook")).cases; renderCasebookList(); } catch { /* next time */ }
    }
    cbBatchTimer = setTimeout(pollBatch, 3000);
  } else if (pollBatch.lastConverted !== undefined) {
    pollBatch.lastConverted = undefined;
    try { cbCases = (await api("/api/casebook")).cases; renderCasebookList(); } catch { /* fine */ }
    refreshSpend();
  }
}
