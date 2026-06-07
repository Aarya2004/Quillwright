// Renders the Digital Apprentice step cards. Owns nothing but the steps DOM.
// Consecutive steps of the same action collapse into one card (e.g. all
// pricing lines become a single "Pricing" card listing the items).

const steps = [];

// Friendly card titles + lead-in text for each agent action.
const CARDS = {
  perceive: { title: "Site Analysis", lead: "Reviewed the job and noted what's needed." },
  price: { title: "Market Pricing", lead: "Pulled current prices for each part." },
  assemble: { title: "Estimate Assembled", lead: "" },
};

// Collapse the flat step list into grouped cards by consecutive action.
function group(list) {
  const cards = [];
  for (const s of list) {
    const last = cards[cards.length - 1];
    if (last && last.action === s.action) {
      last.details.push(s.detail);
      last.status = s.status;
    } else {
      cards.push({ action: s.action, status: s.status, details: [s.detail] });
    }
  }
  return cards;
}

function cardHTML(c, isLast) {
  const working = c.status === "active";
  const marker = working
    ? '<div class="working-dot"></div>'
    : '<span class="material-symbols-outlined">check_circle</span>';
  const meta = CARDS[c.action] || { title: c.action, lead: "" };
  const lead = meta.lead ? `<p class="detail">${meta.lead}</p>` : "";
  const items =
    c.details.length > 1 || meta.lead
      ? `<ul class="step-items">${c.details.map((d) => `<li>${d}</li>`).join("")}</ul>`
      : `<p class="detail">${c.details[0]}</p>`;
  return `<div class="step-card${working ? " working" : ""}">
    <div class="step-rail">${marker}</div>
    <div class="step-body">
      <p class="title">${meta.title}</p>
      ${lead}${items}
    </div>
  </div>`;
}

export function resetTrace(el) {
  steps.length = 0;
  el.innerHTML = '<p class="step-empty">Waiting for a job to forge…</p>';
}

export function addStep(el, step) {
  steps.push(step);
  const cards = group(steps);
  el.innerHTML =
    '<div class="steps">' +
    cards.map((c, i) => cardHTML(c, i === cards.length - 1)).join("") +
    "</div>";
  el.scrollTop = el.scrollHeight;
}
