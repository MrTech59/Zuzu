"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getHealth, hasToken, setToken } from "@/lib/api";

export default function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<"unknown" | "ok" | "down">("unknown");
  const [version, setVersion] = useState("");
  const [key, setKey] = useState("");

  useEffect(() => {
    setKey(hasToken() ? "••••••••" : "");
    let alive = true;
    const check = async () => {
      try {
        const h = await getHealth();
        if (!alive) return;
        setHealth(h.status === "ok" ? "ok" : "down");
        setVersion(h.version);
      } catch {
        if (alive) setHealth("down");
      }
    };
    check();
    const timer = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">🤖 Zuzu</div>
        <Link href="/" className={`nav-link ${pathname === "/" ? "active" : ""}`}>
          Chat
        </Link>
        <Link
          href="/tasks"
          className={`nav-link ${pathname.startsWith("/tasks") ? "active" : ""}`}
        >
          Tasks
        </Link>
        <Link
          href="/approvals"
          className={`nav-link ${pathname.startsWith("/approvals") ? "active" : ""}`}
        >
          Approvals
        </Link>
        <Link
          href="/memories"
          className={`nav-link ${pathname.startsWith("/memories") ? "active" : ""}`}
        >
          Memories
        </Link>
        <div className="muted" style={{ marginTop: "auto" }}>
          {version ? `v${version}` : "Zuzu"}
        </div>
      </nav>
      <div className="main">
        <div className="topbar">
          <span
            className={`health-dot ${health === "ok" ? "ok" : health === "down" ? "err" : ""}`}
            aria-label={`API health: ${health}`}
          />
          <span className="muted">
            API {health === "unknown" ? "checking…" : health}
          </span>
          <input
            className="apikey-input"
            placeholder="API key"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onBlur={() => {
              if (key && key !== "••••••••") setToken(key);
            }}
          />
        </div>
        {children}
      </div>
    </div>
  );
}
