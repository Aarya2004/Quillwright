// The single place that knows the API URLs. Everything else calls these.

const THREAD_ID = "ui";

async function consumeStream(url, body, onEvent) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, thread_id: THREAD_ID }),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop();
    for (const frame of frames) {
      const line = frame.replace(/^data: /, "").trim();
      if (line) onEvent(JSON.parse(line));
    }
  }
}

// Which models fill each role right now (mode + per-role labels) for the badge.
export async function modelInfo() {
  const res = await fetch("/api/model_info");
  return res.json();
}

// Upload one image (base64 data URL); returns the server-side path.
export async function uploadImage(dataUrl, filename) {
  const res = await fetch("/api/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data: dataUrl, filename }),
  });
  const out = await res.json();
  return out.path;
}

// Stream a run; onEvent({type:"trace"|"pause"|"estimate", ...}) per SSE frame.
export function forgeEstimateStream(transcript, trade, imagePaths, onEvent) {
  return consumeStream(
    "/api/forge_estimate_stream",
    { transcript, trade, image_paths: imagePaths },
    onEvent,
  );
}

// Resume a paused run with the human-supplied value; continues streaming.
export function resumeEstimateStream(value, onEvent) {
  return consumeStream("/api/resume_estimate_stream", { value }, onEvent);
}

// Server-authoritative recompute of an edited estimate.
export async function recalc(rows, jobTitle, taxRate) {
  const res = await fetch("/api/recalc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, job_title: jobTitle, tax_rate: taxRate }),
  });
  return res.json();
}

// Document Capture (ADR-0011): parse a handed-over document (supplier quote, spec
// sheet) into {model, observations, proposed_items} for the human to confirm.
export async function parseDocument(dataUrl, filename) {
  const res = await fetch("/api/parse_document", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data: dataUrl, filename }),
  });
  return res.json();
}

// Transcribe a recorded voice note (base64 data URL) into text (Cohere Transcribe).
export async function transcribeNote(dataUrl, filename) {
  const res = await fetch("/api/transcribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data: dataUrl, filename }),
  });
  const out = await res.json();
  return out.transcript || "";
}

// Refine the current estimate conversationally (the Digital Apprentice chat).
// Carries the Refinement Thread (ADR-0013) in and back out. Returns
// {estimate, reply, needs_price, changed, thread}.
export async function chatAboutEstimate(message, rows, taxRate, thread) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, rows, tax_rate: taxRate, thread }),
  });
  return res.json();
}

// --- Saved Estimates (ADR-0013): per-account Estimate Store. ---

// Persist (create or update-in-place via `id`) a Saved Estimate + its thread.
// Returns {id}.
export async function saveEstimate(rows, jobTitle, taxRate, thread, id) {
  const res = await fetch("/api/save_estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, job_title: jobTitle, tax_rate: taxRate, thread, id }),
  });
  return res.json();
}

// The account's saved estimates, newest first ({estimates: [{id, job_title, total}]}).
export async function listEstimates() {
  const res = await fetch("/api/estimates");
  return res.json();
}

// Reopen one saved estimate (frozen snapshot + thread), or null if missing.
export async function loadEstimate(id) {
  const res = await fetch(`/api/estimate/${id}`);
  if (!res.ok) return null;
  return res.json();
}

// Discard a saved estimate.
export async function deleteEstimate(id) {
  await fetch(`/api/estimate/${id}`, { method: "DELETE" });
}

// --- QR phone-capture pairing (Tier 3). ---

// Open a pairing for this desktop session. Returns {code, capture_url, qr_svg}.
export async function createPairing() {
  const res = await fetch("/api/pair/create", { method: "POST" });
  return res.json();
}

// Poll for the phone's capture (delivered once). Returns the capture or null.
export async function pollPairing(code) {
  const res = await fetch(`/api/pair/${code}`);
  const out = await res.json();
  return out.capture;
}

// Translate the customer-facing estimate copy into a language (Cohere Aya).
export async function translateEstimate(rows, jobTitle, taxRate, language) {
  const res = await fetch("/api/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, job_title: jobTitle, tax_rate: taxRate, language }),
  });
  return res.json();
}

// Download a PDF of the current (edited) estimate.
export async function downloadPdf(rows, jobTitle, taxRate) {
  const res = await fetch("/api/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, job_title: jobTitle, tax_rate: taxRate }),
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "estimate.pdf";
  a.click();
  URL.revokeObjectURL(url);
}

// Finalize & Send (S10): deliver the estimate to a customer by SMS or email.
// Returns {status:"sent"|"drafted", transmitted, channel, recipient, summary, provider_id}.
// On bad input the server replies 400 with a plain-text reason.
export async function sendEstimate(channel, recipient, rows, jobTitle, taxRate) {
  const res = await fetch("/api/send_estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel, recipient, rows, job_title: jobTitle, tax_rate: taxRate }),
  });
  if (!res.ok) {
    const reason = await res.text();
    throw new Error(reason || "Send failed.");
  }
  return res.json();
}

// Download a machine-readable JSON of the current estimate (the "no lock-in" export).
export async function downloadJson(rows, jobTitle, taxRate) {
  const res = await fetch("/api/export_json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, job_title: jobTitle, tax_rate: taxRate }),
  });
  const payload = await res.json();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "estimate.json";
  a.click();
  URL.revokeObjectURL(url);
}
