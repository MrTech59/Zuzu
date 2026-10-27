"use client";

/**
 * Zuzu API client.
 *
 * - The API token lives in localStorage and is attached as a Bearer header.
 * - Provider/API errors are surfaced as typed ApiError, never swallowed.
 * - Streaming chat parses the backend's SSE format incrementally.
 */

export const API_BASE: string =
  process.env.NEXT_PUBLIC_ZUZU_API_URL || "http://127.0.0.1:8000/api/v1";

const TOKEN_STORAGE_KEY = "zuzu_api_key";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export function getToken(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

export function setToken(token: string): void {
  if (typeof localStorage === "undefined") return;
  if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function hasToken(): boolean {
  return Boolean(getToken());
}

export interface ApiErrorBody {
  error: { code: string; message: string; detail?: unknown };
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body) headers["Content-Type"] = "application/json";

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (err) {
    throw new ApiError(
      "Could not reach the Zuzu API. Is the backend running?",
      "network_error",
      0,
    );
  }

  if (resp.status === 401) {
    throw new ApiError(
      "Unauthorized: check the API key in the header.",
      "unauthorized",
      401,
    );
  }

  if (!resp.ok) {
    let code = "http_error";
    let message = `Request failed with status ${resp.status}.`;
    try {
      const body = (await resp.json()) as ApiErrorBody;
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      /* keep defaults */
    }
    throw new ApiError(message, code, resp.status);
  }

  return (await resp.json()) as T;
}

/* ------------------------------------------------------------------ types */

export interface Health {
  status: string;
  version: string;
  uptime_seconds: number;
}

export interface Ready {
  ready: boolean;
  checks: { database: string; mcp: string };
}

export interface Message {
  id: string;
  role: string;
  content: string;
  model?: string | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  messages: Message[];
}

export interface TaskStep {
  id: string;
  position: number;
  name: string;
  tool: string | null;
  status: string;
  detail: string | null;
}

export interface Approval {
  id: string;
  status: string;
  action: string;
  resource: string;
  reason: string | null;
  created_at: string;
  expires_at: string;
}

export interface TaskDetail {
  id: string;
  agent: string;
  title: string;
  status: string;
  failure_reason: string | null;
  step_count: number;
  max_steps: number;
  result: string | null;
  created_at: string;
  finished_at: string | null;
  running: boolean;
  steps: TaskStep[];
  approvals: Approval[];
}

export interface TaskSummary {
  id: string;
  agent: string;
  title: string;
  status: string;
  created_at: string;
  step_count: number;
  failure_reason: string | null;
}

export interface Memory {
  id: string;
  kind: string;
  content: string;
  source: string;
  created_at: string;
}

/* ---------------------------------------------------------------- calls */

export async function getHealth(): Promise<Health> {
  return apiFetch<Health>("/health");
}

export async function getReady(): Promise<Ready> {
  return apiFetch<Ready>("/ready");
}

export async function listConversations(): Promise<{ conversations: ConversationSummary[] }> {
  return apiFetch("/conversations");
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return apiFetch(`/conversations/${id}`);
}

export async function listTasks(): Promise<{ tasks: TaskSummary[] }> {
  return apiFetch("/tasks");
}

export async function getTask(id: string): Promise<TaskDetail> {
  return apiFetch(`/tasks/${id}`);
}

export async function cancelTask(id: string): Promise<{ id: string; status: string }> {
  return apiFetch(`/tasks/${id}/cancel`, { method: "POST" });
}

export async function listApprovals(): Promise<{ approvals: Approval[] }> {
  return apiFetch("/approvals");
}

export async function decideApproval(
  id: string,
  approve: boolean,
  confirmAction?: string,
): Promise<{ id: string; status: string }> {
  return apiFetch(`/approvals/${id}/decision`, {
    method: "POST",
    body: JSON.stringify({
      approve,
      decided_by: "user",
      ...(confirmAction ? { confirm_action: confirmAction } : {}),
    }),
  });
}

export async function listMemories(query?: string): Promise<{ memories: Memory[] }> {
  const qs = query ? `?query=${encodeURIComponent(query)}` : "";
  return apiFetch(`/memories${qs}`);
}

export async function deleteMemory(id: string): Promise<{ deleted: string }> {
  return apiFetch(`/memories/${id}`, { method: "DELETE" });
}

export interface ChatResult {
  conversation_id: string;
  user_message: Message;
  assistant_message: Message;
}

export async function sendChat(
  message: string,
  conversationId?: string | null,
): Promise<ChatResult> {
  return apiFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId ?? undefined }),
  });
}

export async function createTask(
  agent: string,
  title: string,
  instruction: string,
): Promise<TaskDetail> {
  return apiFetch("/tasks", {
    method: "POST",
    body: JSON.stringify({ agent, title, instruction }),
  });
}

/* ------------------------------------------------------------ SSE chat */

export interface StreamCallbacks {
  onMeta?: (conversationId: string) => void;
  onDelta?: (content: string) => void;
  onDone?: (messageId: string) => void;
  onError?: (code: string, message: string) => void;
}

export async function streamChat(
  message: string,
  conversationId: string | null,
  callbacks: StreamCallbacks,
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        conversation_id: conversationId ?? undefined,
        stream: true,
      }),
    });
  } catch {
    callbacks.onError?.("network_error", "Could not reach the Zuzu API.");
    return;
  }

  if (resp.status === 401) {
    callbacks.onError?.("unauthorized", "Unauthorized: check the API key.");
    return;
  }
  if (!resp.ok || !resp.body) {
    callbacks.onError?.("http_error", `Chat failed with status ${resp.status}.`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of rawEvent.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        let evt: Record<string, unknown>;
        try {
          evt = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        switch (evt.type) {
          case "meta":
            callbacks.onMeta?.(evt.conversation_id as string);
            break;
          case "delta":
            callbacks.onDelta?.(evt.content as string);
            break;
          case "done":
            callbacks.onDone?.(evt.message_id as string);
            return;
          case "error":
            callbacks.onError?.(
              (evt.code as string) || "stream_error",
              (evt.message as string) || "Unknown stream error.",
            );
            return;
        }
      }
    }
  }
}
