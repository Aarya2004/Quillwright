// My Estimates (ADR-0013): list saved estimates newest-first; reopen or discard.
import { listEstimates, deleteEstimate } from "./client.js";

const money = (n) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

async function load() {
  const host = document.getElementById("estimates");
  host.innerHTML = "";
  const data = await listEstimates();
  const estimates = data.estimates || [];
  document.getElementById("est-count").textContent =
    `${estimates.length} estimate${estimates.length === 1 ? "" : "s"}`;

  if (!estimates.length) {
    host.append(
      el(`<div class="empty"><span class="material-symbols-outlined">folder</span>
          No saved estimates yet. <a href="/">Forge one →</a></div>`),
    );
    return;
  }

  const table = el(`<table>
      <thead><tr><th>Ref</th><th>Job</th><th class="num">Total</th><th></th></tr></thead>
      <tbody></tbody></table>`);
  const tbody = table.querySelector("tbody");
  for (const e of estimates) {
    const tr = el(`<tr>
        <td class="mono">#${e.id}</td>
        <td class="desc"><a href="/?estimate=${e.id}">${e.job_title}</a></td>
        <td class="num">${money(e.total)}</td>
        <td class="num"><button class="link-btn" data-del="${e.id}">Discard</button></td>
      </tr>`);
    tr.querySelector("[data-del]").addEventListener("click", async () => {
      await deleteEstimate(e.id);
      load();
    });
    tbody.append(tr);
  }
  host.append(table);
}

load();
