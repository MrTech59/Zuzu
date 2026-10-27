"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  getConversation,
  hasToken,
  listConversations,
  streamChat,
  type ConversationSummary,
  type Message,
} from "@/lib/api";

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConv, setActiveConv] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    try {
      const { conversations } = await listConversations();
      setConversations(conversations);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations.");
    }
  }, []);

  useEffect(() => {
    if (hasToken()) void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const openConversation = async (id: string) => {
    setError(null);
    setActiveConv(id);
    try {
      const detail = await getConversation(id);
      setMessages(detail.messages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation.");
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setInput("");
    const userMsg: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    const assistantMsg: Message = {
      id: `streaming-${Date.now()}`,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    await streamChat(text, activeConv, {
      onMeta: (conversationId) => {
        setActiveConv(conversationId);
      },
      onDelta: (delta) => {
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, content: last.content + delta };
          return copy;
        });
      },
      onDone: () => {
        setBusy(false);
        void loadConversations();
      },
      onError: (code, message) => {
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = {
            ...last,
            role: "error",
            content: `⚠️ ${message} (${code})`,
          };
          return copy;
        });
        setBusy(false);
      },
    });
  };

  return (
    <div className="chat-window">
      <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0 }}>
        <div style={{ width: 220, flexShrink: 0 }} className="card">
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>Conversations</strong>
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setActiveConv(null);
                setMessages([]);
              }}
            >
              New
            </a>
          </div>
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
            {conversations.map((c) => (
              <a
                key={c.id}
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  void openConversation(c.id);
                }}
                className={activeConv === c.id ? "nav-link active" : "nav-link"}
                style={{ fontSize: 13, color: "var(--text)" }}
              >
                {c.title || "Untitled"}
              </a>
            ))}
            {conversations.length === 0 && (
              <div className="muted">No conversations yet.</div>
            )}
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {error && <div className="error-banner">{error}</div>}
          {!hasToken() && (
            <div className="error-banner">
              Set the API key (top right) to talk to Zuzu.
            </div>
          )}
          <div className="messages" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="empty-state">Say hello to Zuzu 👋</div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`message ${m.role}`}>
                {m.content || (m.role === "assistant" ? "…" : "")}
              </div>
            ))}
          </div>
          <div className="chat-input-row">
            <textarea
              className="chat-input"
              placeholder="Message Zuzu…"
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              disabled={busy}
            />
            <button className="btn" onClick={() => void send()} disabled={busy}>
              {busy ? "…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
