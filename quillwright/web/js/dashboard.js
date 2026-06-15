// Dashboard: render KPIs + recent jobs from the real memory read-model.
const money = (n) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

async function load() {
  const data = await (await fetch("/api/dashboard")).json();

  document.getElementById("kpis").append(
    el(`<div class="kpi"><p class="label">Jobs forged</p><p class="value">${data.job_count}</p>
        <p class="sub">on this device</p></div>`),
    el(`<div class="kpi kpi--dark"><p class="label">Total estimated</p>
        <p class="value">${money(data.revenue_total)}</p>
        <p class="sub">sum of finished estimates</p></div>`),
    el(`<div class="kpi"><p class="label">Distinct items used</p>
        <p class="value">${data.top_items.length}</p>
        <p class="sub">across past jobs</p></div>`),
  );

  const recent = document.getElementById("recent");
  if (!data.recent.length) {
    recent.append(
      el(`<div class="empty"><span class="material-symbols-outlined">description</span>
          No jobs yet. <a href="/">Forge your first estimate →</a></div>`),
    );
  } else {
    const rows = data.recent
      .map(
        (r) => `<tr>
          <td class="desc">${r.transcript || "(no note)"}</td>
          <td>${r.items}</td>
          <td class="num">${money(r.total)}</td>
        </tr>`,
      )
      .join("");
    recent.append(
      el(`<table><thead><tr><th>Job note</th><th>Items</th><th class="num">Total</th></tr></thead>
          <tbody>${rows}</tbody></table>`),
    );
  }

  const top = document.getElementById("top-items");
  if (!data.top_items.length) {
    top.append(el(`<p class="step-empty">No items learned yet.</p>`));
  } else {
    top.append(
      el(
        `<div class="filters">${data.top_items
          .map((i) => `<span class="chip chip--cat">${i}</span>`)
          .join("")}</div>`,
      ),
    );
  }
}

load();
