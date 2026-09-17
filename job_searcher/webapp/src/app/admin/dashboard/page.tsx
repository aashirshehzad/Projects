"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "../admin.module.css";

type Tab = "users" | "tokens" | "logs";

type AdminUser = {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
  onboarded: number;
  auth_method: string;
};

type TokenPerUser = { email: string; tokensIn: number; tokensOut: number };
type TokenTotals = { totalIn: number; totalOut: number };
type ActivityLog = {
  id: string;
  user_id: string | null;
  event: string;
  metadata: string | null;
  created_at: string;
};

export default function AdminDashboardPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("users");

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [tokenTotals, setTokenTotals] = useState<TokenTotals>({ totalIn: 0, totalOut: 0 });
  const [perUser, setPerUser] = useState<TokenPerUser[]>([]);
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (tab === "users") {
      fetch("/api/admin/users")
        .then((r) => r.json())
        .then((d) => setUsers(d.users ?? []));
    } else if (tab === "tokens") {
      fetch("/api/admin/tokens")
        .then((r) => r.json())
        .then((d) => {
          setTokenTotals(d.totals ?? { totalIn: 0, totalOut: 0 });
          setPerUser(d.perUser ?? []);
        });
    } else if (tab === "logs") {
      fetch(`/api/admin/logs?q=${encodeURIComponent(search)}`)
        .then((r) => r.json())
        .then((d) => setLogs(d.logs ?? []));
    }
  }, [tab, search]);

  async function handleLogout() {
    await fetch("/api/admin/logout", { method: "POST" });
    router.push("/admin");
    router.refresh();
  }

  return (
    <div className={styles.shell}>
      <div className={styles.header}>
        <h1 className={styles.headerTitle}>EasyPezee Admin</h1>
        <button type="button" className="btn btn-outline" onClick={handleLogout}>
          Sign out
        </button>
      </div>

      <div className={styles.tabs}>
        {(["users", "tokens", "logs"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`${styles.tab} ${tab === t ? styles.tabActive : ""}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className={styles.panel}>
        {tab === "users" && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Method</th>
                <th>Registered</th>
                <th>Onboarded</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.name ?? "—"}</td>
                  <td>{u.auth_method}</td>
                  <td>{new Date(u.created_at).toLocaleDateString()}</td>
                  <td>{u.onboarded ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "tokens" && (
          <>
            <div className={styles.statsRow}>
              <div className="card">
                <strong>{tokenTotals.totalIn.toLocaleString()}</strong>
                <p>Tokens in</p>
              </div>
              <div className="card">
                <strong>{tokenTotals.totalOut.toLocaleString()}</strong>
                <p>Tokens out</p>
              </div>
              <div className="card">
                <strong>{(tokenTotals.totalIn + tokenTotals.totalOut).toLocaleString()}</strong>
                <p>Total</p>
              </div>
            </div>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Tokens in</th>
                  <th>Tokens out</th>
                </tr>
              </thead>
              <tbody>
                {perUser.map((row) => (
                  <tr key={row.email}>
                    <td>{row.email}</td>
                    <td>{row.tokensIn.toLocaleString()}</td>
                    <td>{row.tokensOut.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {tab === "logs" && (
          <>
            <input
              className={styles.searchInput}
              placeholder="Search logs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Metadata</th>
                  <th>User</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{log.event}</td>
                    <td>{log.metadata ?? "—"}</td>
                    <td>{log.user_id ?? "system"}</td>
                    <td>{new Date(log.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
