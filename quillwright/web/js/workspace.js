// Page logic: wire the Forge button, render the estimate, handle events.
import {
  forgeEstimateStream,
  resumeEstimateStream,
  uploadImage,
  recalc,
  downloadPdf,
  downloadJson,
  translateEstimate,
  chatAboutEstimate,
  transcribeNote,
  parseDocument,
  modelInfo,
} from "./client.js";
import { resetTrace, addStep } from "./trace.js";

const $ = (id) => document.getElementById(id);
const TAX_RATE = 0.13;
const JOB_TITLE = "AC Unit Repair — 123 Maple St";

// Run state, in one place: the label text + the live-dot color (data-state).
function setState(state, label) {
  $("forge-state").textContent = label;
  document.querySelector(".live").dataset.state = state;
}

// Photos picked for this job: server-side paths (after upload).
let imagePaths = [];
// Current estimate rows (editable). [{description, quantity, unit, rate, subtotal}]
let rows = [];
// English source descriptions, so language switches re-translate from English.
let sourceDescriptions = [];

function readAsDataURL(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}

// --- Voice note: record via mic, transcribe (Cohere Transcribe), fill the note ---
let mediaRecorder = null;
let recordedChunks = [];

async function toggleRecording() {
  const btn = $("mic-btn");
  // Stop if already recording.
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    btn.title = "Mic permission denied";
    return;
  }
  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (e) => e.data.size && recordedChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    btn.classList.remove("recording");
    btn.innerHTML = '<span class="material-symbols-outlined">hourglass_top</span>';
    const blob = new Blob(recordedChunks, { type: "audio/webm" });
    const dataUrl = await readAsDataURL(blob);
    const text = await transcribeNote(dataUrl, "note.webm");
    if (text) $("transcript").value = text;
    btn.innerHTML = '<span class="material-symbols-outlined">mic</span>';
  };
  mediaRecorder.start();
  btn.classList.add("recording");
  btn.innerHTML = '<span class="material-symbols-outlined">stop</span>';
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

// --- Document Capture (ADR-0011): a handed-over document -> Proposed Line Items ---
// The document is the *source*, but every price it carries is proposed, never a
// fact — the human confirms (or edits) each row before it enters the estimate.
async function onDocument(e) {
  const file = (e.target.files || [])[0];
  e.target.value = ""; // allow re-picking the same file
  if (!file) return;
  setState("working", "Reading document…");
  const dataUrl = await readAsDataURL(file);
  const out = await parseDocument(dataUrl, file.name);
  if (rows.length) setState("done", "Done");
  else setState("idle", "Idle");
  const title = (out.observations[0] || {}).text || file.name;
  addStep($("log"), {
    action: "document",
    model: out.model,
    detail: `“${title}” — ${out.proposed_items.length} priced row(s) proposed`,
    status: "ok",
  });
  showProposedItems(out.proposed_items);
}

// Render the Proposed-Line-Items confirm card on the Agent-Pause surface.
function showProposedItems(items) {
  const card = $("pause");
  if (!items.length) {
    card.innerHTML = `
      <div class="bot"><span class="material-symbols-outlined">document_scanner</span></div>
      <div class="doc-confirm">
        <p>I couldn't find any priced rows in that document.</p>
        <div class="opts"><button class="link-btn" id="doc-dismiss">Dismiss</button></div>
      </div>`;
  } else {
    card.innerHTML = `
      <div class="bot"><span class="material-symbols-outlined">document_scanner</span></div>
      <div class="doc-confirm">
        <p>I read ${items.length} priced row(s) off that document. Confirm what enters the estimate:</p>
        <div class="doc-items">
          ${items
            .map(
              (p, i) => `
          <label class="doc-item" style="--doc-delay:${i * 55}ms">
            <input type="checkbox" data-i="${i}" checked />
            <span class="doc-desc">${p.description}<small>${p.source_text}</small></span>
            <input class="doc-qty" type="number" step="any" value="${p.quantity}" aria-label="Quantity" />
            <input class="doc-rate" type="number" step="0.01" value="${p.rate.toFixed(2)}" aria-label="Rate" />
          </label>`,
            )
            .join("")}
        </div>
        <div class="opts">
          <button class="btn btn--primary" id="doc-add">Add to estimate</button>
          <button class="link-btn" id="doc-dismiss">Dismiss</button>
        </div>
      </div>`;
  }
  card.style.display = "flex";

  const hide = () => {
    card.style.display = "none";
    card.innerHTML = "";
  };
  $("doc-dismiss").addEventListener("click", hide);
  const add = $("doc-add");
  if (add)
    add.addEventListener("click", () => {
      card.querySelectorAll(".doc-item").forEach((row) => {
        const check = row.querySelector("input[type=checkbox]");
        if (!check.checked) return;
        const p = items[Number(check.dataset.i)];
        rows.push({
          description: p.description,
          quantity: parseFloat(row.querySelector(".doc-qty").value) || 1,
          unit: p.unit,
          rate: parseFloat(row.querySelector(".doc-rate").value) || 0,
          subtotal: 0,
          price_source: "document",
        });
      });
      hide();
      recalcFromRows();
      setChatEnabled(rows.length > 0);
    });
}

// Render the editable estimate from `rows`. qty/rate cells edit -> recalc.
// `animate` staggers the rows in (used when a fresh estimate lands, not on edits).
function renderRows(animate = false) {
  const tbody = $("est-rows");
  if (!rows.length) {
    tbody.innerHTML =
      '<tr class="table-empty"><td colspan="4">No line items yet — forge an estimate to begin.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map(
      (
        li,
        i,
      ) => `<tr data-i="${i}"${animate ? ' class="row-enter" style="--row-delay:' + i * 55 + 'ms"' : ""}>
        <td class="desc" contenteditable data-field="description">${li.description}</td>
        <td class="num" contenteditable data-field="quantity">${li.quantity}</td>
        <td class="num" contenteditable data-field="rate">${money(li.rate)}</td>
        <td class="num">${money(li.subtotal)}</td>
      </tr>`,
    )
    .join("");
}

// Flash the total when it changes (subtle "the number moved" cue).
let lastTotal = null;
function bumpTotal() {
  const el = $("sum-total");
  el.classList.remove("bump");
  void el.offsetWidth; // restart the animation
  el.classList.add("bump");
}

function renderTotals(est) {
  $("sum-subtotal").textContent = money(est.subtotal);
  $("sum-tax-rate").textContent = `${Math.round(est.tax_rate * 100)}%`;
  $("sum-tax").textContent = money(est.tax);
  $("sum-total").textContent = money(est.total);
  if (lastTotal !== null && est.total !== lastTotal) bumpTotal();
  lastTotal = est.total;
}

// Adopt a server estimate as the editable working copy.
// `animate` staggers the rows in (true when a forge/chat just produced it).
function setEstimate(est, animate = false) {
  if (!est) {
    rows = [];
    lastTotal = null;
    renderRows();
    renderTotals({ subtotal: 0, tax_rate: 0, tax: 0, total: 0 });
    setChatEnabled(false);
    return;
  }
  rows = est.line_items.map((li) => ({ ...li }));
  sourceDescriptions = rows.map((li) => li.description);
  $("lang").value = "English";
  renderRows(animate);
  renderTotals(est);
  setChatEnabled(rows.length > 0);
}

// Re-render the customer copy in the selected language (descriptions only).
async function onLanguageChange() {
  const language = $("lang").value;
  // translate from the English source each time, not from a prior translation
  const src = rows.map((li, i) => ({
    ...li,
    description: sourceDescriptions[i] ?? li.description,
  }));
  const est = await translateEstimate(src, JOB_TITLE, TAX_RATE, language);
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
    setEstimate(event.estimate, true);
    setState("done", "Done");
  }
}

// Render the Agent-Pause question card; answering resumes the run.
function showPause(event) {
  setState("needs-you", "Needs you");
  const card = $("pause");
  card.innerHTML = `
    <div class="bot"><span class="material-symbols-outlined">smart_toy</span></div>
    <div class="pause-body">
      <p>${event.reason}. What should I charge for it?</p>
      <div class="opts">
        <input id="pause-price" class="pause-price" type="number" step="0.01" placeholder="0.00" />
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
    setState("working", "Working…");
    await withForgeLocked(() => resumeEstimateStream(value, handleEvent));
  };
  $("pause-submit").addEventListener("click", submit);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
}

// Hold the Forge button down while a run streams (no double-forge); always release.
async function withForgeLocked(run) {
  $("forge-btn").disabled = true;
  try {
    await run();
  } finally {
    $("forge-btn").disabled = false;
  }
}

async function forge() {
  const transcript = $("transcript").value;
  resetTrace($("log"));
  setEstimate(null);
  $("pause").style.display = "none";
  setState("working", "Working…");
  await withForgeLocked(() => forgeEstimateStream(transcript, "hvac", imagePaths, handleEvent));
}

function newEstimate() {
  resetTrace($("log"));
  setEstimate(null);
  $("pause").style.display = "none";
  setState("idle", "Idle");
  $("transcript").value = "";
  $("thumbs").innerHTML = "";
  imagePaths = [];
  chatStarted = false;
  $("transcript").focus();
}

// --- Chat: refine the estimate, in the SAME stream as the trace ---
// The input docks at the bottom of the Apprentice pane and only enables once an
// estimate exists. The first chat turn drops a divider after the trace steps.
let chatStarted = false;

function setChatEnabled(on) {
  $("chat-text").disabled = !on;
  $("chat-send").disabled = !on;
  $("chat-text").placeholder = on
    ? "Ask the apprentice to refine the estimate…"
    : "Forge an estimate, then refine it here…";
}

function appendToStream(node) {
  const log = $("log");
  log.appendChild(node);
  log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
}

function ensureChatStarted() {
  if (chatStarted) return;
  chatStarted = true;
  const divider = document.createElement("div");
  divider.className = "chat-divider";
  divider.textContent = "Refine";
  $("log").appendChild(divider);
}

function appendMsg(role, text) {
  ensureChatStarted();
  const el = document.createElement("div");
  el.className = `chat-msg ${role}`;
  el.innerHTML = `<div class="bubble">${text}</div>`;
  appendToStream(el);
  return el;
}

function showTyping() {
  ensureChatStarted();
  const el = document.createElement("div");
  el.className = "chat-msg bot typing";
  el.innerHTML = `<div class="bubble"><i></i><i></i><i></i></div>`;
  appendToStream(el);
  return el;
}

let chatBusy = false;
async function sendChat(e) {
  e.preventDefault();
  const text = $("chat-text").value.trim();
  if (!text || chatBusy || $("chat-text").disabled) return;
  chatBusy = true;
  $("chat-send").disabled = true;
  $("chat-text").value = "";
  appendMsg("user", text);
  const typing = showTyping();
  try {
    const out = await chatAboutEstimate(text, rows, TAX_RATE);
    typing.remove();
    appendMsg("bot", out.reply);
    if (out.estimate) {
      // Adopt the refined estimate; the right pane updates + total bumps.
      setEstimate(out.estimate);
    }
  } catch (err) {
    typing.remove();
    appendMsg("bot", "Sorry — I couldn't process that just now. Try again?");
  } finally {
    chatBusy = false;
    $("chat-send").disabled = $("chat-text").disabled;
    $("chat-text").focus();
  }
}

function addItem() {
  rows.push({ description: "New item", quantity: 1, unit: "ea", rate: 0, subtotal: 0 });
  renderRows();
  recalcFromRows();
}

$("forge-btn").addEventListener("click", forge);
$("new-estimate-btn").addEventListener("click", newEstimate);
$("photo-input").addEventListener("change", onPhotos);
$("doc-input").addEventListener("change", onDocument);
$("mic-btn").addEventListener("click", toggleRecording);
$("add-item-btn").addEventListener("click", addItem);
$("pdf-btn").addEventListener("click", () => downloadPdf(rows, JOB_TITLE, TAX_RATE));
$("json-btn").addEventListener("click", () => downloadJson(rows, JOB_TITLE, TAX_RATE));
$("discard-btn").addEventListener("click", newEstimate);
$("finalize-btn").addEventListener("click", () => downloadPdf(rows, JOB_TITLE, TAX_RATE));
$("lang").addEventListener("change", onLanguageChange);
$("chat-form").addEventListener("submit", sendChat);
// Edits commit on blur (after the user leaves the cell).
$("est-rows").addEventListener("focusout", onCellEdit);
$("transcript").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) forge();
});

// Populate the model-mode badge (stub / local / modal / mixed) + per-role labels.
async function showModelBadge() {
  try {
    const info = await modelInfo();
    const badge = $("model-badge");
    badge.dataset.mode = info.mode;
    $("model-badge-mode").textContent = info.mode.charAt(0).toUpperCase() + info.mode.slice(1);
    const labels = { brain: "brain", perception: "vision", multilingual: "lang" };
    $("model-badge-roles").textContent = Object.entries(info.roles)
      .map(([role, name]) => `${labels[role] || role}: ${name}`)
      .join(" · ");
    badge.hidden = false;
  } catch {
    /* badge is informational; never block the app if it fails */
  }
}
showModelBadge();

// First paint: show the empty-estimate state rather than a bare table header.
renderRows();
