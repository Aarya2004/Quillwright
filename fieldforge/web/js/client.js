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
