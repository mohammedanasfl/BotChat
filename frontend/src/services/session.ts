import { createSession } from "./api";

const STORAGE_KEY = "abinaya-chat-session";
const RENEW_BEFORE_MS = 60_000; // renew a minute before expiry

interface StoredSession {
  token: string;
  expiresAt: number;
}

/**
 * Anonymous session tokens. Kept in sessionStorage so navigating between the website's pages
 * doesn't force a new Turnstile check; cleared when the tab closes.
 */
export class SessionManager {
  private inFlight: Promise<string> | null = null;
  private memory: StoredSession | null = null;

  constructor(
    private readonly apiUrl: string,
    private readonly getTurnstileToken: () => Promise<string>,
    private readonly storage: Storage | null = safeSessionStorage(),
  ) {}

  async getToken(): Promise<string> {
    const stored = this.read();
    if (stored && stored.expiresAt - Date.now() > RENEW_BEFORE_MS) return stored.token;
    this.inFlight ??= this.renew().finally(() => (this.inFlight = null));
    return this.inFlight;
  }

  clear(): void {
    this.memory = null;
    this.storage?.removeItem(STORAGE_KEY);
  }

  private async renew(): Promise<string> {
    const session = await createSession(this.apiUrl, await this.getTurnstileToken());
    this.memory = session;
    this.storage?.setItem(STORAGE_KEY, JSON.stringify(session));
    return session.token;
  }

  private read(): StoredSession | null {
    if (this.memory) return this.memory;
    try {
      const raw = this.storage?.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as StoredSession) : null;
    } catch {
      return null;
    }
  }
}

function safeSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null; // blocked storage (privacy modes): the in-memory copy still works
  }
}
