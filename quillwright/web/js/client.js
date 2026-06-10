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
// Returns {estimate, reply, needs_price}.
export async function chatAboutEstimate(message, rows, taxRate) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, rows, tax_rate: taxRate }),
  });
  return res.json();
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
