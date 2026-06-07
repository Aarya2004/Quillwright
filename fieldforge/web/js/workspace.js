// Page logic: wire the Forge button, render the estimate, handle events.
import { forgeEstimateStream, resumeEstimateStream } from "./client.js";
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
        <td>${li.quantity} ${li.unit}</td>
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

// The single event handler used by both the initial run and the resume.
function handleEvent(event) {
  if (event.type === "trace") {
    addStep($("log"), event.step);
  } else if (event.type === "pause") {
    showPause(event);
  } else if (event.type === "estimate") {
    renderEstimate(event.estimate);
    $("forge-state").textContent = "Done";
  }
}

// Render the Agent-Pause question card; answering resumes the run.
function showPause(event) {
  $("forge-state").textContent = "Needs you";
  const card = $("pause");
  card.innerHTML = `
    <div class="bot"><span class="material-symbols-outlined">smart_toy</span></div>
    <div style="flex:1">
      <p>${event.reason}. What should I charge for it?</p>
      <div class="opts">
        <input id="pause-price" type="number" step="0.01" placeholder="0.00"
               style="padding:8px;border:1px solid var(--outline);border-radius:8px;width:120px" />
        <button class="btn btn--primary" id="pause-submit">Use this price</button>
      </div>
    </div>`;
  card.style.display = "flex";
  const input = $("pause-price");
  input.focus();
  const submit = async () => {
    const value = parseFloat(input.value);
    if (Number.isNaN(value)) return;
    card.style.display = "none";
    card.innerHTML = "";
    $("forge-state").textContent = "Working…";
    await resumeEstimateStream(value, handleEvent);
  };
  $("pause-submit").addEventListener("click", submit);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
}

async function forge() {
  const transcript = $("transcript").value;
  resetTrace($("log"));
  renderEstimate(null);
  $("pause").style.display = "none";
  $("forge-state").textContent = "Working…";
  await forgeEstimateStream(transcript, "hvac", handleEvent);
}

function newEstimate() {
  resetTrace($("log"));
  renderEstimate(null);
  $("pause").style.display = "none";
  $("forge-state").textContent = "Idle";
  $("transcript").value = "";
  $("transcript").focus();
}

$("forge-btn").addEventListener("click", forge);
$("new-estimate-btn").addEventListener("click", newEstimate);
$("transcript").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) forge();
});
