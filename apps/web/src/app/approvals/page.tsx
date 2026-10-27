"use client";

import { useCallback, useEffect, useState } from "react";
import { decideApproval, listApprovals, type Approval } from "@/lib/api";

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { approvals } = await listApprovals();
      setApprovals(approvals);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load approvals.");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [load]);

  const decide = async (a: Approval, approve: boolean) => {
    setBusyId(a.id);
    try {
      // confirm_action binds the decision to the action kind that was shown.
      await decideApproval(a.id, approve, a.action);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Decision failed.");
    } finally {
      setBusyId(null);
    }
  };

  const pending = approvals.filter((a) => a.status === "pending");
  const past = approvals.filter((a) => a.status !== "pending");

  return (
    <div>
      <h2>Approvals</h2>
      {error && <div className="error-banner">{error}</div>}

      {pending.length === 0 ? (
        <div className="empty-state">Nothing is waiting for approval.</div>
      ) : (
        pending.map((a) => (
          <div className="card" key={a.id}>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span className={`status-badge ${a.status}`}>{a.action}</span>
              <strong>{a.resource}</strong>
            </div>
            <p className="muted" style={{ margin: "8px 0" }}>
              {a.reason}
              <br />
              requested {new Date(a.created_at).toLocaleString()} · expires{" "}
              {new Date(a.expires_at).toLocaleTimeString()}
            </p>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn approve"
                disabled={busyId === a.id}
                onClick={() => void decide(a, true)}
              >
                Approve
              </button>
              <button
                className="btn danger"
                disabled={busyId === a.id}
                onClick={() => void decide(a, false)}
              >
                Reject
              </button>
            </div>
          </div>
        ))
      )}

      {past.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Decided</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Resource</th>
                <th>Status</th>
                <th>Decided</th>
              </tr>
            </thead>
            <tbody>
              {past.map((a) => (
                <tr key={a.id}>
                  <td>{a.action}</td>
                  <td className="muted">{a.resource}</td>
                  <td>
                    <span className={`status-badge ${a.status}`}>{a.status}</span>
                  </td>
                  <td className="muted">
                    {a.created_at ? new Date(a.created_at).toLocaleString() : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
