// Renders the Digital Apprentice step cards. Owns nothing but the steps DOM.

const steps = [];

// Friendly card titles for each agent action.
const TITLES = {
  perceive: "Site Analysis",
  price: "Pricing",
  assemble: "Estimate Assembled",
};

function cardHTML(s, isLast) {
  const working = s.status === "active";
  const marker = working
    ? '<div class="working-dot"></div>'
    : '<span class="material-symbols-outlined">check_circle</span>';
  const rail = isLast ? marker : `${marker}`;
  const title = TITLES[s.action] || s.action;
  return `<div class="step-card${working ? " working" : ""}">
    <div class="step-rail">${rail}</div>
    <div class="step-body">
      <p class="title">${title}</p>
      <p class="detail">${s.detail}</p>
    </div>
  </div>`;
}

export function resetTrace(el) {
  steps.length = 0;
  el.innerHTML = '<p class="step-empty">Waiting for a job to forge…</p>';
}

export function addStep(el, step) {
  steps.push(step);
  el.innerHTML =
    '<div class="steps">' +
    steps.map((s, i) => cardHTML(s, i === steps.length - 1)).join("") +
    "</div>";
  el.scrollTop = el.scrollHeight;
}
