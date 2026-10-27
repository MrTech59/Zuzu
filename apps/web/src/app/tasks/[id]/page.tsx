"use client";

import { useEffect, useState } from "react";
import { use } from "react";
import { getTask, type TaskDetail } from "@/lib/api";

export default function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const t = await getTask(id);
        if (alive) {
          setTask(t);
          setError(null);
        }
      } catch (err) {
        if (alive)
          setError(err instanceof Error ? err.message : "Failed to load task.");
      }
    };
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [id]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!task) return <div className="empty-state">Loading task…</div>;

  return (
    <div>
      <h2>
        {task.title}{" "}
        <span className={`status-badge ${task.status}`}>{task.status}</span>
      </h2>
      <p className="muted">
        Agent: {task.agent} · Step {task.step_count}/{task.max_steps}
        {task.finished_at
          ? ` · finished ${new Date(task.finished_at).toLocaleString()}`
          : ""}
      </p>
      {task.failure_reason && (
        <div className="error-banner">Failure: {task.failure_reason}</div>
      )}
      {task.result && (
        <div className="card">
          <strong>Result</strong>
          <pre style={{ whiteSpace: "pre-wrap", margin: "8px 0 0" }}>
            {safeParseResult(task.result)}
          </pre>
        </div>
      )}
      <div className="card">
        <strong>Steps</strong>
        {task.steps.length === 0 ? (
          <div className="muted" style={{ marginTop: 8 }}>
            Planning…
          </div>
        ) : (
          <table className="table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Tool</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {task.steps.map((s) => (
                <tr key={s.id}>
                  <td>{s.position}</td>
                  <td>{s.name}</td>
                  <td className="muted">{s.tool ?? "—"}</td>
                  <td>
                    <span className={`status-badge ${s.status}`}>{s.status}</span>
                  </td>
                  <td className="muted">{s.detail ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {task.approvals.length > 0 && (
        <div className="card">
          <strong>Approvals</strong>
          <table className="table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>Action</th>
                <th>Resource</th>
                <th>Status</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {task.approvals.map((a) => (
                <tr key={a.id}>
                  <td>{a.action}</td>
                  <td className="muted">{a.resource}</td>
                  <td>
                    <span className={`status-badge ${a.status}`}>{a.status}</span>
                  </td>
                  <td className="muted">{a.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function safeParseResult(result: string): string {
  try {
    const parsed = JSON.parse(result);
    if (parsed && typeof parsed === "object" && "summary" in parsed) {
      return String(parsed.summary);
    }
    return result;
  } catch {
    return result;
  }
}
