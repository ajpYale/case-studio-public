// McKennel & Co. shell: run room (parallel generations with live cost), library, and practice with Handsome Dan.
// Needs case_view.js (h, api, renderCase, exhibitBlock, ...) loaded first.
"use strict";

const TIER = { easy: "Puppy", medium: "Bulldog", hard: "Top Dog", instant_offer: "Handsome Dan" };
// Typical number of progress stages per level (measured), for the progress bars.
const EXPECTED_STAGES = { easy: 8, medium: 10, hard: 12, instant_offer: 15 };

let options = null;
let currentId = null;
let previousView = "library";
let jobsTimer = null;
let libLevel = "";
let practiceLevel = "";
let session = null;
let sessionBusy = false;
const sessionJobs = new Set(); // jobs started from this browser tab, for the session KPIs

// ---------------------------------------------------------------- navigation

function showView(name) {
  for (const v of ["run", "library", "case", "practice"]) $(`#view-${v}`).hidden = v !== name;
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name
    || (name === "case" && b.dataset.view === previousView)));
  if (name === "library") loadLibrary();
  if (name === "run") pollJobs(true);
  if (name === "practice") renderPracticeHome();
  window.scrollTo({ top: 0 });
}

function go(name) {
  if (name !== "case") previousView = name;
  history.replaceState(null, "", name === "run" ? "/" : `/#${name}`);
  showView(name);
}

// ---------------------------------------------------------------- options, spend

async function loadOptions() {
  options = await api("/api/options");
  const fill = (sel, items) => {
    for (const it of items) {
      const value = typeof it === "string" ? it : it.value;
      const label = typeof it === "string" ? it : it.label;
      sel.append(h("option", { value }, label));
    }
  };
  fill($("#case_type"), options.case_types);
  fill($("#industry"), options.industries);
  fill($("#format"), options.formats);
  document.querySelectorAll('input[name="difficulty"], input[name="engine"]').forEach((el) =>
    el.addEventListener("change", updateEngineHint));
  updateEngineHint();
  const b = options.built_from;
  if (b.starter || !b.cases) {
    $("#built-from").textContent = "Running on the starter knowledge pack";
    $("#empty-built").textContent = "Every case here passed the code checks and an independent review.";
  } else {
    $("#built-from").textContent = `Trained on ${b.cases} cases from ${b.casebooks} casebooks`;
    $("#empty-built").textContent = `Every case here passed the code checks and an independent review. Built from ${b.cases} audited cases across ${b.casebooks} MBA casebooks.`;
  }
}

function engineOf(value) {
  return options.engines.find((e) => e.value === value) || options.engines[0];
}

function selected(name) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : null;
}

function updateEngineHint() {
  if (!options) return;
  const level = selected("difficulty");
  const eng = engineOf(selected("engine"));
  const parts = [`Every step runs on ${eng.models[level]}.`];
  if (eng.value === "luna" && level !== "easy") {
    parts.push(level === "medium"
      ? "About 3¢ per case. Luna is reliable at this level: both Medium test cases passed an independent stronger-model review."
      : "A few cents per case, but not reliable at this level: in testing, 5 of 7 Luna Hard and Instant Offer cases still had a major issue a stronger model caught. Use Second opinion (~5¢) on the result, or the Stronger engine.");
  }
  if (eng.confirm_levels.includes(level)) parts.push("Expensive: you'll be asked to confirm before every run.");
  $("#engine-hint").textContent = parts.join(" ");
  $("#engine-hint").classList.toggle("warn", eng.confirm_levels.includes(level));
  const n = count();
  $("#gen-btn").textContent = n === 1 ? "Generate case" : `Generate ${n} cases`;
}

async function refreshSpend() {
  try {
    const b = await api("/api/budget");
    const pct = Math.min(100, (100 * b.spent_today_usd) / b.daily_budget_usd);
    $("#spend-pill").replaceChildren(`Today $${b.spent_today_usd.toFixed(2)} of $${b.daily_budget_usd.toFixed(0)}`,
      h("span.bar", null, h("i", { style: `width:${pct}%` })));
    $("#budget").textContent = `Per-case cap $${b.max_usd_per_case.luna.toFixed(2)} (Luna) / $${b.max_usd_per_case.strong.toFixed(2)} (Stronger) · daily cap $${b.daily_budget_usd.toFixed(2)}`;
  } catch { /* informational */ }
}

// ---------------------------------------------------------------- run room

function count() {
  const n = parseInt($("#count").value, 10);
  return Math.max(1, Math.min(6, Number.isFinite(n) ? n : 1));
}

function setCount(n) {
  $("#count").value = Math.max(1, Math.min(6, n));
  updateEngineHint();
}

function formBody() {
  const fd = new FormData($("#gen-form"));
  const body = { difficulty: fd.get("difficulty"), engine: fd.get("engine") || "luna" };
  for (const k of ["case_type", "industry", "format", "notes"]) {
    const v = (fd.get(k) || "").toString().trim();
    if (v) body[k] = v;
  }
  return body;
}

async function submitJobs(bodies) {
  $("#form-error").hidden = true;
  const sol = bodies.filter((b) => engineOf(b.engine).confirm_levels.includes(b.difficulty));
  if (sol.length) {
    const model = engineOf(sol[0].engine).models[sol[0].difficulty];
    // Expensive models need an explicit yes on every run, never remembered between runs.
    const ok = confirm(`${sol.length} of these case${sol.length === 1 ? "" : "s"} run on ${model}, the most expensive model.\n\n` +
      "Each makes many model calls and takes 8–20 minutes.\n\nGenerate and charge them to your Portkey key?");
    if (!ok) return;
    sol.forEach((b) => { b.confirm_cost = true; });
  }
  $("#gen-btn").disabled = true;
  const errors = [];
  for (const body of bodies) {
    try {
      const { job_id } = await api("/api/cases", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      sessionJobs.add(job_id);
    } catch (err) {
      errors.push(err.message);
      break; // refusals (queue full, budget, blocked notes) apply to the rest too
    }
  }
  $("#gen-btn").disabled = false;
  if (errors.length) {
    $("#form-error").textContent = `${bodies.length > 1 ? "Some cases weren't started. " : "Not started. "}${errors[0]}`;
    $("#form-error").hidden = false;
  }
  pollJobs(true);
}

function money(x) {
  return x < 0.1 ? `$${x.toFixed(3)}` : `$${x.toFixed(2)}`;
}

function kTok(x) {
  return x >= 1000 ? `${(x / 1000).toFixed(x >= 100000 ? 0 : 1)}K` : `${x}`;
}

function clock(sec) {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function jobCard(j) {
  const done = j.status === "done";
  const flagged = done && j.quality && j.quality !== "verified";
  const cls = `job.${j.status}${done ? (flagged ? ".flagged" : ".verified") : ""}`;
  const stages = j.stages.map((s) => s.stage);
  const pct = done ? 100 : Math.min(95, (100 * stages.length) / (EXPECTED_STAGES[j.difficulty] || 10));
  const cur = j.current;
  let step;
  if (j.status === "queued") step = h("div.job-step", null, `Waiting for a free slot · ${clock(j.waited)}`);
  else if (j.status === "running") {
    step = h("div.job-step", null, h("span.pulse"),
      cur ? `${cur.step} · ${cur.role} · ${Math.round(cur.seconds)} s${cur.retry ? ` · gateway retry ${cur.retry}` : ""}`
        : (stages[stages.length - 1] || "Starting"));
  } else if (done) {
    step = h("div.job-step", null, h("span.quality-badge." + (j.quality || "verified"), null,
      h("span.dot.dot-" + (j.quality || "verified")), STATUS[j.quality] || "Done"), `· ${j.fix_rounds ?? 0} fix rounds`);
  } else step = h("div.job-error", null, j.error || "Failed");
  const costPct = j.budget_usd ? Math.min(100, (100 * j.usd) / j.budget_usd) : 0;
  return h("article." + cls, null,
    h("div.job-top", null,
      h("span", null, h("span.pill.pill-" + j.difficulty, null, LEVEL[j.difficulty]), ` ${TIER[j.difficulty]}`),
      h("span", null, `${j.model || ""} · ${clock(j.elapsed)}`)),
    h("div.job-title" + (j.title ? "" : ".pending"), null, j.title || (j.status === "queued" ? "In the queue" : "Writing a new case…")),
    step,
    h("div.job-bar", null, h("i", { style: `width:${pct}%` })),
    h("div.job-metrics", null,
      h("div", null, h("b", null, money(j.usd)), "cost"),
      h("div", null, h("b", null, `${j.calls}`), "model calls"),
      h("div", null, h("b", null, `${kTok(j.input)} / ${kTok(j.output)}`), "tokens in / out"),
      h("div", null, h("b", null, j.input ? `${Math.round((100 * j.cached) / j.input)}%` : "–"), "cached")),
    h("div.job-cost-bar", { title: `Cost against this case's $${(j.budget_usd || 0).toFixed(2)} cap` }, h("i", { style: `width:${costPct}%` })),
    stages.length && !done && j.status !== "error" ? h("ol.job-stages", null, stages.map((s) => h("li", null, s))) : null,
    done ? h("div.job-actions", null,
      h("button.btn.btn-ghost", { type: "button", onclick: () => openCase(j.case_id) }, "Open case"),
      h("button.btn.btn-ghost", { type: "button", onclick: () => startPractice({ case_id: j.case_id }) }, "Practice it")) : null);
}

function renderKpis(data) {
  const mine = data.jobs.filter((j) => sessionJobs.has(j.id));
  const all = data.jobs;
  const running = all.filter((j) => j.status === "running").length;
  const queued = all.filter((j) => j.status === "queued").length;
  const done = mine.filter((j) => j.status === "done");
  const spent = mine.reduce((a, j) => a + (j.usd || 0), 0);
  const avg = done.length ? done.reduce((a, j) => a + j.usd, 0) / done.length : 0;
  const k = (v, l) => h("div.k", null, h("b", null, v), h("span", null, l));
  $("#kpi-strip").replaceChildren(
    k(`${running} / ${data.parallel}`, "running / parallel slots"),
    k(`${queued}`, "waiting in line"),
    k(`${done.length}`, "finished this session"),
    k(money(spent), "spent this session"),
    k(done.length ? money(avg) : "–", "average per finished case"));
}

async function pollJobs(immediate) {
  clearTimeout(jobsTimer);
  const tick = async () => {
    let data;
    try { data = await api("/api/jobs"); } catch { jobsTimer = setTimeout(tick, 4000); return; }
    renderKpis(data);
    $("#jobs").replaceChildren(...data.jobs.map(jobCard));
    $("#jobs-empty").hidden = data.jobs.length > 0;
    const active = data.jobs.some((j) => j.status === "running" || j.status === "queued");
    refreshSpend();
    if (active || !$("#view-run").hidden) jobsTimer = setTimeout(tick, active ? 1500 : 6000);
  };
  if (immediate) tick(); else jobsTimer = setTimeout(tick, 1500);
}

// ---------------------------------------------------------------- library + case

async function loadLibrary() {
  const items = await api("/api/cases");
  const grid = $("#library");
  const shown = items.filter((it) => !libLevel || it.difficulty === libLevel);
  if (!shown.length) {
    grid.replaceChildren(h("p.muted", null, items.length ? "No cases at this level yet." : "Generated cases will appear here."));
    return;
  }
  grid.replaceChildren(...shown.map((it) => h("article.lib-card", null,
    h("div.badges", null, h("span.pill.pill-" + it.difficulty, null, LEVEL[it.difficulty]),
      h("span.badge", null, TIER[it.difficulty]),
      h("span.badge" + (it.status === "verified" ? ".ok" : ".warn"), null, STATUS[it.status] || it.status),
      it.second_opinion === null || it.second_opinion === undefined
        ? h("span.badge", { title: "Open the case and click Second opinion for an independent Terra review (~5¢)" }, "No second opinion yet")
        : h("span.badge" + (it.second_opinion ? ".warn" : ".ok"), null, it.second_opinion ? `Second opinion: ${it.second_opinion} major` : "Second opinion: clean")),
    h("h3", null, it.title),
    h("div.meta", null, `${it.client} · ${it.industry}`),
    h("p.summary", null, it.summary || ""),
    h("div.actions", null,
      h("button.btn.btn-ghost", { type: "button", onclick: () => openCase(it.id) }, "Open"),
      h("button.btn.btn-ghost", { type: "button", onclick: () => startPractice({ case_id: it.id }) }, "Practice with Handsome Dan")))));
}

async function openCase(id) {
  let data;
  try {
    data = await api(`/api/cases/${id}`);
  } catch (err) {
    alert(`Couldn't open that case: ${err.message}`);
    return;
  }
  currentId = id;
  renderCase(data);
  showView("case");
}

// ---------------------------------------------------------------- practice with Handsome Dan

function danAvatar() {
  const a = danEl(36);
  a.classList.add("avatar");
  return a;
}

function renderPracticeHome() {
  if (session && session.status !== "scored") {
    renderInterview();
    return;
  }
  if (session && session.status === "scored") {
    renderScorecard();
    return;
  }
  $("#practice-start").hidden = false;
  $("#interview").hidden = true;
  $("#scorecard").hidden = true;
  const last = localStorage.getItem("practiceSession");
  $("#practice-resume").replaceChildren(last ? h("button.link-btn", { type: "button", onclick: () => resumePractice(last) }, "Resume your last interview") : "");
}

function practiceEngine() {
  return localStorage.getItem("ivEngine") || "luna";
}

async function startPractice(req) {
  req = { engine: practiceEngine(), ...req };
  go("practice");
  $("#practice-error").hidden = true;
  $("#practice-go").disabled = true;
  $("#practice-go").textContent = "Handsome Dan is sniffing out a case…";
  try {
    session = await api("/api/practice", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    localStorage.setItem("practiceSession", session.id);
    lastSpoken = -1;
    renderInterview();
    speakLatest();
  } catch (err) {
    $("#practice-error").textContent = err.message;
    $("#practice-error").hidden = false;
  } finally {
    $("#practice-go").disabled = false;
    $("#practice-go").textContent = "Give me a case";
  }
}

async function resumePractice(id) {
  try {
    session = await api(`/api/practice/${id}`);
    session.status === "scored" ? renderScorecard() : renderInterview();
  } catch {
    localStorage.removeItem("practiceSession");
    renderPracticeHome();
  }
}

function renderInterview() {
  $("#practice-start").hidden = true;
  $("#scorecard").hidden = true;
  $("#interview").hidden = false;
  const s = session;
  $("#iv-level").className = "pill pill-" + s.difficulty;
  $("#iv-level").textContent = `${LEVEL[s.difficulty]} · ${TIER[s.difficulty]}${s.engine === "strong" ? " · Stronger interviewer" : ""}`;
  $("#iv-client").textContent = s.client;
  $("#iv-industry").textContent = `· ${s.industry}`;
  $("#iv-progress").replaceChildren(...Array.from({ length: s.section_count }, (_, i) =>
    h("i" + (i + 1 < s.section_number ? ".done" : i + 1 === s.section_number ? ".now" : ""), { title: `Part ${i + 1} of ${s.section_count}` })));
  const msgs = $("#messages");
  msgs.replaceChildren(...s.transcript.map((t) => message(t)));
  if (sessionBusy) msgs.append(h("div.msg.dan.typing", null, danAvatar(), h("div.bubble", null, "Handsome Dan is thinking…")));
  msgs.scrollTop = msgs.scrollHeight;
  const u = s.usage;
  const row = (l, v) => h("div.meter-row", null, h("span", null, l), h("b", null, v));
  $("#iv-meter").replaceChildren(h("h3.card-title", null, "This interview"),
    row("Part", `${s.section_number} of ${s.section_count}`),
    row("Your messages", `${s.candidate_turns}`),
    row("Model calls", `${u.calls} on ${u.model}`),
    row("Tokens in / out", `${kTok(u.input)} / ${kTok(u.output)} (${u.input ? Math.round((100 * u.cached) / u.input) : 0}% cached)`),
    row("Cost so far", `${money(u.usd)} of $${u.budget_usd.toFixed(2)} cap`),
    row("Answer leaks blocked", `${s.leaks_blocked}`),
    row("Coaching questions removed", `${s.questions_blocked || 0}`));
  const ex = $("#iv-exhibits");
  ex.replaceChildren(...(s.exhibits.length ? s.exhibits.map((e, i) => h("div.ex-thumb", null,
    h("button.btn.btn-ghost.enlarge-btn", { type: "button", title: "Open this exhibit full size", onclick: () => openExhibitViewer(i) }, "⤢ Enlarge"),
    (() => { const blk = exhibitBlock(e, e.number); blk.addEventListener("click", () => openExhibitViewer(i)); return blk; })()))
    : [h("p.muted.small", null, "Handsome Dan hands these over as you reach them.")]));
  const finished = s.status === "complete";
  $("#composer-text").disabled = sessionBusy || finished;
  $("#send-btn").disabled = sessionBusy || finished;
  $("#hint-btn").disabled = sessionBusy || finished;
  $("#skip-btn").disabled = sessionBusy || finished;
  $("#skip-btn").textContent = s.section_number >= s.section_count ? "Skip and end the case" : "Skip to the next part";
  $("#mic-btn").disabled = sessionBusy || finished;
  $("#score-btn").disabled = sessionBusy || (s.candidate_turns === 0 && !finished);
  $("#score-btn").classList.toggle("btn-primary", finished);
  if (!sessionBusy && !finished) $("#composer-text").focus();
}

function message(t) {
  if (t.skipped) return h("div.msg-note", null, "You skipped this part without answering.");
  const dan = t.role === "interviewer";
  const handed = (t.exhibits || []).length
    ? h("div.handed", null, `Handed over: ${t.exhibits.map((id) => {
      const e = session.exhibits.find((x) => x.id === id);
      return e ? `Exhibit ${e.number}` : id;
    }).join(", ")}`) : null;
  return h("div.msg" + (dan ? ".dan" : ".me"), null,
    dan ? danAvatar() : null,
    h("div", null, h("div.bubble", null, t.text), handed));
}

// ---- voice: dictate replies (speech-to-text) and hear Handsome Dan (text-to-speech).
// Both use the browser's built-in speech features; nothing extra is sent to our server.
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let listening = false;
let listenToken = 0; // bumped whenever dictation is cancelled, so late results are ignored
let micWanted = false; // true while the user wants the mic on (Stop sets it false)
let lastSpoken = -1;

function setMicIdle() {
  listening = false;
  $("#mic-btn").classList.remove("listening");
  $("#mic-btn").textContent = "🎤 Speak";
}

// Cancel dictation completely: late results from the recognizer must never refill the box.
function cancelListening() {
  micWanted = false;
  listenToken++;
  if (recognizer) {
    recognizer.onresult = null;
    try { recognizer.abort(); } catch { /* already stopped */ }
    recognizer = null;
  }
  setMicIdle();
}

function toggleListening() {
  if (!Recognition) return;
  if (listening) { // "Stop": finish the current phrase, keep everything said, don't restart
    micWanted = false;
    if (recognizer) { try { recognizer.stop(); } catch { /* already stopped */ } }
    setMicIdle();
    return;
  }
  const box = $("#composer-text");
  const base = box.value ? box.value.replace(/\s*$/, " ") : "";
  const token = ++listenToken;
  let committed = "";   // everything said in earlier recognition sessions
  let quickEnds = 0;    // sessions that died right after starting (to avoid a restart loop)
  let fatal = false;

  // The browser ends a recognition session by itself after a pause or a minute or so of speech,
  // even in continuous mode. Keep listening until the user presses Stop or sends: when a session
  // ends, start a fresh one and keep what was already heard.
  const session = () => {
    const r = new Recognition();
    const startedAt = performance.now();
    let finals = "", interim = "";
    r.lang = "en-US";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (ev) => {
      if (token !== listenToken) return;
      interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finals += ` ${t}`; else interim += ` ${t}`;
      }
      box.value = (base + committed + finals + interim).replace(/\s+/g, " ").trimStart();
    };
    r.onerror = (ev) => {
      if (["not-allowed", "service-not-allowed", "audio-capture"].includes(ev.error)) {
        fatal = true;
        alert(ev.error === "audio-capture" ? "No microphone was found."
          : "Your browser blocked the microphone. Allow it for this site to speak your replies.");
      }
    };
    r.onend = () => {
      if (token !== listenToken) return;           // stopped, sent, or cancelled
      committed += finals + interim;                // keep words that hadn't been finalised yet
      quickEnds = performance.now() - startedAt < 800 ? quickEnds + 1 : 0;
      if (!micWanted || fatal || quickEnds >= 5) { listenToken++; setMicIdle(); return; }
      recognizer = session();
    };
    r.start();
    return r;
  };
  micWanted = true;
  recognizer = session();
  listening = true;
  $("#mic-btn").classList.add("listening");
  $("#mic-btn").textContent = "■ Stop";
}

// Two voices. "Regal" prefers a British male neural voice, slower and lower; "calm" a neutral
// female voice at normal pace. Falls back to whatever English voice the browser has.
const VOICE_PROFILES = {
  regal: { prefer: [/Ryan.*United Kingdom/i, /Thomas.*United Kingdom/i, /George/i, /en-GB.*(male|Ryan|Thomas)/i, /Guy/i,
    /Christopher/i, /Davis/i, /Andrew/i, /Brian/i, /David/i, /Mark/i, /Daniel/i], pitch: 0.78, rate: 0.9 },
  calm: { prefer: [/Aria/i, /Jenny/i, /Ava/i, /Emma/i, /Michelle/i, /Libby/i, /Sonia/i, /Zira/i, /Samantha/i, /Susan/i, /female/i],
    pitch: 1.0, rate: 1.0 },
};

function voiceProfile() {
  return localStorage.getItem("danVoice") || "off";
}

function pickVoice(profile) {
  const voices = (window.speechSynthesis ? speechSynthesis.getVoices() : []).filter((v) => v.lang.toLowerCase().startsWith("en"));
  for (const re of VOICE_PROFILES[profile].prefer) {
    const v = voices.find((x) => re.test(`${x.name} ${x.lang}`));
    if (v) return v;
  }
  return voices[0] || null;
}

function say(text, profile = voiceProfile()) {
  if (!window.speechSynthesis || profile === "off" || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const p = VOICE_PROFILES[profile];
  u.voice = pickVoice(profile);
  u.pitch = p.pitch;
  u.rate = p.rate;
  speechSynthesis.speak(u);
}

// After a new interviewer message: read the case prompt (the opening) or every reply, per the setting.
function speakLatest() {
  if (!session || voiceProfile() === "off") return;
  const idx = session.transcript.length - 1;
  const last = session.transcript[idx];
  if (!last || last.role !== "interviewer" || idx === lastSpoken) return;
  const scope = localStorage.getItem("danVoiceScope") || "prompt";
  if (scope === "prompt" && idx !== 0) return;
  lastSpoken = idx;
  say(last.text);
}

async function sendMessage(text) {
  if (!text.trim() || sessionBusy || !session) return;
  cancelListening();
  if (window.speechSynthesis) speechSynthesis.cancel();
  sessionBusy = true;
  session.transcript.push({ role: "candidate", text, exhibits: [] });
  $("#composer-text").value = "";
  renderInterview();
  try {
    session = await api(`/api/practice/${session.id}/message`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
  } catch (err) {
    session.transcript.push({ role: "interviewer", text: `(Couldn't reach Handsome Dan: ${err.message})`, exhibits: [] });
  } finally {
    sessionBusy = false;
    renderInterview();
    speakLatest();
    refreshSpend();
  }
}

async function skipPart() {
  if (!session || sessionBusy) return;
  cancelListening();
  if (window.speechSynthesis) speechSynthesis.cancel();
  sessionBusy = true;
  renderInterview();
  try {
    session = await api(`/api/practice/${session.id}/skip`, { method: "POST" });
  } catch (err) {
    alert(`Couldn't move on: ${err.message}`);
  } finally {
    sessionBusy = false;
    renderInterview();
    speakLatest();
  }
}

// Full-size exhibit viewer for practice: arrows flip between the exhibits handed over so far.
let viewerIndex = 0;

function openExhibitViewer(i) {
  if (!session || !session.exhibits.length) return;
  viewerIndex = Math.max(0, Math.min(i, session.exhibits.length - 1));
  let box = $("#ex-viewer");
  if (!box) {
    box = h("div.ex-viewer", { id: "ex-viewer", role: "dialog", "aria-modal": "true", "aria-label": "Exhibit" });
    box.addEventListener("click", (ev) => { if (ev.target === box) closeExhibitViewer(); });
    document.body.append(box);
  }
  renderExhibitViewer();
  box.hidden = false;
  document.body.classList.add("viewer-open");
}

function renderExhibitViewer() {
  const box = $("#ex-viewer");
  const list = session.exhibits;
  const e = list[viewerIndex];
  const many = list.length > 1;
  box.replaceChildren(h("div.ex-viewer-panel", null,
    h("div.ex-viewer-bar", null,
      h("span", null, `Exhibit ${e.number}${many ? `  ·  ${viewerIndex + 1} of ${list.length}` : ""}`),
      h("div", null,
        many ? h("button.btn.btn-ghost", { type: "button", onclick: () => stepViewer(-1), disabled: viewerIndex === 0 ? "disabled" : null }, "← Previous") : null,
        many ? h("button.btn.btn-ghost", { type: "button", onclick: () => stepViewer(1), disabled: viewerIndex === list.length - 1 ? "disabled" : null }, "Next →") : null,
        h("button.btn.btn-ghost", { type: "button", onclick: closeExhibitViewer, "aria-label": "Close" }, "✕ Close"))),
    h("div.ex-viewer-body", null, exhibitBlock(e, e.number))));
}

function stepViewer(d) {
  viewerIndex = Math.max(0, Math.min(viewerIndex + d, session.exhibits.length - 1));
  renderExhibitViewer();
}

function closeExhibitViewer() {
  const box = $("#ex-viewer");
  if (box) box.hidden = true;
  document.body.classList.remove("viewer-open");
}

document.addEventListener("keydown", (ev) => {
  const box = $("#ex-viewer");
  if (!box || box.hidden) return;
  if (ev.key === "Escape") closeExhibitViewer();
  if (ev.key === "ArrowRight") stepViewer(1);
  if (ev.key === "ArrowLeft") stepViewer(-1);
});

async function scoreSession() {
  if (!session || sessionBusy) return;
  sessionBusy = true;
  $("#score-btn").textContent = "Scoring…";
  renderInterview();
  try {
    session = await api(`/api/practice/${session.id}/score`, { method: "POST" });
    renderScorecard(true);
    celebrate();
  } catch (err) {
    alert(`Couldn't score the interview: ${err.message}`);
  } finally {
    sessionBusy = false;
    $("#score-btn").textContent = "Score my case";
    refreshSpend();
  }
}

function stars(n) {
  return h("span.stars", null, "★".repeat(n), h("span.off", null, "★".repeat(5 - n)));
}

const VERDICT_KIND = {
  Offer: "Offer-ready. Handsome Dan is very proud of you.",
  Strong: "Strong work. A little polish and you're there.",
  Borderline: "You're close. A couple of habits will get you over the line.",
  "Not yet": "Not yet, and that's exactly what practice is for. Every case makes the next one easier.",
};

// A short burst of Yale-blue confetti when the scorecard appears (skipped for reduced motion).
function celebrate() {
  if (DAN_REDUCED) return;
  const layer = h("div.confetti", { "aria-hidden": "true" });
  const colors = ["#00356b", "#286dc0", "#63aaff", "#ffffff", "#978d85"];
  for (let i = 0; i < 70; i++) {
    const bit = h("i");
    bit.style.left = `${Math.random() * 100}%`;
    bit.style.background = colors[i % colors.length];
    bit.style.animationDelay = `${Math.random() * 0.6}s`;
    bit.style.animationDuration = `${2.2 + Math.random() * 1.6}s`;
    bit.style.transform = `rotate(${Math.random() * 360}deg)`;
    layer.append(bit);
  }
  document.body.append(layer);
  setTimeout(() => layer.remove(), 4500);
}

function renderScorecard(fresh = false) {
  $("#practice-start").hidden = true;
  $("#interview").hidden = true;
  const box = $("#scorecard");
  box.hidden = false;
  const c = session.scorecard;
  const verdictCls = c.verdict.split(" ")[0];
  box.replaceChildren(
    h("div.congrats", null, danEl(40), h("span", null, "Congratulations on finishing the case!")),
    h("div.card.score-hero", null,
      danEl(92),
      h("div", null,
        h("p.eyebrow", null, `${LEVEL[session.difficulty]} · ${session.client}`),
        h("h1", null, session.title || "Your interview"),
        h("p", null, c.summary)),
      h("div", null, h("div.score-big", null, `${c.overall}`, h("small", null, "/5")), h("span.verdict." + verdictCls, null, c.verdict),
        h("p.verdict-kind", null, VERDICT_KIND[c.verdict] || ""))),
    h("div.card", null, h("h3.card-title", null, "By rubric dimension"),
      ...c.dimensions.map((d) => h("div.dim", null, h("b", null, d.dimension), stars(d.score),
        h("div", null, d.evidence, h("div.muted", null, `Next time: ${d.to_improve}`))))),
    c.math.length ? h("div.card", null, h("h3.card-title", null, "Your math"),
      h("table.calc-table", null,
        h("thead", null, h("tr", null, h("th", null, "Step"), h("th", null, "Answer key"), h("th", null, "You said"), h("th", null, ""))),
        h("tbody", null, c.math.map((m) => h("tr", null, h("td", null, m.step), h("td.result", null, m.expected),
          h("td", null, m.candidate ?? "—"), h("td", null, m.correct === true ? "✓" : m.correct === false ? "✗" : "not attempted")))))) : null,
    h("div.two-col", null,
      h("div.card", null, h("h3.card-title", null, "What went well"), list(c.strengths)),
      h("div.card", null, h("h3.card-title", null, "Next time, try"), list(c.improvements))),
    h("details.card.transcript", null, h("summary", null, `The interview (${session.transcript.length} messages)`),
      h("div.messages.read-only", null, session.transcript.map((t) => message(t)))),
    h("div.card", null,
      h("p.muted.small", null, `This interview: ${session.usage.calls} model calls, ${kTok(session.usage.input)} input and ${kTok(session.usage.output)} output tokens, ${money(session.usage.usd)}.`),
      h("div.job-actions", null,
        session.case_id ? h("button.btn.btn-ghost", { type: "button", onclick: () => openCase(session.case_id) }, "Open the interviewer guide") : null,
        h("button.btn.btn-primary", { type: "button", onclick: () => { session = null; localStorage.removeItem("practiceSession"); renderPracticeHome(); } }, "Practice another case"))));
}

// ---------------------------------------------------------------- boot

function wire() {
  document.querySelectorAll(".nav-btn").forEach((b) => b.addEventListener("click", () => go(b.dataset.view)));
  $("#gen-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const body = formBody();
    submitJobs(Array.from({ length: count() }, () => ({ ...body })));
  });
  $("#count-minus").addEventListener("click", () => setCount(count() - 1));
  $("#count-plus").addEventListener("click", () => setCount(count() + 1));
  $("#count").addEventListener("change", () => setCount(count()));
  $("#one-of-each").addEventListener("click", () => {
    const body = formBody();
    submitJobs(["easy", "medium", "hard", "instant_offer"].map((d) => ({ ...body, difficulty: d })));
  });
  $("#case-back").addEventListener("click", () => go(previousView));
  // Closing "More options" puts every option back to its default.
  $("details.more").addEventListener("toggle", (ev) => {
    if (ev.target.open) return;
    ev.target.querySelectorAll("select").forEach((s) => { s.selectedIndex = 0; });
    ev.target.querySelectorAll("textarea").forEach((t) => { t.value = ""; });
  });
  document.querySelectorAll("#lib-filter .chip").forEach((c) => c.addEventListener("click", () => {
    libLevel = c.dataset.level;
    document.querySelectorAll("#lib-filter .chip").forEach((x) => x.classList.toggle("active", x === c));
    loadLibrary();
  }));
  document.querySelectorAll("#practice-level .chip").forEach((c) => c.addEventListener("click", () => {
    practiceLevel = c.dataset.level;
    document.querySelectorAll("#practice-level .chip").forEach((x) => x.classList.toggle("active", x === c));
  }));
  $("#practice-go").addEventListener("click", () => startPractice(practiceLevel ? { difficulty: practiceLevel } : {}));
  document.querySelectorAll('input[name="iv-engine"]').forEach((el) => {
    el.checked = el.value === practiceEngine();
    el.addEventListener("change", () => localStorage.setItem("ivEngine", el.value));
  });
  $("#composer").addEventListener("submit", (ev) => { ev.preventDefault(); sendMessage($("#composer-text").value); });
  $("#composer-text").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); sendMessage($("#composer-text").value); }
  });
  $("#hint-btn").addEventListener("click", () => sendMessage("Could I get a hint?"));
  $("#skip-btn").addEventListener("click", skipPart);
  if (Recognition) $("#mic-btn").addEventListener("click", toggleListening);
  else { $("#mic-btn").hidden = true; }
  if (!window.speechSynthesis) $("#voice-card").hidden = true;
  $("#voice-profile").value = voiceProfile();
  $("#voice-scope").value = localStorage.getItem("danVoiceScope") || "prompt";
  $("#voice-profile").addEventListener("change", (ev) => {
    localStorage.setItem("danVoice", ev.target.value);
    if (ev.target.value === "off") { if (window.speechSynthesis) speechSynthesis.cancel(); return; }
    say(ev.target.value === "regal" ? "Good day. I am Handsome Dan, and I shall be your interviewer."
      : "Hi there. I'll read the case to you.", ev.target.value);
  });
  $("#voice-scope").addEventListener("change", (ev) => localStorage.setItem("danVoiceScope", ev.target.value));
  $("#hear-prompt").addEventListener("click", () => {
    if (!session) return;
    say(session.transcript[0].text, voiceProfile() === "off" ? "regal" : voiceProfile());
  });
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {}; // load the voice list early
  $("#score-btn").addEventListener("click", scoreSession);
  $("#iv-new").addEventListener("click", () => {
    if (!confirm("Leave this interview? You can resume it later from the Practice page.")) return;
    session = null;
    renderPracticeHome();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const printId = new URLSearchParams(location.search).get("print");
  if (printId) {
    renderPrintView(printId).catch((err) => { document.body.textContent = `Couldn't render case: ${err.message}`; });
    return;
  }
  wire();
  mountDans();
  startBuddy();
  try {
    await loadOptions();
  } catch (err) {
    $("#engine-hint").textContent = `Couldn't load options: ${err.message}`;
  }
  refreshSpend();
  const fromHash = () => {
    const v = (location.hash || "").replace("#", "");
    return ["library", "practice"].includes(v) ? v : "run";
  };
  window.addEventListener("hashchange", () => go(fromHash()));
  go(fromHash());
});
