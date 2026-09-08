// Turns a raw thrown error (api.ts's `j()` throws `new Error("${status}: ${bodyText}")`
// on any non-2xx response) into a clean, client-presentable message - per
// user directive, never show a raw JSON error blob on screen, since this
// runs live in front of clients during demos. The backend already writes
// human-readable {"detail": "..."} messages for every error it raises on
// purpose (see gemini_extraction.human_readable_error, pinned_scans reject
// messages, etc.) - this just extracts that text instead of dumping the
// whole "Error: 502: {...}" string, and falls back to a generic, still-
// presentable message for anything that doesn't parse (a network failure,
// an unexpected 500, etc.).
export function formatApiError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);

  const match = raw.match(/^(\d{3}):\s*([\s\S]*)$/);
  if (match) {
    const [, , body] = match;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed.detail === "string" && parsed.detail.trim()) {
        return parsed.detail;
      }
    } catch {
      // body wasn't JSON (or had no .detail) - fall through to the generic message below
    }
    return "Something went wrong while processing this request. Please try again.";
  }

  // No "STATUS: body" shape at all - most likely the request never reached
  // the server (network drop, backend not running).
  if (/failed to fetch|networkerror|load failed/i.test(raw)) {
    return "Couldn't reach the server. Please check your connection and try again.";
  }
  return "Something went wrong while processing this request. Please try again.";
}
