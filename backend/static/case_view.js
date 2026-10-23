// McKennel & Co.: shared helpers and the case view (interviewer guide, handouts, quality check).
// Model-written text is always inserted with textContent, never innerHTML.
"use strict";

const $ = (sel) => document.querySelector(sel);
const LEVEL = { easy: "Easy", medium: "Medium", hard: "Hard", instant_offer: "Instant Offer" };
const KIND = {
  framework: "Framework", brainstorm: "Brainstorm", market_sizing: "Market sizing", quant: "Quant",
  exhibit_read: "Exhibit", pivot: "Pivot", synthesis: "Synthesis",
};
const ESTIMATE = {
  easy: "Usually about three minutes: plan, write, check every number, then an independent review.",
  medium: "Usually five to seven minutes: plan, write, check every number, then independent reviews.",
  hard: "Usually six to eleven minutes. Harder cases get more fix-and-review rounds.",
  instant_offer: "Usually seven to twenty minutes. Instant Offer cases get the most fix-and-review rounds.",
};
const STATUS = {
  verified: "Verified",
  review_flags: "Reviewer flags remain",
  needs_attention: "Needs attention",
};


// h("div.cls", {attr}, child, "text", ...) — tiny element builder.
function h(spec, attrs, ...children) {
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  if (attrs && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) {
    children.unshift(attrs);
  } else if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "onclick") el.addEventListener("click", v);
      else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v);
    }
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function list(items, cls) {
  if (!items || !items.length) return null;
  return h("ul" + (cls ? "." + cls : ""), null, items.map((t) => h("li", null, t)));
}

async function api(path, init) {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

function exhibitBlock(ex, n) {
  const box = h("figure.exhibit", { id: `exhibit-${ex.id}` },
    h("div.exhibit-label", null, `Exhibit ${n}`),
    h("h4", null, ex.title),
    ex.subtitle ? h("div.sub", null, ex.subtitle) : null);
  if (ex.kind === "text") {
    box.append(h("div.textbody", null, ex.text_body || ""));
  } else {
    if (ex.kind !== "table") {
      const chart = renderChart(ex);
      if (chart) box.append(chart);
    }
    if (ex.kind === "table") {
      const table = h("table", null,
        h("thead", null, h("tr", null, ex.columns.map((c) => h("th", null, c)))),
        h("tbody", null, ex.rows.map((r, i) =>
          h("tr" + (/^(total|sum)\b/i.test(r.label.trim()) ? ".total" : ""), null,
            h("td", null, r.label), (ex.display[i] || []).map((c) => h("td", null, c))))));
      box.append(table);
    }
  }
  if (ex.footnote) box.append(h("div.foot", null, ex.footnote));
  return box;
}

function exhibitNumbers(c) {
  const map = {};
  c.exhibits.forEach((e, i) => { map[e.id] = i + 1; });
  return map;
}

function guidePanel(c) {
  const exNum = exhibitNumbers(c);
  const exById = Object.fromEntries(c.exhibits.map((e) => [e.id, e]));
  const panel = h("div.tab-panel", { "data-tab": "guide" });

  panel.append(h("section.block", null,
    h("div.readaloud", null, h("span.readaloud-label", null, "Read aloud"), c.prompt)));

  if (c.clarifying.length) {
    panel.append(h("section.block", null, h("h2", null, "Clarifying answers"),
      h("div.qa", null, c.clarifying.flatMap((q) => [h("div.q", null, q.question), h("div", null, q.answer)]))));
  }

  panel.append(h("section.block", null, h("h2", null, "Sample framework"),
    h("div.framework", null, c.framework.map((b) => h("div.bucket", null, h("h4", null, b.name), list(b.points)))),
    c.framework_notes ? h("p.note", null, c.framework_notes) : null));

  c.sections.forEach((s, i) => {
    const card = h("section.section-card", null,
      h("div.section-head", null, h("h3", null, `${i + 1}. ${s.title}`), h("span.kind", null, KIND[s.kind] || s.kind)),
      h("p.ask", null, s.ask));
    for (const id of s.exhibit_ids) if (exById[id]) card.append(exhibitBlock(exById[id], exNum[id]));
    if (s.info_to_share.length) card.append(h("div.subhead", null, "Share if asked"), list(s.info_to_share, "share"));
    if (s.calculations.length) {
      card.append(h("div.subhead", null, "Worked math"),
        h("table.calc-table", null,
          h("thead", null, h("tr", null, h("th", null, "Step"), h("th", null, "Formula"), h("th", null, "Result"))),
          h("tbody", null, s.calculations.map((k) =>
            h("tr", null, h("td", null, k.label), h("td.formula", null, k.expression_display), h("td.result", null, k.display))))));
    }
    card.append(h("div.subhead", null, "Model answer"), h("div.answer", null, s.model_answer));
    const coach = h("div.coach");
    const pairs = [["What great looks like", s.what_great_looks_like, ""], ["Common mistakes", s.common_mistakes, ""],
      ["Hints", s.hints, ""], ["Pushback", s.pushback, "pushback"]];
    for (const [title, items, cls] of pairs) {
      if (items && items.length) coach.append(h("div" + (cls ? "." + cls : ""), null, h("div.subhead", null, title), list(items)));
    }
    if (coach.childElementCount) card.append(coach);
    panel.append(card);
  });

  const r = c.recommendation;
  panel.append(h("section.block.recommendation", null, h("h2", null, "Recommendation"),
    h("div.rec-answer", null, r.answer),
    h("div.cols", null,
      h("div", null, h("div.subhead", null, "Risks"), list(r.risks)),
      h("div", null, h("div.subhead", null, "Next steps"), list(r.next_steps)))));

  if (c.rubric.length) {
    panel.append(h("section.block", null, h("h2", null, "Scoring rubric"),
      h("table.rubric", null,
        h("thead", null, h("tr", null, h("th", null, "Dimension"), h("th", null, "Strong"), h("th", null, "Weak"))),
        h("tbody", null, c.rubric.map((l) => h("tr", null, h("td", null, l.dimension), h("td", null, l.strong), h("td", null, l.weak)))))));
  }
  panel.append(h("section.block", null, h("h2", null, "Interviewer notes"), h("p", null, c.interviewer_notes)));
  return panel;
}

function handoutPanel(c) {
  const panel = h("div.tab-panel", { "data-tab": "handouts" });
  panel.append(h("section.handout-page", null,
    h("div.handout-num", null, "Case prompt"),
    h("h2", null, c.title),
    h("div.readaloud", null, c.prompt)));
  c.exhibits.forEach((e, i) => panel.append(h("section.handout-page", null, exhibitBlock(e, i + 1))));
  return panel;
}

const usd = (x) => (x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(3)}`);
const num = (x) => (x || 0).toLocaleString("en-US");

// Every model call this case made, with tokens, time and dollars (measured from the API's usage data).
function usageBlock(u) {
  if (!u) return h("div.qcheck", null, h("h3", null, "Tokens and cost"), h("p.muted", null, "Not recorded for this case (made before token logging was added)."));
  return h("div.qcheck", null,
    h("h3", null, "Tokens and cost"),
    h("p.muted", null, `${u.calls} model calls on ${u.model} · ${num(u.input)} input tokens (${num(u.cached)} cached) · ${num(u.output)} output · ${Math.round(u.seconds)} s of model time`),
    h("table.usage-table", null,
      h("thead", null, h("tr", null, ["Step", "Agent", "Input", "Cached", "Output", "Seconds", "Cost"].map((t) => h("th", null, t)))),
      h("tbody", null, u.steps.map((s) => h("tr", null, h("td", null, s.step), h("td", null, s.role), h("td", null, num(s.input)),
        h("td", null, num(s.cached)), h("td", null, num(s.output)), h("td", null, s.seconds.toFixed(0)), h("td", null, usd(s.usd))))),
      h("tfoot", null, h("tr", null, h("td", null, "Total"), h("td", null, ""), h("td", null, num(u.input)), h("td", null, num(u.cached)),
        h("td", null, num(u.output)), h("td", null, u.seconds.toFixed(0)), h("td", null, usd(u.usd))))));
}

function qualityPanel(q, usage, opinion, difficulty) {
  const panel = h("div.tab-panel", { "data-tab": "quality" });
  const issue = (i) => h("div.issue." + i.severity, null, h("b", null, i.severity), `${i.where}: ${i.problem}`, i.fix ? ` — Fix: ${i.fix}` : null);
  panel.append(h("div.qcheck", null,
    h("h3", null, STATUS[q.status] || q.status),
    h("p", null, q.status === "verified"
      ? "Every calculation was recomputed from the case's own inputs, every exhibit total checked, and an independent review found no remaining errors."
      : "Some issues remain after automatic fixing. Read them before running the case."),
    h("p.muted", null, `${q.fix_rounds} automatic fix round${q.fix_rounds === 1 ? "" : "s"} · model ${q.model}`
      + (q.engine !== "strong" && ["hard", "instant_offer"].includes(difficulty) ? " · Luna's own review is lenient at this level; get a second opinion before relying on it" : ""))));
  panel.append(h("div.qcheck", null, h("h3", null, "Number checks"),
    q.checks.length ? q.checks.map(issue) : h("p", null, "All formulas compute, match their expected values, and exhibits add up.")));
  q.reviews.forEach((r, n) => {
    panel.append(h("div.qcheck", null,
      h("h3", null, n === q.reviews.length - 1 && n > 0 ? "Final review" : ["Independent review", "Second review", "Third review", "Fourth review", "Fifth review"][n] || `Review ${n + 1}`),
      h("p", null, r.summary),
      h("p.muted", null, `Difficulty fit: ${r.difficulty_fit.replace("_", " ")}`),
      r.issues.length ? r.issues.map(issue) : h("p", null, "No issues found.")));
  });
  if (opinion) {
    const serious = opinion.issues.filter((i) => i.severity !== "minor").length;
    panel.prepend(h("div.qcheck.second-opinion", null,
      h("h3", null, `Second opinion · ${opinion.model}`),
      h("p", null, serious ? `${serious} serious issue${serious === 1 ? "" : "s"} found. Read them before running the case.` : "No serious issues found."),
      h("p", null, opinion.summary),
      h("p.muted", null, `Difficulty fit: ${opinion.difficulty_fit.replace("_", " ")} · cost ${usd(opinion.usage.usd)}`),
      opinion.issues.length ? opinion.issues.map(issue) : null));
  }
  panel.append(usageBlock(usage));
  return panel;
}

function renderCase(data) {
  const c = data.case;
  const q = data.quality;
  const root = $("#case");
  root.replaceChildren();

  const head = h("header.case-head", null,
    h("div.case-tags", null,
      h("span.pill.pill-" + c.difficulty, null, LEVEL[c.difficulty] || c.difficulty),
      h("span", null, c.case_type), h("span.sep", null, "|"), h("span", null, c.industry),
      h("span.sep", null, "|"), h("span", null, c.format.replace("_", "-")),
      h("span.sep", null, "|"), h("span", null, `${c.duration_minutes} min`),
      h("span.sep", null, "|"),
      h("span.quality-badge." + q.status, null, h("span.dot.dot-" + q.status), STATUS[q.status] || q.status)),
    h("h1", null, c.title),
    h("div.case-client", null, `Client: ${c.client}`),
    h("div.case-actions", null,
      h("button.btn.btn-ghost", { type: "button", onclick: () => window.print() }, "Print this tab"),
      h("button.btn.btn-ghost", { type: "button", onclick: (ev) => savePdf(data.id, ev.currentTarget) },
        data.pdf ? "Re-save PDF" : "Save PDF to Generated Cases"),
      h("button.btn.btn-ghost", { type: "button", title: "Choose where on your computer to save the PDF", onclick: (ev) => savePdfAs(data.id, ev.currentTarget) }, "Save PDF as…"),
      q.engine === "strong" ? null : h("button.btn.btn-ghost", { type: "button", title: "One independent review by the stronger model (gpt-5.6-terra), about $0.05. Nothing is rewritten.", onclick: (ev) => secondOpinion(data.id, ev.currentTarget) },
        data.second_opinion ? "New second opinion" : "Second opinion (Terra, ~5¢)"),
      h("button.btn.btn-ghost", { type: "button", onclick: () => startPractice({ case_id: data.id }) }, "Practice this case with Handsome Dan"),
      h("button.btn.btn-ghost.btn-danger", { type: "button", onclick: () => removeCase(data.id) }, "Delete")),
    h("p.saved-note", { id: "saved-note" }, data.pdf ? `Saved to Generated Cases as “${data.pdf}”` : ""));

  const panels = [guidePanel(c), handoutPanel(c), qualityPanel(q, data.usage, data.second_opinion, c.difficulty)];
  const labels = { guide: "Interviewer guide", handouts: "Candidate handouts", quality: "Quality check" };
  const tabs = h("div.tabs", { role: "tablist" });
  const select = (name) => {
    tabs.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    panels.forEach((p) => { p.hidden = p.dataset.tab !== name; p.classList.toggle("active", p.dataset.tab === name); });
  };
  for (const name of Object.keys(labels)) {
    const t = h("button.tab", { type: "button", role: "tab", onclick: () => select(name) }, labels[name]);
    t.dataset.tab = name;
    tabs.append(t);
  }
  root.append(head, tabs, ...panels);
  select("guide");
}

// Save the PDF wherever the user picks, using the browser's own save dialog (Edge/Chrome); other
// browsers fall back to a normal download, which also lets the user choose a folder.
async function savePdfAs(id, btn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Preparing PDF…";
  try {
    const res = await fetch(`/api/cases/${id}/pdf/file`);
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(detail);
    }
    const name = decodeURIComponent((res.headers.get("content-disposition") || "").match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i)?.[1] || "case.pdf");
    const blob = await res.blob();
    if (window.showSaveFilePicker) {
      let handle;
      try {
        handle = await window.showSaveFilePicker({ suggestedName: name, types: [{ description: "PDF", accept: { "application/pdf": [".pdf"] } }] });
      } catch (err) {
        if (err.name === "AbortError") return; // the user closed the dialog
        throw err;
      }
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
      $("#saved-note").textContent = `Saved “${handle.name}” where you chose.`;
    } else {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.append(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      $("#saved-note").textContent = `Downloading “${name}”.`;
    }
  } catch (err) {
    $("#saved-note").textContent = `Couldn't save the PDF: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

async function savePdf(id, btn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Saving PDF…";
  try {
    const res = await api(`/api/cases/${id}/pdf`, { method: "POST" });
    $("#saved-note").textContent = `Saved to Generated Cases as “${res.pdf}”`;
    btn.textContent = "Re-save PDF";
  } catch (err) {
    $("#saved-note").textContent = `Couldn't save the PDF: ${err.message}`;
    btn.textContent = label;
  } finally {
    btn.disabled = false;
  }
}

async function secondOpinion(id, btn) {
  btn.disabled = true;
  btn.textContent = "Reviewing… (about a minute)";
  try {
    await api(`/api/cases/${id}/second-opinion`, { method: "POST" });
    await openCase(id);
    document.querySelector('.tab[data-tab="quality"]').click();
    refreshSpend();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Second opinion (Terra, ~5¢)";
    $("#saved-note").textContent = `Second opinion failed: ${err.message}`;
  }
}

async function removeCase(id) {
  if (!confirm("Delete this case from the library? Its PDF in Generated Cases is deleted too.")) return;
  await api(`/api/cases/${id}`, { method: "DELETE" });
  currentId = null;
  showView("library");
}

// ?print=<id> renders one case as a document (interviewer guide, then candidate handouts) for PDF export.
async function renderPrintView(id) {
  document.body.classList.add("print-mode");
  const data = await api(`/api/cases/${id}`);
  renderCase(data);
  showView("case");
  for (const p of document.querySelectorAll(".tab-panel")) {
    const keep = p.dataset.tab === "guide" || p.dataset.tab === "handouts";
    p.hidden = !keep;
    p.classList.toggle("active", keep);
  }
  const handouts = document.querySelector('.tab-panel[data-tab="handouts"]');
  handouts.prepend(h("h2.print-part", null, "Candidate handouts"));
  document.title = `${LEVEL[data.case.difficulty]} - ${data.case.title}`;
  window.__caseReady = true;
}

