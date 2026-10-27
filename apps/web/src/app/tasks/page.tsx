"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  cancelTask,
  createTask,
  listTasks,
  type TaskSummary,
} from "@/lib/api";

const AGENTS = [
  ["researcher", "Researcher — approved web research (read-only)"],
  ["developer", "Developer — workspace file changes (approval required)"],
  ["tester", "Tester — run permitted checks (approval required)"],
  ["homelab-observer", "Homelab observer — read-only diagnostics"],
] as const;

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [agent, setAgent] = useState<string>("researcher");
  const [title, setTitle] = useState("");
  const [instruction, setInstruction] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    try {
      const { tasks } = await listTasks();
      setTasks(tasks);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tasks.");
    }
  };

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 4000);
    return () => clearInterval(t);
  }, []);

  const submit = async () => {
    if (!title.trim() || !instruction.trim()) return;
    setCreating(true);
    try {
      await createTask(agent, title.trim(), instruction.trim());
      setTitle("");
      setInstruction("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task.");
    } finally {
      setCreating(false);
    }
  };

  const cancel = async (id: string) => {
    try {
      await cancelTask(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed.");
    }
  };

  return (
    <div>
      <h2>Tasks</h2>
      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <strong>New task</strong>
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          <select value={agent} onChange={(e) => setAgent(e.target.value)} className="chat-input">
            {AGENTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input
            className="chat-input"
            placeholder="Task title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            className="chat-input"
            placeholder="What should the agent do?"
            rows={3}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <div>
            <button className="btn" onClick={() => void submit()} disabled={creating}>
              {creating ? "Creating…" : "Create task"}
            </button>
          </div>
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className="empty-state">No tasks yet.</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Agent</th>
              <th>Status</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td>
                  <a href={`/tasks/${t.id}`}>{t.title}</a>
                </td>
                <td className="muted">{t.agent}</td>
                <td>
                  <span className={`status-badge ${t.status}`}>{t.status}</span>
                </td>
                <td className="muted">{new Date(t.created_at).toLocaleString()}</td>
                <td>
                  {!["succeeded", "failed", "cancelled"].includes(t.status) && (
                    <button className="btn secondary" onClick={() => void cancel(t.id)}>
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
