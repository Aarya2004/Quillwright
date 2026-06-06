// Page logic: wire the Forge button, render the estimate, handle events.
import { forgeEstimateStream } from "./client.js";
import { resetTrace, addStep } from "./trace.js";

const $ = (id) => document.getElementById(id);

function money(n) {
  return `$${Number(n).toFixed(2)}`;
}

function renderEstimate(est) {
  const tbody = $("est-rows");
  if (!est) {
    tbody.innerHTML = "";
    return;
  }
  tbody.innerHTML = est.line_items
    .map(
      (li) => `<tr>
        <td class="desc" contenteditable>${li.description}</td>
        <td>${li.quantity % 1 === 0 ? li.quantity : li.quantity} ${li.unit}</td>
        <td class="num" contenteditable>${money(li.rate)}</td>
        <td class="num">${money(li.subtotal)}</td>
      </tr>`,
    )
    .join("");
  $("sum-subtotal").textContent = money(est.subtotal);
  $("sum-tax-rate").textContent = `${Math.round(est.tax_rate * 100)}%`;
  $("sum-tax").textContent = money(est.tax);
  $("sum-total").textContent = money(est.total);
}

async function forge() {
  const transcript = $("transcript").value;
  resetTrace($("log"));
  renderEstimate(null);
  $("forge-state").textContent = "Working…";

  await forgeEstimateStream(transcript, "hvac", (event) => {
    if (event.type === "trace") {
      addStep($("log"), event.step);
    } else if (event.type === "estimate") {
      renderEstimate(event.estimate);
      $("forge-state").textContent = "Done";
    }
  });
}

$("forge-btn").addEventListener("click", forge);
$("transcript").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) forge();
});
