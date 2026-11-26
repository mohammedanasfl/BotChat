import { afterEach, describe, expect, it, vi } from "vitest";
import { errorMessage } from "../src/hooks/useChat";
import { ApiError, streamChat } from "../src/services/api";
import { SessionManager } from "../src/services/session";
import { SseParser } from "../src/services/sse";

afterEach(() => vi.restoreAllMocks());

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    },
  };
}

describe("SseParser", () => {
  it("parses events split across chunks and CRLF", () => {
    const parser = new SseParser();
    expect(parser.feed('event: token\r\ndata: {"text":"Hel')).toEqual([]);
    expect(parser.feed('lo"}\r\n\r\nevent: complete\ndata: {"finish_reason":"stop"}\n\n')).toEqual([
      { event: "token", data: { text: "Hello" } },
      { event: "complete", data: { finish_reason: "stop" } },
    ]);
  });
});

describe("streamChat", () => {
  it("emits events from a streamed SSE body", async () => {
    const chunks = ['event: start\ndata: {"request_id":"r"}\n\n', 'event: token\ndata: {"text":"Hi"}\n\n'];
    const body = new ReadableStream({
      start(controller) {
        for (const c of chunks) controller.enqueue(new TextEncoder().encode(c));
        controller.close();
      },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));
    const events: string[] = [];
    await streamChat("https://api", { message: "hi", history: [], conversation_id: "c" }, "tok",
      (e) => events.push(e.event), new AbortController().signal);

    expect(events).toEqual(["start", "token"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api/api/chat");
    expect((init!.headers as Record<string, string>).authorization).toBe("Bearer tok");
  });

  it("throws ApiError with the backend error code", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "session_expired", message: "Expired" } }), { status: 401 }),
    );
    await expect(
      streamChat("https://api", { message: "hi", history: [], conversation_id: "c" }, "t", () => {},
        new AbortController().signal),
    ).rejects.toMatchObject({ status: 401, code: "session_expired" });
  });
});

describe("SessionManager", () => {
  const sessionResponse = () =>
    new Response(JSON.stringify({ session_token: "S1", expires_in: 900 }), { status: 200 });

  it("creates a session once and reuses it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => sessionResponse());
    const turnstile = vi.fn().mockResolvedValue("T1");
    const manager = new SessionManager("https://api", turnstile, memoryStorage());

    const [a, b] = await Promise.all([manager.getToken(), manager.getToken()]); // concurrent: one request
    expect([a, b, await manager.getToken()]).toEqual(["S1", "S1", "S1"]);
    expect(turnstile).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renews shortly before expiry and after clear()", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => sessionResponse());
    const turnstile = vi.fn().mockResolvedValue("T");
    const storage = memoryStorage();
    storage.setItem("abinaya-chat-session", JSON.stringify({ token: "OLD", expiresAt: Date.now() + 30_000 }));
    const manager = new SessionManager("https://api", turnstile, storage);

    expect(await manager.getToken()).toBe("S1"); // < 60 s left: renewed
    manager.clear();
    await manager.getToken();
    expect(turnstile).toHaveBeenCalledTimes(2);
  });
});

describe("errorMessage", () => {
  it("maps API errors to friendly text", () => {
    expect(errorMessage(new ApiError(429, "rate_limited", ""))).toMatch(/wait a minute/);
    expect(errorMessage(new ApiError(403, "turnstile_failed", ""))).toMatch(/verify/);
    expect(errorMessage(new Error("network"))).toMatch(/temporarily unavailable/);
  });
});
