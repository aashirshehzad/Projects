"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./jobs.module.css";

type Application = {
  id: string;
  job_title: string;
  company: string;
  status: string;
  applied_at: string;
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  applied: "Applied",
  rejected: "Rejected",
};

export default function JobsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [status, setStatus] = useState("pending");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch("/api/applications");
    const data = await res.json();
    setApplications(data.applications ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetch("/api/applications")
      .then((res) => res.json())
      .then((data) => {
        setApplications(data.applications ?? []);
        setLoading(false);
      });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!jobTitle.trim() || !company.trim()) return;
    setSubmitting(true);
    await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobTitle, company, status }),
    });
    setJobTitle("");
    setCompany("");
    setStatus("pending");
    setSubmitting(false);
    await load();
  }

  return (
    <div>
      <h1 className={styles.title}>Applications</h1>
      <p className={styles.subtitle}>Track every job you&apos;ve applied to.</p>

      <form className={`card ${styles.form}`} onSubmit={handleSubmit}>
        <input
          placeholder="Job title"
          value={jobTitle}
          onChange={(e) => setJobTitle(e.target.value)}
          required
        />
        <input
          placeholder="Company"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          required
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">Pending</option>
          <option value="applied">Applied</option>
          <option value="rejected">Rejected</option>
        </select>
        <button type="submit" disabled={submitting} className="btn btn-dark">
          {submitting ? "Adding..." : "Add"}
        </button>
      </form>

      {loading ? (
        <p className={styles.subtitle}>Loading...</p>
      ) : applications.length === 0 ? (
        <p className={styles.subtitle}>No applications logged yet.</p>
      ) : (
        <div className={`card ${styles.tableCard}`}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Job title</th>
                <th>Company</th>
                <th>Status</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app) => (
                <tr key={app.id}>
                  <td>{app.job_title}</td>
                  <td>{app.company}</td>
                  <td>
                    <span className={`${styles.badge} ${styles[app.status]}`}>
                      {STATUS_LABEL[app.status] ?? app.status}
                    </span>
                  </td>
                  <td>{new Date(app.applied_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
