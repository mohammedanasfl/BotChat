import { SseParser, type SseEvent } from "./sse";

export interface HistoryItem {
  role: "user" | "assistant";
  content: string;
}

/** An error response from the API, using the backend's error envelope. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    return new ApiError(response.status, body?.error?.code ?? "unknown", body?.error?.message ?? "");
  } catch {
    return new ApiError(response.status, "unknown", response.statusText);
  }
}

export async function createSession(
  apiUrl: string,
  turnstileToken: string,
): Promise<{ token: string; expiresAt: number }> {
  const response = await fetch(`${apiUrl}/api/session`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ turnstile_token: turnstileToken }),
  });
  if (!response.ok) throw await toApiError(response);
  const body = await response.json();
  return { token: body.session_token, expiresAt: Date.now() + body.expires_in * 1000 };
}

export async function streamChat(
  apiUrl: string,
  payload: { message: string; history: HistoryItem[]; conversation_id: string },
  sessionToken: string,
  onEvent: (event: SseEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${apiUrl}/api/chat`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "text/event-stream",
      authorization: `Bearer ${sessionToken}`,
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok || !response.body) throw await toApiError(response);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const event of parser.feed(value)) onEvent(event);
  }
}
