// Parts Catalog: read-only stock view from the seeded inventory read-model.
// Low-stock flags + counts are computed server-side; category filter is client-side.
const money = (n) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);
const el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

let parts = [];
let activeCat = "ALL";

function stockBar(p) {
  const pct =
    p.reorder_at > 0 ? Math.min(100, Math.round((p.stock / (p.reorder_at * 3)) * 100)) : 100;
  const status = p.reorder_at === 0 ? "Service" : p.low ? "LOW" : "OK";
  return `<div class="stock ${p.low ? "is-low" : ""}">
      <div class="nums"><span>${p.stock} ${p.unit}</span><span>${status}</span></div>
      <div class="meter"><span style="width:${pct}%"></span></div>
    </div>`;
}

function render() {
  const host = document.getElementById("parts");
  host.innerHTML = "";
  const shown = activeCat === "ALL" ? parts : parts.filter((p) => p.category === activeCat);
  const rows = shown
    .map(
      (p) => `<tr>
        <td class="desc">${p.description}</td>
        <td><span class="chip chip--cat">${p.category}</span></td>
        <td>${stockBar(p)}</td>
        <td class="num">${money(p.rate)}</td>
        <td>${p.low ? '<span class="chip chip--low">Reorder</span>' : '<span class="chip chip--ok">In stock</span>'}</td>
      </tr>`,
    )
    .join("");
  host.append(
    el(`<table>
        <thead><tr><th>Part</th><th>Category</th><th>Stock</th><th class="num">Unit price</th><th>Status</th></tr></thead>
        <tbody>${rows}</tbody></table>`),
  );
}

async function load() {
  const data = await (await fetch("/api/inventory")).json();
  parts = data.parts;

  document.getElementById("kpis").append(
    el(`<div class="kpi"><p class="label">Total SKUs</p><p class="value">${data.total_skus}</p>
        <p class="sub">in the catalog</p></div>`),
    el(`<div class="kpi kpi--alert"><p class="label">Low stock</p>
        <p class="value">${data.low_stock_count}</p><p class="sub">at or below reorder point</p></div>`),
  );

  const cats = ["ALL", ...new Set(parts.map((p) => p.category))];
  const filters = document.getElementById("filters");
  cats.forEach((c) => {
    const b = el(`<button class="filter ${c === "ALL" ? "active" : ""}">${c}</button>`);
    b.addEventListener("click", () => {
      activeCat = c;
      filters.querySelectorAll(".filter").forEach((f) => f.classList.toggle("active", f === b));
      render();
    });
    filters.append(b);
  });

  render();
}

load();
