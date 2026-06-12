// Renders the Digital Apprentice step cards into the shared stream (#log).
// Consecutive steps of the same action collapse into one card. Cards render
// INCREMENTALLY (append new, patch changed) so each entry animation fires once —
// the staggered "steps slowly show up" reveal. A connector rail links the
// check-circles down the left edge for a terminal/console feel.

const steps = [];

const CARDS = {
  recall: { title: "Memory", lead: "Checked your past jobs for anything similar." },
  document: { title: "Document Capture", lead: "Read the handed-over document." },
  perceive: { title: "Site Analysis", lead: "Reviewed the job and noted what's needed." },
  price: { title: "Market Pricing", lead: "Pulled current prices for each part." },
  add_priced_item: { title: "Market Pricing", lead: "Pulled current prices for each part." },
  finish: { title: "Estimate Assembled", lead: "" },
  assemble: { title: "Estimate Assembled", lead: "" },
};

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

function cardInner(c) {
  const working = c.status === "active";
  const marker = working
    ? '<div class="working-dot"></div>'
    : '<span class="material-symbols-outlined check">check_circle</span>';
  const meta = CARDS[c.action] || { title: c.action, lead: "" };
  const lead = meta.lead ? `<p class="detail">${meta.lead}</p>` : "";
  const items =
    c.details.length > 1 || meta.lead
      ? `<ul class="step-items">${c.details.map((d) => `<li>${d}</li>`).join("")}</ul>`
      : `<p class="detail">${c.details[0]}</p>`;
  return `<div class="step-rail">${marker}<span class="rail-line"></span></div>
    <div class="step-body">
      <p class="title">${meta.title}</p>
      ${lead}${items}
    </div>`;
}

function host(el) {
  let h = el.querySelector(".steps");
  if (!h) {
    const div = document.createElement("div");
    div.className = "steps";
    el.prepend(div);
    h = div;
  }
  return h;
}

export function resetTrace(el) {
  steps.length = 0;
  el.innerHTML = '<div class="steps"><p class="step-empty">Waiting for a job to forge…</p></div>';
}

export function addStep(el, step) {
  steps.push(step);
  const cards = group(steps);
  const h = host(el);
  const empty = h.querySelector(".step-empty");
  if (empty) empty.remove();

  const existing = h.querySelectorAll(":scope > .step-card");
  cards.forEach((c, i) => {
    if (existing[i]) {
      const node = existing[i];
      const wasWorking = node.classList.contains("working");
      node.innerHTML = cardInner(c);
      node.classList.toggle("working", c.status === "active");
      if (wasWorking && c.status !== "active") node.classList.add("just-done");
    } else {
      const node = document.createElement("div");
      node.className = "step-card enter" + (c.status === "active" ? " working" : "");
      node.style.setProperty("--enter-delay", `${Math.min(i, 6) * 60}ms`);
      node.innerHTML = cardInner(c);
      h.appendChild(node);
      node.addEventListener("animationend", () => node.classList.remove("enter"), { once: true });
    }
  });
  el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
}
