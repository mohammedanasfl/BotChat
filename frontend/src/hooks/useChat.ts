import { useCallback, useRef, useState } from "react";
import { ApiError, streamChat, type HistoryItem } from "../services/api";
import type { SessionManager } from "../services/session";
import type { SseEvent } from "../services/sse";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "done" | "error";
}

const MAX_HISTORY = 10; // matches the backend's MAX_HISTORY_MESSAGES

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return "You're sending messages quickly. Please wait a minute and try again.";
    if (error.status === 403) return "We couldn't verify your browser. Please reload the page and try again.";
    if (error.status === 422) return error.message || "Please shorten your message and try again.";
  }
  return "The assistant is temporarily unavailable. Please try again.";
}

export function useChat(apiUrl: string, session: SessionManager) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const conversationId = useRef(crypto.randomUUID());

  const update = (id: string, change: (m: ChatMessage) => ChatMessage) =>
    setMessages((list) => list.map((m) => (m.id === id ? change(m) : m)));

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;

      const history: HistoryItem[] = messages
        .filter((m) => m.status === "done" && m.content)
        .slice(-MAX_HISTORY)
        .map(({ role, content }) => ({ role, content }));
      const assistantId = crypto.randomUUID();
      setMessages((list) => [
        ...list,
        { id: crypto.randomUUID(), role: "user", content: message, status: "done" },
        { id: assistantId, role: "assistant", content: "", status: "streaming" },
      ]);
      setBusy(true);
      controller.current = new AbortController();

      const onEvent = ({ event, data }: SseEvent) => {
        const payload = data as { text?: string; message?: string };
        if (event === "token") update(assistantId, (m) => ({ ...m, content: m.content + (payload.text ?? "") }));
        else if (event === "complete") update(assistantId, (m) => ({ ...m, status: "done" }));
        else if (event === "error")
          update(assistantId, (m) => ({ ...m, status: "error", content: m.content || errorMessage(null) }));
      };

      const attempt = async () =>
        streamChat(
          apiUrl,
          { message, history, conversation_id: conversationId.current },
          await session.getToken(),
          onEvent,
          controller.current!.signal,
        );

      try {
        try {
          await attempt();
        } catch (error) {
          // Expired or rejected session: renew once (silently, via Turnstile) and retry.
          if (!(error instanceof ApiError && error.status === 401)) throw error;
          session.clear();
          await attempt();
        }
        update(assistantId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
      } catch (error) {
        if (controller.current?.signal.aborted) {
          update(assistantId, (m) => ({ ...m, status: "done", content: m.content || "(stopped)" }));
        } else {
          update(assistantId, (m) => ({ ...m, status: "error", content: errorMessage(error) }));
        }
      } finally {
        setBusy(false);
        controller.current = null;
      }
    },
    [apiUrl, busy, messages, session],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  return { messages, busy, send, stop };
}
