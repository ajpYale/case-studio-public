// Live partner mode, the candidate's screen: shows the prompt and the exhibits the interviewer has
// handed over, and nothing else. Read-only; checks for changes every two seconds.
"use strict";

const liveToken = location.pathname.split("/").filter(Boolean).pop();
let liveSig = "";
const liveSeen = new Set(); // exhibits already on screen; anything else is highlighted as new

function renderCandidate(v) {
  $("#live-level").className = v.difficulty ? `pill pill-${v.difficulty}` : "pill";
  $("#live-level").textContent = LEVEL[v.difficulty] || v.difficulty || "";
  $("#live-level").hidden = !v.difficulty;
  $("#live-client").textContent = v.client;
  $("#live-industry").textContent = v.industry ? `· ${v.industry}` : "";
  $("#live-prompt").replaceChildren(v.prompt
    ? h("div.readaloud", null, h("span.readaloud-label", null, "Case prompt"), v.prompt)
    : h("p.muted", null, "Your interviewer will share the case prompt here when you start."));
  const fresh = new Set(v.exhibits.filter((e) => !liveSeen.has(e.id)).map((e) => e.id));
  const list = v.exhibits.slice().reverse(); // newest first, so a new handout is at the top
  $("#live-exhibits").replaceChildren(...(list.length
    ? list.map((e) => h("div.card.live-exhibit" + (fresh.has(e.id) ? ".new" : ""), null, exhibitBlock(e, e.number)))
    : [h("p.muted.live-empty", null, "No exhibits yet. They'll appear here as soon as your interviewer hands them over.")]));
  if (fresh.size) window.scrollTo({ top: $("#live-exhibits").offsetTop - 12, behavior: "smooth" });
  liveSeen.clear(); // only what's on screen now, so an exhibit taken back and handed over again counts as new
  v.exhibits.forEach((e) => liveSeen.add(e.id));
}

async function pollLive() {
  try {
    const v = await api(`/api/live/${liveToken}`);
    const sig = JSON.stringify([v.prompt, v.exhibits.map((e) => e.id)]);
    if (sig !== liveSig) {
      const first = !liveSig;
      liveSig = sig;
      if (first) v.exhibits.forEach((e) => liveSeen.add(e.id)); // don't flash what was already there on load
      renderCandidate(v);
    }
    $("#live-status").textContent = "Connected · updates appear automatically";
  } catch (err) {
    $("#live-status").textContent = `Reconnecting… (${err.message})`;
  }
  setTimeout(pollLive, 2000);
}

document.addEventListener("DOMContentLoaded", pollLive);
