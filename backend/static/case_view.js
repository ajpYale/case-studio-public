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

// Converted casebook cases keep each exhibit's original image next to the redrawn version.
// The choice of which to show is remembered across cases.
function exhibitView() {
  return localStorage.getItem("exhibitView") || "original";
}

function exhibitBlock(ex, n) {
  if (ex.image_url) {
    const box = h("figure.exhibit.has-original", { id: `exhibit-${ex.id}` });
    const render = () => {
      const original = exhibitView() === "original";
      const flip = h("button.link-btn.ex-flip", { type: "button", title: "Switch between the casebook's original exhibit and the app's redrawn version" },
        original ? "Show redrawn" : "Show original");
      flip.addEventListener("click", (ev) => {
        ev.stopPropagation();
        localStorage.setItem("exhibitView", original ? "redrawn" : "original");
        render();
      });
      const redrawn = exhibitBody({ ...ex, image_url: null }, n);
      box.replaceChildren(...(original
        ? [h("div.exhibit-label", null, `Exhibit ${n}`, flip), h("img.ex-original", { src: ex.image_url, alt: ex.title })]
        : [...redrawn.childNodes].map((c, i) => (i === 0 ? h("div.exhibit-label", null, `Exhibit ${n}`, flip) : c))));
    };
    render();
    return box;
  }
  return exhibitBody(ex, n);
}

function exhibitBody(ex, n) {
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
    h("p", null, q.converted
      ? "Converted from a club casebook and kept as the casebook wrote it. Every calculation was recomputed and every exhibit total checked; the review below lists what the reviewer noticed in the casebook case itself (club casebooks often have gaps or slips), so read it before you run the case."
      : q.status === "verified"
        ? "Every calculation was recomputed from the case's own inputs, every exhibit total checked, and an independent review found no remaining errors."
        : "Some issues remain after automatic fixing. Read them before running the case."),
    h("p.muted", null, `${q.fix_rounds} automatic fix round${q.fix_rounds === 1 ? "" : "s"} · model ${q.model}`
      + (q.engine !== "strong" && ["hard", "instant_offer"].includes(difficulty) ? " · Luna's own review is lenient at this level; get a second opinion before relying on it" : ""))));
  panel.append(h("div.qcheck", null, h("h3", null, "Number checks"),
    q.checks.length ? q.checks.map(issue) : h("p", null, "All formulas compute, match their expected values, and exhibits add up.")));
  panel.append(solverBlock(q));
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

// The solver check: an agent worked the case from the candidate's materials only; code compared with the key.
function solverBlock(q) {
  const s = q.solver;
  const box = h("div.qcheck.solver-check");
  if (!s) {
    box.append(h("h3", null, "Solver check"), h("p.muted", null, "Not run for this case (it was made before the solver check was added)."));
    return box;
  }
  if (!s.total) {
    box.append(h("h3", null, "Solver check"), h("p.muted", null, `The solver check couldn't run for this case${s.error ? `: ${s.error}` : "."}`));
    return box;
  }
  const first = q.solver_first;
  const firstMissed = first && first.total ? first.total - first.solved : 0;
  box.append(...[
    h("h3", null, `Solver check · ${s.solved} of ${s.total} results reached`),
    h("p", null, "A solver agent worked this case using only what the candidate is given (the prompt, clarifying answers, shared facts and exhibits), never the answer key. Code then compared its answers with the key. A miss usually means a fact the candidate needs is missing or a question can be read two ways."),
    firstMissed ? h("p.muted", null, `Its first attempt missed ${firstMissed}; those went back to the writer before the reviews.`) : null,
    s.stale ? h("p.muted", null, "This result is from before the last fixes: the final check was skipped to stay within the case's budget.") : null,
    h("table.calc-table", null,
      h("thead", null, h("tr", null, h("th", null, "Step"), h("th", null, "Answer key"), h("th", null, "Solver"), h("th", null, ""))),
      h("tbody", null, s.results.flatMap((r) => [
        h("tr", null, h("td", null, r.label), h("td.result", null, r.expected), h("td", null, r.solver ?? "—"),
          h("td", null, r.ok ? "✓" : "✗")),
        !r.ok && (r.missing || r.working) ? h("tr.solver-note", null, h("td", { colspan: "4" },
          r.missing ? `Solver: ${r.missing}` : `Solver's working: ${r.working}`)) : null,
      ].filter(Boolean))))].filter(Boolean));
  return box;
}

// ------------------------------------------------------------------ problem reports ("flag an error")

const FLAG_LABELS = {
  math: "A number or the answer key is wrong",
  missing: "Information I needed wasn't given",
  unclear: "A question or exhibit is unclear",
  exhibit: "An exhibit is wrong or hard to read",
  interviewer: "Handsome Dan did something wrong",
  other: "Something else",
};

// A small modal: pick a category, add an optional note, send. `submit` posts it and may throw.
function openFlagDialog(title, submit, categories = Object.keys(FLAG_LABELS)) {
  const sel = h("select", null, categories.map((k) => h("option", { value: k }, FLAG_LABELS[k])));
  const note = h("textarea", { rows: "3", maxlength: "500", placeholder: "What's wrong? e.g. “Exhibit 2's total doesn't match its rows.”" });
  const err = h("p.form-error");
  err.hidden = true;
  const sendBtn = h("button.btn.btn-primary", { type: "button" }, "Send report");
  const close = () => { box.remove(); document.body.classList.remove("viewer-open"); };
  const box = h("div.ex-viewer.flag-dialog", { role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div.flag-panel.card", null,
      h("h3.card-title", null, title),
      h("label.field", null, "What kind of problem?", sel),
      h("label.field", null, "Details (optional)", note),
      h("p.muted.small", null, "Open reports are shown to the reviewer agent when new cases are written, so the same kind of problem gets caught next time."),
      err,
      h("div.job-actions", null, h("button.btn.btn-ghost", { type: "button", onclick: close }, "Cancel"), sendBtn)));
  sendBtn.addEventListener("click", async () => {
    sendBtn.disabled = true;
    err.hidden = true;
    try {
      await submit({ category: sel.value, note: note.value.trim() });
      close();
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
      sendBtn.disabled = false;
    }
  });
  box.addEventListener("click", (ev) => { if (ev.target === box) close(); });
  box.addEventListener("keydown", (ev) => { if (ev.key === "Escape") close(); });
  document.body.append(box);
  document.body.classList.add("viewer-open");
  sel.focus();
}

function flagsBlock(data) {
  const flags = data.flags || [];
  const open = flags.filter((f) => !f.resolved).length;
  const box = h("div.qcheck.flags-check", null, h("h3", null, open ? `User reports · ${open} open` : "User reports"));
  if (!flags.length) {
    box.append(h("p.muted", null, "No problems reported yet. Use “Flag a problem” if you find one."));
    return box;
  }
  for (const f of flags.slice().reverse()) {
    box.append(h("div.issue" + (f.resolved ? ".minor.resolved" : ".major"), null,
      h("b", null, f.resolved ? "resolved" : "open"),
      `${FLAG_LABELS[f.category] || f.category}${f.where ? ` (${f.where})` : ""}${f.note ? `: ${f.note}` : ""}`,
      h("span.muted", null, ` · ${new Date(f.at).toLocaleDateString()}`), " ",
      h("button.link-btn", { type: "button", onclick: async () => {
        await api(`/api/cases/${data.id}/flags/${f.id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resolved: !f.resolved }) });
        await openCase(data.id);
        document.querySelector('.tab[data-tab="quality"]').click();
      } }, f.resolved ? "Reopen" : "Mark resolved")));
  }
  return box;
}

function flagCase(id) {
  openFlagDialog("Flag a problem with this case", async (body) => {
    await api(`/api/cases/${id}/flags`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, where: "Library" }) });
    await openCase(id);
    document.querySelector('.tab[data-tab="quality"]').click();
  }, Object.keys(FLAG_LABELS).filter((k) => k !== "interviewer"));
}

// ------------------------------------------------------------------ live partner mode (interviewer side)

let liveState = null;

async function startLive(caseId) {
  try {
    liveState = await api("/api/live", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ case_id: caseId }) });
    renderLivePanel();
    $("#live-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    $("#saved-note").textContent = `Couldn't start a live case: ${err.message}`;
  }
}

async function liveUpdate(path, body) {
  try {
    liveState = await api(`/api/live/${liveState.token}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (err) {
    alert(`Couldn't update the candidate's screen: ${err.message}`);
  }
  renderLivePanel();
}

function linkRow(label, url) {
  return h("div.live-link", null, h("span.live-link-label", null, label),
    h("a", { href: url, target: "_blank", rel: "noopener" }, url),
    h("button.link-btn", { type: "button", onclick: (ev) => { navigator.clipboard?.writeText(url); ev.currentTarget.textContent = "Copied"; } }, "Copy"));
}

function renderLivePanel() {
  const box = $("#live-panel");
  if (!box || !liveState) return;
  const s = liveState;
  box.hidden = false;
  box.replaceChildren(
    h("div.live-head", null, h("h3.card-title", null, "Live case: the candidate's screen"),
      h("button.link-btn", { type: "button", onclick: () => { liveState = null; box.hidden = true; } }, "Close")),
    h("div.live-grid", null,
      h("img.live-qr", { src: s.qr, alt: "QR code that opens the candidate's screen", width: "150", height: "150" }),
      h("div", null,
        h("p", null, "Your candidate scans this or opens the link. They see only what you show them below: never the guide, the answers or the case title."),
        s.lan_ready ? linkRow("Phone or computer on this Wi-Fi", s.lan_url)
          : h("p.muted.small", null, s.lan_url
            ? "To use a phone, restart the server with --host 0.0.0.0 (see the README). Until then the QR code opens it on this computer, for example in a second window on another screen."
            : "This computer isn't on a network, so use a second window on this computer."),
        linkRow("This computer", s.local_url))),
    h("div.live-controls", null,
      h("button.btn" + (s.prompt_shown ? ".btn-ghost" : ".btn-primary.btn-inline"), { type: "button", onclick: () => liveUpdate("/prompt", { shown: !s.prompt_shown }) },
        s.prompt_shown ? "✓ Prompt shown · hide it" : "Show the prompt on their screen"),
      ...s.exhibits.map((e) => h("button.btn.btn-ghost.live-ex" + (e.released ? ".released" : ""), {
        type: "button", title: e.released ? "Take this exhibit back" : `Hand this exhibit over${e.part ? ` (used in part ${e.part})` : ""}`,
        onclick: () => liveUpdate(`/exhibits/${e.id}`, { released: !e.released }),
      }, `${e.released ? "✓ " : ""}Exhibit ${e.number}${e.part ? ` · part ${e.part}` : ""}`))));
}

// ------------------------------------------------------------------ printing without the server

// The browser's own print dialog saves the full document (guide, then handouts) as a PDF. Works
// everywhere, including servers that can't print PDFs themselves.
function printCase(id) {
  window.open(`/?print=${encodeURIComponent(id)}&dialog=1`, "_blank");
}

function serverPdf() {
  return typeof options === "undefined" || !options || options.server_pdf !== false;
}

function pdfFallback(id, message) {
  $("#saved-note").replaceChildren(`${message} `,
    h("button.link-btn", { type: "button", onclick: () => printCase(id) }, "Use your browser's Print / Save as PDF instead"));
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
    data.source && data.source.kind === "casebook"
      ? h("div.case-source", null, `Converted from the ${data.source.school} casebook${data.source.year ? ` (${data.source.year})` : ""}: “${data.source.title}”. Stays on this computer.`)
      : null,
    h("div.case-actions", null,
      h("button.btn.btn-ghost", { type: "button", title: "Run this case with a partner: they see the prompt and exhibits on their own screen when you hand them over", onclick: () => startLive(data.id) }, "Give this case live"),
      h("button.btn.btn-ghost", { type: "button", onclick: () => startPractice({ case_id: data.id }) }, "Practice this case with Handsome Dan"),
      h("button.btn.btn-ghost", { type: "button", title: "Opens the full document (guide, then handouts) in your browser's print dialog, where you can save it as a PDF", onclick: () => printCase(data.id) }, "Print / Save as PDF"),
      serverPdf() ? h("button.btn.btn-ghost", { type: "button", onclick: (ev) => savePdf(data.id, ev.currentTarget) },
        data.pdf ? "Re-save PDF" : "Save PDF to Generated Cases") : null,
      serverPdf() ? h("button.btn.btn-ghost", { type: "button", title: "Choose where on your computer to save the PDF", onclick: (ev) => savePdfAs(data.id, ev.currentTarget) }, "Save PDF as…") : null,
      q.engine === "strong" ? null : h("button.btn.btn-ghost", { type: "button", title: "One independent review by the stronger model (gpt-5.6-terra), about $0.05. Nothing is rewritten.", onclick: (ev) => secondOpinion(data.id, ev.currentTarget) },
        data.second_opinion ? "New second opinion" : "Second opinion (Terra, ~5¢)"),
      h("button.btn.btn-ghost", { type: "button", onclick: () => flagCase(data.id) }, "⚑ Flag a problem"),
      h("button.btn.btn-ghost.btn-danger", { type: "button", onclick: () => removeCase(data.id) }, "Delete")),
    h("p.saved-note", { id: "saved-note" }, data.pdf ? `Saved to Generated Cases as “${data.pdf}”` : ""));
  const livePanel = h("section.live-panel.card", { id: "live-panel" });
  livePanel.hidden = true;

  const quality = qualityPanel(q, data.usage, data.second_opinion, c.difficulty);
  quality.insertBefore(flagsBlock(data), quality.children[1] || null);
  const panels = [guidePanel(c), handoutPanel(c), quality];
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
  root.append(head, livePanel, tabs, ...panels);
  select("guide");
  if (liveState && liveState.case_id === data.id) renderLivePanel(); // keep the live controls across re-renders
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
    pdfFallback(id, `Couldn't save the PDF: ${err.message}`);
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
    pdfFallback(id, `Couldn't save the PDF: ${err.message}`);
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
  // Opened by "Print / Save as PDF": go straight to the browser's print dialog once it's laid out.
  if (new URLSearchParams(location.search).get("dialog")) {
    await document.fonts?.ready;
    setTimeout(() => window.print(), 250);
  }
}

