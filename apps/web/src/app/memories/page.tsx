"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteMemory, listMemories, type Memory } from "@/lib/api";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [query, setQuery] = useState("");
  const [newContent, setNewContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { memories } = await listMemories(query || undefined);
      setMemories(memories);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories.");
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (!newContent.trim()) return;
    setBusy(true);
    try {
      const { apiFetch } = await import("@/lib/api");
      await apiFetch("/memories", {
        method: "POST",
        body: JSON.stringify({ content: newContent.trim() }),
      });
      setNewContent("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create memory.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteMemory(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  return (
    <div>
      <h2>Memories</h2>
      <p className="muted">
        Durable facts Zuzu can use. Separate from conversation history; delete
        anytime.
      </p>
      {error && <div className="error-banner">{error}</div>}

      <div className="card" style={{ display: "flex", gap: 8 }}>
        <input
          className="chat-input"
          placeholder="Search memories…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="card" style={{ display: "flex", gap: 8 }}>
        <input
          className="chat-input"
          placeholder="New memory…"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void create();
          }}
        />
        <button className="btn" onClick={() => void create()} disabled={busy}>
          Add
        </button>
      </div>

      {memories.length === 0 ? (
        <div className="empty-state">
          {query ? "No matching memories." : "No memories yet."}
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Content</th>
              <th>Kind</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {memories.map((m) => (
              <tr key={m.id}>
                <td>{m.content}</td>
                <td className="muted">{m.kind}</td>
                <td className="muted">{new Date(m.created_at).toLocaleString()}</td>
                <td>
                  <button className="btn secondary" onClick={() => void remove(m.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
