import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { WidgetConfig } from "../config/config";
import { useChat } from "../hooks/useChat";
import type { SessionManager } from "../services/session";

const SUGGESTIONS = [
  "What products do you make?",
  "Can you print our logo on t-shirts?",
  "What is your minimum order quantity?",
  "How do I get a wholesale quote?",
];
const MAX_CHARS = 1000; // matches the backend limit

interface Props {
  config: WidgetConfig;
  session: SessionManager;
  onClose: () => void;
}

export function ChatWindow({ config, session, onClose }: Props) {
  const { messages, busy, send, stop } = useChat(config.apiUrl, session);
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => inputRef.current?.focus(), []);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!draft.trim() || busy) return;
    void send(draft);
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) submit(event);
    if (event.key === "Escape") onClose();
  };

  return (
    <section className="window" role="dialog" aria-label={`${config.title} assistant`}>
      <header className="header">
        <div>
          <p className="title">{config.title}</p>
          <p className="subtitle">Ask about products, orders and policies</p>
        </div>
        <button type="button" className="icon-button" aria-label="Close chat" onClick={onClose}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </header>

      <div className="messages" ref={listRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="empty">
            <p>Hello! How can we help you today?</p>
            <div className="suggestions">
              {SUGGESTIONS.map((text) => (
                <button key={text} type="button" className="suggestion" onClick={() => void send(text)}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`bubble ${m.role} ${m.status}`}>
              {m.content || (m.status === "streaming" ? <span className="typing" aria-label="Typing" /> : null)}
            </div>
          ))
        )}
      </div>

      {/* Turnstile renders here from the light DOM (it can't live inside a shadow root). */}
      <slot name="turnstile" />

      <form className="composer" onSubmit={submit}>
        <textarea
          ref={inputRef}
          value={draft}
          rows={1}
          maxLength={MAX_CHARS}
          placeholder="Type your question…"
          aria-label="Your message"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        {busy ? (
          <button type="button" className="send" onClick={stop} aria-label="Stop answer">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="7" y="7" width="10" height="10" />
            </svg>
          </button>
        ) : (
          <button type="submit" className="send" disabled={!draft.trim()} aria-label="Send message">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 12l16-8-6 16-2-6z" />
            </svg>
          </button>
        )}
      </form>
      <p className="note">
        AI answers from Abinaya's published information. Messages are processed by Google Gemini, so please
        don't share personal details.
      </p>
    </section>
  );
}
