import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  apiFetch,
  ApiError,
  getToken,
  setToken,
  streamChat,
  sendChat,
} from "@/lib/api";

// Minimal in-memory localStorage for the node test environment.
if (typeof globalThis.localStorage === "undefined") {
  const store = new Map<string, string>();
  (globalThis as Record<string, unknown>).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => void store.clear(),
  };
}

describe("api client", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("tok-123");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("attaches bearer token from storage", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/health");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer tok-123",
    );
  });

  it("maps 401 to unauthorized ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ error: { code: "unauthorized", message: "nope" } }),
          { status: 401 },
        ),
      ),
    );
    await expect(apiFetch("/tasks")).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });
  });

  it("surfaces backend error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: { code: "policy_denied", message: "Denied by policy." },
          }),
          { status: 403 },
        ),
      ),
    );
    await expect(apiFetch("/tasks")).rejects.toMatchObject({
      status: 403,
      code: "policy_denied",
      message: "Denied by policy.",
    });
  });

  it("maps network failure to a clear ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(apiFetch("/health")).rejects.toMatchObject({
      code: "network_error",
      status: 0,
    });
  });

  it("token roundtrip", () => {
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken("");
    expect(getToken()).toBe("");
  });

  it("sendChat posts JSON body", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          conversation_id: "c1",
          user_message: { id: "m1", role: "user", content: "hi", created_at: "" },
          assistant_message: {
            id: "m2",
            role: "assistant",
            content: "hello",
            created_at: "",
          },
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const result = await sendChat("hi", null);
    expect(result.assistant_message.content).toBe("hello");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/chat");
    expect(JSON.parse(init.body as string)).toEqual({
      message: "hi",
      conversation_id: undefined,
    });
  });
});

describe("streamChat SSE parsing", () => {
  function sseResponse(events: string[]): Response {
    const stream = new ReadableStream({
      start(controller) {
        for (const e of events) controller.enqueue(new TextEncoder().encode(e));
        controller.close();
      },
    });
    return new Response(stream, { status: 200 });
  }

  it("parses meta, deltas, done", async () => {
    localStorage.setItem("zuzu_api_key", "tok");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          'data: {"type":"meta","conversation_id":"c9"}\n\n',
          'data: {"type":"delta","content":"Hel"}\n\n',
          'data: {"type":"delta","content":"lo"}\n\n',
          'data: {"type":"done","message_id":"m9","finish_reason":"stop"}\n\n',
        ]),
      ),
    );
    const got: { meta?: string; text: string; done?: string; errors: string[] } = {
      text: "",
      errors: [],
    };
    await streamChat("hi", null, {
      onMeta: (id) => (got.meta = id),
      onDelta: (c) => (got.text += c),
      onDone: (id) => (got.done = id),
      onError: (code) => got.errors.push(code),
    });
    expect(got.meta).toBe("c9");
    expect(got.text).toBe("Hello");
    expect(got.done).toBe("m9");
    expect(got.errors).toEqual([]);
  });

  it("surfaces error events", async () => {
    localStorage.setItem("zuzu_api_key", "tok");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          'data: {"type":"error","code":"provider_timeout","message":"timed out"}\n\n',
        ]),
      ),
    );
    const errors: string[] = [];
    await streamChat("hi", null, { onError: (code) => errors.push(code) });
    expect(errors).toEqual(["provider_timeout"]);
  });
});
