/**
 * Cloudflare Turnstile in explicit mode. The container lives in the LIGHT DOM (slotted into the
 * widget's shadow root) because Turnstile looks elements up on `document` and doesn't support
 * Shadow DOM.
 */
const SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const ACTION = "chat_session"; // checked by the Worker

interface TurnstileApi {
  render(container: HTMLElement, options: Record<string, unknown>): string;
  execute(widgetId: string): void;
  reset(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let scriptPromise: Promise<TurnstileApi> | null = null;

function loadScript(): Promise<TurnstileApi> {
  scriptPromise ??= new Promise((resolve, reject) => {
    if (window.turnstile) return resolve(window.turnstile);
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("Turnstile unavailable")));
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error("Could not load Turnstile"));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export class TurnstileClient {
  private widgetId: string | null = null;
  private pending: { resolve: (token: string) => void; reject: (error: Error) => void } | null = null;

  constructor(
    private readonly container: HTMLElement,
    private readonly siteKey: string,
  ) {}

  /** Get a fresh single-use token. Usually invisible; shows a challenge only when needed. */
  async getToken(): Promise<string> {
    const turnstile = await loadScript();
    const token = new Promise<string>((resolve, reject) => (this.pending = { resolve, reject }));
    if (this.widgetId === null) {
      this.widgetId = turnstile.render(this.container, {
        sitekey: this.siteKey,
        action: ACTION,
        appearance: "interaction-only",
        execution: "execute",
        callback: (value: string) => this.pending?.resolve(value),
        "error-callback": () => this.pending?.reject(new Error("Verification failed")),
        "expired-callback": () => this.widgetId && turnstile.reset(this.widgetId),
      });
    } else {
      turnstile.reset(this.widgetId); // tokens are single-use
    }
    turnstile.execute(this.widgetId);
    return token;
  }
}
