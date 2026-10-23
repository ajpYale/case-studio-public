// Handsome Dan, alive: eyes that follow the pointer, a head that tilts toward it, blinking, and a
// small Handsome Dan who trots along the bottom of the screen after the cursor and hops when you
// click. Respects prefers-reduced-motion and can be put on a leash (hidden).
"use strict";

const DAN_QUIPS = [
  // case craft
  "Woof. Boola boola.", "Did you check the denominator?", "Bark once if your NPV is positive.",
  "Structure first. Then snacks.", "That's a nice framework. MECE? Prove it.", "Have you tried asking a clarifying question?",
  "Round numbers, please. I'm a dog.", "So what? Synthesize.", "Sit. Stay. Size the market.",
  "Pushback: are you sure about that margin?", "Good human. Now do the breakeven.", "Is that MECE, or just messy?",
  "Say your assumptions out loud.", "Always ask: so what for the client?", "I don't chase cars. I chase drivers of profit.",
  "Label your axes. Every time.", "Breakeven? I break for treats.", "Lead with the answer. Then the why.",
  "One good hypothesis beats a long list.", "Top-down first, then bottom-up.", "If a number looks weird, sanity-check it.",
  "Woof means \"walk me through your math.\"", "Every case starts with a clarifying question.", "Pause. Structure. Then speak.",
  "Don't round too early.", "Percentage points are not percent. I checked.", "Revenue is not profit. Even I know that.",
  "Ask for the data. Don't guess the data.", "Big numbers? Think in powers of ten.", "Exhibits have titles for a reason. Read them.",
  "Pushback tests conviction. Hold your ground if you're right.", "Segment the market, then multiply.",
  "Distractor data is my favorite chew toy.", "Talk to the CEO like a busy dog: one clear point.", "Slow is smooth. Smooth is fast.",
  "Summarize where you are every few minutes.", "Capacity constraints: the leash on every growth plan.",
  "Cannibalization? Not on my watch.", "Fixed costs don't wag. Variable costs do.", "Write the formula before the numbers.",
  "Check the units. Thousands and millions bite.", "A pivot is just the case asking you to sit, then roll over.",
  // Handsome Dan
  "I've seen 449 casebook cases. I've eaten three.", "Yes, I'm handsome. Focus.", "Napping is my core competency.",
  "I sit on the 50-yard line. You sit with your framework.", "Fun fact: Yale has had a Handsome Dan since 1889.",
  "My resume is one line long: \"Yale.\"", "I don't do group projects. I do group naps.",
  "Bulldog Security Forces are watching your math.", "If you nail this case, I'll let you pet me.",
  "My love language is a clean MECE tree.", "I was going to make a pivot table. I made a nap instead.",
  "Cold-call me. I dare you.", "That's a strong answer. Bark if you agree.", "Harvard who?",
];

const DAN_FLIP_LINES = ["Boola boola!", "Stuck the landing.", "10/10. The Harvard judges are furious.",
  "Handsome AND athletic.", "Still faster than your mental math.", "That's what we call a pivot."];

const DAN_REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function danMarkup(cls = "") {
  return `<svg class="dan-live ${cls}" viewBox="0 0 100 100" role="img" aria-label="Handsome Dan">
  <circle cx="50" cy="50" r="48" fill="#00356b"/>
  <circle cx="50" cy="50" r="44.5" fill="none" stroke="#63aaff" stroke-width="1.2" opacity=".55"/>
  <g class="dan-head">
    <path d="M24 34 C14 30 12 20 19 16 C25 13 33 18 36 26 C31 26 27 29 24 34 Z" fill="#b9ab9b"/>
    <path d="M76 34 C86 30 88 20 81 16 C75 13 67 18 64 26 C69 26 73 29 76 34 Z" fill="#b9ab9b"/>
    <path d="M50 21 C70 21 82 31 83 47 C84 58 82 66 77 71 C74 79 64 84 50 84 C36 84 26 79 23 71 C18 66 16 58 17 47 C18 31 30 21 50 21 Z" fill="#f4efe8"/>
    <path d="M36 30 Q50 25.5 64 30" stroke="#cbbfb2" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path d="M40 35 Q50 32 60 35" stroke="#cbbfb2" stroke-width="1.6" fill="none" stroke-linecap="round"/>
    <path d="M27 60 C27 50 38 49 50 52 C62 49 73 50 73 60 C73 72 63 78 50 78 C37 78 27 72 27 60 Z" fill="#e4d9cc"/>
    <ellipse cx="37" cy="44" rx="6.4" ry="6" fill="#fff"/>
    <ellipse cx="63" cy="44" rx="6.4" ry="6" fill="#fff"/>
    <g class="dan-pupils">
      <circle cx="37" cy="44" r="3.9" fill="#1d1d1d"/><circle cx="63" cy="44" r="3.9" fill="#1d1d1d"/>
      <circle cx="38.3" cy="42.7" r="1.2" fill="#fff"/><circle cx="64.3" cy="42.7" r="1.2" fill="#fff"/>
    </g>
    <g class="dan-lids"><ellipse cx="37" cy="44" rx="6.8" ry="6.4" fill="#f4efe8"/><ellipse cx="63" cy="44" rx="6.8" ry="6.4" fill="#f4efe8"/></g>
    <path d="M42 53 Q50 48.5 58 53 Q58 59 50 60 Q42 59 42 53 Z" fill="#1d1d1d"/>
    <path d="M50 60 L50 63.5" stroke="#1d1d1d" stroke-width="2" stroke-linecap="round"/>
    <path d="M36 66 Q50 71 64 66 Q62 74 50 75 Q38 74 36 66 Z" fill="#1d1d1d"/>
    <path d="M40.5 67.2 L42.4 62.6 L44.3 68.2 Z" fill="#fff"/><path d="M55.7 68.2 L57.6 62.6 L59.5 67.2 Z" fill="#fff"/>
    <g class="dan-shades" style="display:none">
      <rect x="27" y="38" width="20" height="11" rx="3" fill="#111"/><rect x="53" y="38" width="20" height="11" rx="3" fill="#111"/>
      <path d="M47 42 L53 42" stroke="#111" stroke-width="2.4"/>
    </g>
  </g>
  <path d="M29 82 Q50 92 71 82 L71 88 Q50 98 29 88 Z" fill="#286dc0"/>
  <text x="50" y="92.6" text-anchor="middle" font-family="Georgia, serif" font-size="9" font-weight="700" fill="#fff">Y</text>
</svg>`;
}

// A live Handsome Dan element of a given pixel size.
function danEl(size = 40, cls = "") {
  const wrap = document.createElement("span");
  wrap.className = "dan-wrap";
  wrap.style.width = wrap.style.height = `${size}px`;
  wrap.innerHTML = danMarkup(cls); // our own static markup, never model text
  return wrap;
}

// Replace every <span data-dan="64"></span> placeholder with a live Handsome Dan.
function mountDans(root = document) {
  root.querySelectorAll("[data-dan]").forEach((el) => {
    const live = danEl(parseInt(el.dataset.dan, 10) || 48, el.dataset.danClass || "");
    live.classList.add(...el.classList);  // keep the placeholder's own styling (e.g. .dan-mark)
    el.replaceWith(live);
  });
}

let danPointer = { x: window.innerWidth / 2, y: window.innerHeight / 2 };

function lookAtPointer() {
  for (const svg of document.querySelectorAll("svg.dan-live")) {
    const r = svg.getBoundingClientRect();
    if (!r.width || r.bottom < 0 || r.top > window.innerHeight) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height * 0.44;
    const dx = danPointer.x - cx, dy = danPointer.y - cy;
    const d = Math.hypot(dx, dy) || 1;
    const reach = Math.min(1, d / 220);
    const px = (dx / d) * 2.3 * reach, py = (dy / d) * 2.0 * reach;
    svg.querySelector(".dan-pupils").setAttribute("transform", `translate(${px.toFixed(2)} ${py.toFixed(2)})`);
    if (!DAN_REDUCED) {
      const tilt = Math.max(-7, Math.min(7, dx / 60));
      svg.querySelector(".dan-head").setAttribute("transform", `rotate(${tilt.toFixed(1)} 50 52)`);
    }
  }
}

// ---------------------------------------------------------------- the trotting buddy

function startBuddy() {
  if (document.body.classList.contains("print-mode") || document.getElementById("dan-buddy")) return;
  const buddy = document.createElement("div");
  buddy.id = "dan-buddy";
  buddy.innerHTML = `<div class="buddy-bubble" hidden></div>`;
  const body = danEl(62, "buddy-svg");
  body.classList.add("buddy-body");
  buddy.append(body);
  const leash = document.createElement("button");
  leash.type = "button";
  leash.className = "buddy-leash";
  leash.title = "Put Handsome Dan on a leash";
  leash.textContent = "Leash";
  buddy.append(leash);
  document.body.append(buddy);

  const unleash = document.createElement("button");
  unleash.type = "button";
  unleash.id = "dan-unleash";
  unleash.textContent = "Unleash Handsome Dan";
  document.body.append(unleash);

  let x = window.innerWidth - 110, target = x, facing = 1, hopUntil = 0, quipTimer = null;
  let flipStart = 0, clickTimer = null;
  const FLIP_MS = 950;
  const setLeashed = (on) => {
    localStorage.setItem("danLeashed", on ? "1" : "0");
    buddy.hidden = on;
    unleash.hidden = !on;
  };
  leash.addEventListener("click", (ev) => { ev.stopPropagation(); setLeashed(true); });
  unleash.addEventListener("click", (ev) => { ev.stopPropagation(); setLeashed(false); });
  setLeashed(localStorage.getItem("danLeashed") === "1");

  const say = (text) => {
    const b = buddy.querySelector(".buddy-bubble");
    b.textContent = text;
    b.hidden = false;
    clearTimeout(quipTimer);
    quipTimer = setTimeout(() => { b.hidden = true; }, 2600);
  };
  const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
  // One click: a line (after a short wait, so a double click doesn't also trigger it).
  buddy.addEventListener("click", (ev) => {
    ev.stopPropagation();
    clearTimeout(clickTimer);
    clickTimer = setTimeout(() => say(pick(DAN_QUIPS)), 260);
  });
  // Double click (on him, or on empty space anywhere on the page): a big jump and a backflip.
  const flip = () => {
    if (buddy.hidden) return;
    clearTimeout(clickTimer);
    if (DAN_REDUCED) { say(pick(DAN_FLIP_LINES)); return; }
    if (performance.now() - flipStart < FLIP_MS) return;
    flipStart = performance.now();
    setTimeout(() => say(pick(DAN_FLIP_LINES)), FLIP_MS - 150);
  };
  buddy.addEventListener("dblclick", (ev) => { ev.stopPropagation(); ev.preventDefault(); flip(); });
  document.addEventListener("dblclick", (ev) => {
    // Only empty space: not buttons, links, form fields or exhibits, and not a double-click that
    // selected a word of text.
    if (ev.target.closest && ev.target.closest("button, a, input, textarea, select, label, summary, [contenteditable], .ex-viewer")) return;
    const picked = window.getSelection ? window.getSelection().toString().trim() : "";
    if (picked) return;
    flip();
  });
  document.addEventListener("click", (ev) => {
    if (buddy.hidden || DAN_REDUCED) return;
    target = ev.clientX - 31;
    hopUntil = performance.now() + 450;
    if (Math.random() < 0.18) say(DAN_QUIPS[Math.floor(Math.random() * DAN_QUIPS.length)]);
  });

  const tick = (now) => {
    if (!buddy.hidden && !DAN_REDUCED) {
      target = Math.max(8, Math.min(window.innerWidth - 80, danPointer.x - 31));
      const step = (target - x) * 0.045;
      x += Math.abs(step) < 0.05 ? 0 : step;
      if (Math.abs(step) > 0.4) facing = step > 0 ? 1 : -1;
      const walking = Math.abs(step) > 0.35;
      const flipT = (now - flipStart) / FLIP_MS;
      const flipping = flipT >= 0 && flipT < 1;
      const hop = flipping ? Math.sin(flipT * Math.PI) * 110
        : now < hopUntil ? Math.sin(((hopUntil - now) / 450) * Math.PI) * 26 : 0;
      const bob = walking ? Math.abs(Math.sin(now / 90)) * 5 : 0;
      buddy.style.transform = `translate(${x.toFixed(1)}px, ${(-hop - bob).toFixed(1)}px)`;
      // ease the spin so it tucks at the top of the jump: one full backward rotation
      const spin = flipping ? -360 * (flipT < 0.5 ? 2 * flipT * flipT : 1 - Math.pow(-2 * flipT + 2, 2) / 2) * facing : 0;
      body.style.transform = `scaleX(${facing}) rotate(${(flipping ? spin : walking ? Math.sin(now / 90) * 4 : 0).toFixed(1)}deg)`;
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

document.addEventListener("mousemove", (ev) => {
  danPointer = { x: ev.clientX, y: ev.clientY };
  lookAtPointer();
}, { passive: true });
window.addEventListener("scroll", lookAtPointer, { passive: true });
