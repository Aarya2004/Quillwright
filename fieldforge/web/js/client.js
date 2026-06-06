// The single place that knows the API URLs. Everything else calls these.

// Stream the agent run; invokes onEvent({type:"trace"|"estimate", ...}) per SSE frame.
export async function forgeEstimateStream(transcript, trade, onEvent) {
  const res = await fetch("/api/forge_estimate_stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, trade }),
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
