// Shared DOM-safety helpers.

// Escape the 5 HTML-significant characters so untrusted strings (model output,
// OCR/document text, transcripts) can be interpolated into innerHTML without the
// browser parsing them as markup. The threat here is content that flows
// model -> DOM: a jailbroken/buggy model or a malicious scanned document could
// otherwise emit <img onerror=…> and run script in the tech's session (XSS).
export function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}
