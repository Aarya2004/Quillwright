// Active Jobs: list every past Run from the real memory read-model, newest first.
const money = (n) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

async function load() {
  const data = await (await fetch("/api/jobs")).json();
  const jobs = data.jobs;
  document.getElementById("job-count").textContent =
    `${jobs.length} job${jobs.length === 1 ? "" : "s"}`;

  const host = document.getElementById("jobs");
  if (!jobs.length) {
    host.append(
      el(`<div class="empty"><span class="material-symbols-outlined">work</span>
          No jobs recorded yet. <a href="/">Forge an estimate →</a></div>`),
    );
    return;
  }
  const rows = jobs
    .map(
      (j) => `<tr>
        <td class="mono">#${j.id}</td>
        <td class="desc">${j.transcript || "(no note)"}</td>
        <td>${j.items}</td>
        <td class="num">${money(j.total)}</td>
      </tr>`,
    )
    .join("");
  host.append(
    el(`<table>
        <thead><tr><th>Ref</th><th>Job note</th><th>Items</th><th class="num">Total</th></tr></thead>
        <tbody>${rows}</tbody></table>`),
  );
}

load();
