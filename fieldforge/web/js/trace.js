// Renders the live AI Forge log. Owns nothing but the log DOM.

const steps = [];

function stepHTML(s, isLast) {
  const done = s.status !== "active";
  const marker = done
    ? '<span class="material-symbols-outlined">check_circle</span>'
    : '<span class="dot"></span>';
  const cursor = s.status === "active" ? '<span class="terminal-cursor"></span>' : "";
  const rail = isLast ? marker : `${marker}<div class="line"></div>`;
  const badge = s.model ? `<div class="badge">${s.model}</div>` : "";
  return `<div class="log-step">
    <div class="log-rail">${rail}</div>
    <div class="log-body"><p>${s.detail}${cursor}</p>${badge}</div>
  </div>`;
}

export function resetTrace(el) {
  steps.length = 0;
  el.innerHTML = '<p class="log-empty">Waiting for capture…</p>';
}

export function addStep(el, step) {
  steps.push(step);
  el.innerHTML = steps.map((s, i) => stepHTML(s, i === steps.length - 1)).join("");
  el.scrollTop = el.scrollHeight;
}
