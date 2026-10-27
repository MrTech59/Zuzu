"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getApiBase, getToken, setApiBase, setToken } from "@/lib/api";

export default function SetupPage() {
  const router = useRouter();
  const [apiUrl, setApiUrl] = useState<string>("");
  const [apiKey, setApiKey] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [alreadyConfigured, setAlreadyConfigured] = useState(false);

  useEffect(() => {
    setApiUrl(getApiBase());
    if (getToken()) {
      setApiKey("••••••••");
      setAlreadyConfigured(true);
    }
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);

    const trimmedUrl = apiUrl.trim().replace(/\/$/, "");
    const trimmedKey = apiKey.trim();

    try {
      const healthResp = await fetch(`${trimmedUrl}/health`);
      if (!healthResp.ok) {
        throw new Error("The API health check failed. Is the backend running?");
      }
      const readyResp = await fetch(`${trimmedUrl}/ready`, {
        headers: { Authorization: `Bearer ${trimmedKey}` },
      });
      if (!readyResp.ok) {
        throw new Error("The API key was rejected. Check the key and try again.");
      }
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : "Setup failed.");
      return;
    }

    setApiBase(trimmedUrl);
    if (!alreadyConfigured || apiKey !== "••••••••") {
      setToken(trimmedKey);
    }
    setBusy(false);
    router.push("/");
  }

  return (
    <main className="setup-container" style={{ maxWidth: 480, margin: "4rem auto", padding: "0 1rem" }}>
      <h1>Zuzu first-run setup</h1>
      {alreadyConfigured && (
        <p data-testid="already-configured" style={{ color: "var(--success)" }}>
          API key is already stored. You can update it below.
        </p>
      )}
      <form onSubmit={handleSubmit}>
        <label htmlFor="apiUrl">API base URL</label>
        <input
          id="apiUrl"
          data-testid="setup-api-url"
          type="url"
          value={apiUrl}
          onChange={(e) => setApiUrl(e.target.value)}
          placeholder="http://127.0.0.1:8000/api/v1"
          required
          style={{ width: "100%", marginBottom: "1rem" }}
        />

        <label htmlFor="apiKey">API key</label>
        <input
          id="apiKey"
          data-testid="setup-api-key"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="Paste the ZUZU_API_KEY value from .env"
          required={!alreadyConfigured}
          style={{ width: "100%", marginBottom: "1rem" }}
        />

        {error && (
          <div data-testid="setup-error" style={{ color: "var(--error)", marginBottom: "1rem" }}>
            {error}
          </div>
        )}

        <button type="submit" data-testid="setup-submit" disabled={busy}>
          {busy ? "Connecting..." : "Save and continue"}
        </button>
      </form>
    </main>
  );
}
