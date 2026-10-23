// Bulldog Security Forces: the trap page. Everything here is generated in the browser from the
// lists below. No model calls, no network, no data about the visitor leaves the page.
"use strict";

const SCHOOLS = {
  hbs: { name: "Harvard Business School", lines: [
    "HBS taught you 500 cases and not one of them was titled \"How to Be Likable.\"",
    "You learned to talk confidently for 90 seconds about a company you read about on the shuttle. Handsome Dan calls that \"a Tuesday.\"",
    "Your class participation grade was the highest thing you ever achieved, and it was mostly volume.",
    "You can't stop saying \"at HBS we\" in rooms where nobody asked.",
  ] },
  gsb: { name: "Stanford GSB", lines: [
    "You paid a quarter of a million dollars for a fleece vest and a class about your feelings. The feelings were regret.",
    "Your startup is \"Uber for houseplants\" and it has raised more money than your family has ever seen.",
    "You took Touchy Feely and the only thing you learned to touch was your seed round.",
    "Admit rate under 7%, and somehow you still got in. Statistically, Handsome Dan finds that suspicious.",
  ] },
  wharton: { name: "Wharton", lines: [
    "You can't tell anyone how you feel, but you can tell them the IRR of your feelings.",
    "Your love language is a 40-tab Excel model with circular references you refuse to fix.",
    "You went to Philadelphia for business school, which is the first bad investment your bank ever approved.",
    "You think \"work-life balance\" is a line item you can cut in a downturn.",
  ] },
  booth: { name: "Chicago Booth", lines: [
    "You still consider fun an unproven hypothesis and you're waiting for a larger sample.",
    "You ran a regression on your social life. The coefficient on \"you\" was not significant.",
    "You moved to Chicago on purpose and called the winters \"a good discipline.\"",
    "Your idea of a party is a seminar with snacks.",
  ] },
  kellogg: { name: "Kellogg", lines: [
    "You've done so many group projects you now introduce yourself as \"we.\"",
    "You're a great team player because no one at Kellogg was allowed to work alone with you.",
    "You think \"synergy\" is a personality.",
    "Your marketing degree is excellent preparation for marketing your marketing degree.",
  ] },
  columbia: { name: "Columbia Business School", lines: [
    "You live in New York, so the only thing you'll ever fully own is your student debt.",
    "\"At the very center of business\" — and somehow still running late to it.",
    "Your apartment is 300 square feet and you describe it as \"cozy, but central.\"",
    "You came for Wall Street and left with a Sweetgreen loyalty card.",
  ] },
  sloan: { name: "MIT Sloan", lines: [
    "You built a model to find friends. It returned NaN.",
    "Your idea of small talk is explaining the difference between machine learning and \"real\" machine learning.",
    "You have a patent pending on the concept of a weekend.",
    "Your pitch deck has 60 slides and an appendix for the appendix.",
  ] },
  tuck: { name: "Tuck", lines: [
    "You went to business school in the woods and still couldn't see the forest for the trees.",
    "Your network is incredibly close-knit, mostly because there's nowhere else to go.",
    "You list \"winter\" as a hobby on your resume.",
    "Hanover has one stoplight and you still spent two years networking at it.",
  ] },
  haas: { name: "Berkeley Haas", lines: [
    "You \"question the status quo,\" mostly by asking why your rent is $4,000.",
    "Your defining principle is \"beyond yourself,\" which is also where your budget ended up.",
    "You compost your feelings and call it \"a sustainable mindset.\"",
  ] },
  ross: { name: "Michigan Ross", lines: [
    "Your \"action-based learning\" was mostly the action of losing a group chat argument about football.",
    "You think Ann Arbor is a major financial center. It is not. It has a very nice bagel shop.",
    "You wear maize unironically to job interviews.",
  ] },
  fuqua: { name: "Duke Fuqua", lines: [
    "\"Team Fuqua,\" because none of you could have gotten in alone.",
    "You've camped out for basketball tickets longer than you've ever prepared for an interview.",
    "Your leadership philosophy is a T-shirt.",
  ] },
  stern: { name: "NYU Stern", lines: [
    "Close enough to Wall Street to smell it. Far enough that it can't smell you.",
    "You tell people you go to school \"downtown,\" hoping they assume something more impressive.",
    "Your networking strategy is standing near the bar at events and saying \"Stern, actually.\"",
  ] },
  darden: { name: "UVA Darden", lines: [
    "You've done so many cases you now wake up at 6 a.m. and cold-call yourself.",
    "Your learning team meets at 7 a.m. because Darden thinks sleep is a soft skill.",
    "You say \"the case method\" the way other people say \"my therapist.\"",
  ] },
  insead: { name: "INSEAD", lines: [
    "A one-year MBA, because two years of you was too much for any single institution.",
    "You speak four languages and in all of them you say \"well, at INSEAD...\"",
    "You did Fontainebleau and Singapore, and still can't find your way to a decent job offer.",
  ] },
  lbs: { name: "London Business School", lines: [
    "You went to London for the culture and came back saying \"brilliant\" about spreadsheets.",
    "Your proudest London achievement is knowing which side of the escalator to stand on.",
    "You call it \"uni\" now. Handsome Dan has noted this in your file.",
  ] },
  none: { name: "none of the above", lines: [
    "You don't go to any business school? Bold. Handsome Dan respects the hustle. He does not respect you, but he respects the hustle.",
    "You're here without a Yale ID, without an MBA, and without a plan. Truly a free spirit, in the sense that nobody is paying for you.",
    "You clicked on a Yale bulldog's website for fun. Handsome Dan has questions about your weekends.",
  ] },
};

const FAMILY = [
  "Your family put your acceptance letter on the fridge, then quietly moved it behind the takeout menus.",
  "At Thanksgiving, your relatives ask how school is going in the same tone they use for \"how's the cough?\"",
  "Your parents still introduce your cousin first. Your cousin went to Yale.",
  "Somewhere, your mother is telling her book club you're \"finding yourself.\"",
  "Your family group chat has a second family group chat, and it's about you.",
  "Your grandmother prays for you by name. Handsome Dan has seen the list, and you're below the cat.",
  "Your dad tells his friends you're \"in consulting\" and then changes the subject to the weather.",
];

const FUTURE = [
  "Statistically you will never amount to anything, though Handsome Dan ran the numbers and is willing to round up to \"something.\"",
  "Your ten-year reunion will be held in a conference room you booked yourself.",
  "The peak of your career will be telling people you \"know a guy at Yale.\"",
  "One day you'll make VP. Of the group chat.",
  "Your LinkedIn will say \"Strategy,\" and your mom will still ask what you actually do.",
  "Your exit opportunity is the exit.",
];

const YALE = [
  "Meanwhile, Handsome Dan has never paid tuition, has a full-time staff, and is in more photos than your entire class.",
  "Handsome Dan did not apply to Yale. Yale applied to Handsome Dan.",
  "Boola boola. Look it up. Actually, don't: you'd need Yale credentials.",
  "Handsome Dan's resume is one line long: \"Yale.\" He has never needed a second line.",
  "Yale SOM: we educate leaders for business and society. You: you read this far.",
];

const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
let school = null;
let lastCombo = "";

function roast() {
  const s = SCHOOLS[school || "none"];
  let combo;
  for (let i = 0; i < 8; i++) {  // avoid an immediate repeat
    combo = [pick(s.lines), pick(FAMILY), pick(FUTURE), pick(YALE)];
    if (combo.join("|") !== lastCombo) break;
  }
  lastCombo = combo.join("|");
  return combo;
}

function showRoast() {
  const box = document.getElementById("roast");
  box.replaceChildren();
  const [a, b, c, d] = roast();
  const lines = [["School assessment", a], ["Family impact report", b], ["Projected life outcome", c], ["Official Yale position", d]];
  for (const [label, text] of lines) {
    const row = document.createElement("div");
    row.className = "roast-line";
    const tag = document.createElement("span");
    tag.className = "roast-tag";
    tag.textContent = label;
    const p = document.createElement("p");
    p.textContent = text;
    row.append(tag, p);
    box.append(row);
  }
  const n = parseInt(sessionStorage.getItem("roasts") || "0", 10) + 1;
  sessionStorage.setItem("roasts", String(n));
  document.getElementById("roast-count").textContent =
    `Insults issued this visit: ${n}. Emotional damage: ${n < 3 ? "moderate" : n < 6 ? "significant" : "catastrophic"}.`;
  document.getElementById("roast-wrap").hidden = false;
}

const SCAN = [
  ["Unauthorized non-Yale presence detected", "ALERT"],
  ["Scanning for Yale ID", "NOT FOUND"],
  ["Checking Mory's membership", "DENIED"],
  ["Checking ability to sing \"Bright College Years\"", "TONE-DEAF"],
  ["Cross-referencing admissions records", "NO RECORD (as expected)"],
  ["Deploying Bulldog Security Forces", "DEPLOYED"],
  ["Handsome Dan's assessment", "UNIMPRESSED"],
];

function runScan() {
  const log = document.getElementById("scan");
  let i = 0;
  const next = () => {
    if (i >= SCAN.length) {
      document.getElementById("school-pick").hidden = false;
      return;
    }
    const [what, verdict] = SCAN[i++];
    const line = document.createElement("div");
    line.className = "scan-line";
    line.textContent = `> ${what} `;
    const dots = document.createElement("span");
    dots.className = "scan-dots";
    line.append(dots);
    log.append(line);
    let d = 0;
    const t = setInterval(() => {
      dots.textContent = ".".repeat(++d);
      if (d === 4) {
        clearInterval(t);
        const v = document.createElement("b");
        v.textContent = ` ${verdict}`;
        if (verdict === "DEPLOYED") document.querySelectorAll(".dan-shades").forEach((g) => { g.style.display = ""; });
        line.append(v);
        setTimeout(next, 260);
      }
    }, 150);
  };
  next();
}

document.addEventListener("DOMContentLoaded", () => {
  mountDans();
  startBuddy();
  const pickBox = document.getElementById("schools");
  for (const [key, s] of Object.entries(SCHOOLS)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = key === "none" ? "None of the above" : s.name;
    b.addEventListener("click", () => {
      school = key;
      pickBox.querySelectorAll(".chip").forEach((x) => x.classList.toggle("active", x === b));
      showRoast();
    });
    pickBox.append(b);
  }
  document.getElementById("again").addEventListener("click", showRoast);
  setTimeout(runScan, 700);
});
