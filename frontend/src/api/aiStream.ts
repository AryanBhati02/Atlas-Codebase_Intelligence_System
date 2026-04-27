/**
 * Streaming AI utility — reads SSE responses token by token.
 *
 * Protocol:
 *   data: {"text": "token"}\n\n   — text chunk
 *   data: {"refs": [...]}\n\n     — reference metadata (Q&A)
 *   data: {"error": "..."}\n\n    — server-side error
 *   data: [DONE]\n\n              — stream complete
 *
 * Uses fetch() + ReadableStream (not EventSource) so it supports POST and
 * custom headers. Supports AbortController for cancellation and retries
 * up to MAX_RETRIES times on network failure.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";
const MAX_RETRIES = 3;

export interface StreamCallbacks {
  /** Called for each text token received. Accumulate with prev => prev + text. */
  onChunk: (text: string) => void;
  /** Called when reference metadata arrives (Q&A endpoint). */
  onRefs?: (refs: Array<{ path: string; relevance_reason: string }>) => void;
  /** Called when the stream finishes cleanly. */
  onDone: () => void;
  /** Called on unrecoverable error after all retries. */
  onError: (error: Error) => void;
}

export interface StreamControl {
  cancel: () => void;
}

/**
 * Start a streaming AI request.
 *
 * @param endpoint  Path relative to API_BASE, e.g. "/ai/explain/stream"
 * @param params    Query params (GET) or JSON body (POST)
 * @param callbacks Token/done/error handlers
 * @param method    "GET" (default) — params go in URL; "POST" — params go in body
 */
export function streamAI(
  endpoint: string,
  params: Record<string, string>,
  callbacks: StreamCallbacks,
  method: "GET" | "POST" = "GET"
): StreamControl {
  const controller = new AbortController();
  let done = false;

  const run = async () => {
    let attempt = 0;

    while (attempt < MAX_RETRIES && !controller.signal.aborted) {
      attempt++;
      try {
        let url = `${API_BASE}${endpoint}`;
        const init: RequestInit = {
          signal: controller.signal,
          headers: {
            Accept: "text/event-stream",
            "Cache-Control": "no-cache",
          },
        };

        if (method === "GET") {
          const qs = new URLSearchParams(params);
          url = `${url}?${qs.toString()}`;
        } else {
          init.method = "POST";
          (init.headers as Record<string, string>)["Content-Type"] = "application/json";
          init.body = JSON.stringify(params);
        }

        const response = await fetch(url, init);

        if (!response.ok) {
          const text = await response.text().catch(() => "");
          throw new Error(`HTTP ${response.status}: ${text.slice(0, 120)}`);
        }
        if (!response.body) {
          throw new Error("Response body is null");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done: streamDone, value } = await reader.read();
          if (streamDone) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          // Keep incomplete last line in buffer
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();

            if (payload === "[DONE]") {
              done = true;
              callbacks.onDone();
              return;
            }

            try {
              const parsed = JSON.parse(payload) as Record<string, unknown>;

              if (typeof parsed.text === "string" && parsed.text) {
                callbacks.onChunk(parsed.text);
              }

              if (Array.isArray(parsed.refs) && callbacks.onRefs) {
                callbacks.onRefs(
                  parsed.refs as Array<{ path: string; relevance_reason: string }>
                );
              }

              if (typeof parsed.error === "string") {
                // Server-side error in stream — treat as done with warning
                callbacks.onChunk(`\n\n*Server error: ${parsed.error}*`);
              }
            } catch {
              // Malformed JSON — skip silently
            }
          }
        }

        // Stream ended without [DONE] — still call onDone
        if (!done) {
          done = true;
          callbacks.onDone();
        }
        return;
      } catch (err) {
        if (controller.signal.aborted) return;

        const isLast = attempt >= MAX_RETRIES;
        if (isLast) {
          callbacks.onError(err instanceof Error ? err : new Error(String(err)));
          return;
        }
        // Exponential back-off before retry
        await new Promise<void>((r) => setTimeout(r, 600 * attempt));
      }
    }
  };

  // Fire and forget — errors surface through callbacks
  run();

  return {
    cancel: () => {
      controller.abort();
      if (!done) {
        done = true;
        callbacks.onDone();
      }
    },
  };
}
