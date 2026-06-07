// Page logic: wire the Forge button, render the estimate, handle events.
import {
  forgeEstimateStream,
  resumeEstimateStream,
  uploadImage,
  recalc,
  downloadPdf,
} from "./client.js";
import { resetTrace, addStep } from "./trace.js";

const $ = (id) => document.getElementById(id);
const TAX_RATE = 0.13;
const JOB_TITLE = "AC Unit Repair — 123 Maple St";

// Photos picked for this job: server-side paths (after upload).
let imagePaths = [];
// Current estimate rows (editable). [{description, quantity, unit, rate, subtotal}]
let rows = [];

function readAsDataURL(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}

async function onPhotos(e) {
  const files = Array.from(e.target.files || []);
  for (const file of files) {
    const dataUrl = await readAsDataURL(file);
    const img = document.createElement("img");
    img.src = dataUrl;
    $("thumbs").appendChild(img);
    const path = await uploadImage(dataUrl, file.name);
    imagePaths.push(path);
  }
}

function money(n) {
  return `$${Number(n).toFixed(2)}`;
}

// Render the editable estimate from `rows`. qty/rate cells edit -> recalc.
function renderRows() {
  const tbody = $("est-rows");
  tbody.innerHTML = rows
    .map(
      (li, i) => `<tr data-i="${i}">
        <td class="desc" contenteditable data-field="description">${li.description}</td>
        <td class="num" contenteditable data-field="quantity">${li.quantity}</td>
        <td class="num" contenteditable data-field="rate">${money(li.rate)}</td>
        <td class="num">${money(li.subtotal)}</td>
      </tr>`,
    )
    .join("");
}

function renderTotals(est) {
  $("sum-subtotal").textContent = money(est.subtotal);
  $("sum-tax-rate").textContent = `${Math.round(est.tax_rate * 100)}%`;
  $("sum-tax").textContent = money(est.tax);
  $("sum-total").textContent = money(est.total);
}

// Adopt a server estimate as the editable working copy.
function setEstimate(est) {
  if (!est) {
    rows = [];
    $("est-rows").innerHTML = "";
    renderTotals({ subtotal: 0, tax_rate: 0, tax: 0, total: 0 });
    return;
  }
  rows = est.line_items.map((li) => ({ ...li }));
  renderRows();
  renderTotals(est);
}

// Recompute totals server-side after an edit (Facts-from-Tools).
async function recalcFromRows() {
  const est = await recalc(rows, JOB_TITLE, TAX_RATE);
  rows = est.line_items.map((li) => ({ ...li }));
  renderRows();
  renderTotals(est);
}

// Read an edited cell back into `rows`.
function onCellEdit(e) {
  const td = e.target.closest("td[data-field]");
  if (!td) return;
  const tr = td.closest("tr");
  const i = Number(tr.dataset.i);
  const field = td.dataset.field;
  let val = td.textContent.trim();
  if (field === "quantity" || field === "rate") val = parseFloat(val.replace(/[^0-9.]/g, "")) || 0;
  rows[i][field] = val;
  recalcFromRows();
}

// The single event handler used by both the initial run and the resume.
function handleEvent(event) {
  if (event.type === "trace") {
    addStep($("log"), event.step);
  } else if (event.type === "pause") {
    showPause(event);
  } else if (event.type === "estimate") {
    setEstimate(event.estimate);
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
  setEstimate(null);
  $("pause").style.display = "none";
  $("forge-state").textContent = "Working…";
  await forgeEstimateStream(transcript, "hvac", imagePaths, handleEvent);
}

function newEstimate() {
  resetTrace($("log"));
  setEstimate(null);
  $("pause").style.display = "none";
  $("forge-state").textContent = "Idle";
  $("transcript").value = "";
  $("thumbs").innerHTML = "";
  imagePaths = [];
  $("transcript").focus();
}

function addItem() {
  rows.push({ description: "New item", quantity: 1, unit: "ea", rate: 0, subtotal: 0 });
  renderRows();
  recalcFromRows();
}

$("forge-btn").addEventListener("click", forge);
$("new-estimate-btn").addEventListener("click", newEstimate);
$("photo-input").addEventListener("change", onPhotos);
$("add-item-btn").addEventListener("click", addItem);
$("pdf-btn").addEventListener("click", () => downloadPdf(rows, JOB_TITLE, TAX_RATE));
$("discard-btn").addEventListener("click", newEstimate);
$("finalize-btn").addEventListener("click", () => downloadPdf(rows, JOB_TITLE, TAX_RATE));
// Edits commit on blur (after the user leaves the cell).
$("est-rows").addEventListener("focusout", onCellEdit);
$("transcript").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) forge();
});
