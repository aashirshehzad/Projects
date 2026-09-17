import { auth } from "@/lib/auth";
import {
  countApplicationsForUser,
  listCvsForUser,
  findUserById,
} from "@/lib/db";
import { getDb } from "@/lib/schema";
import { StatsCard } from "@/components/StatsCard";
import styles from "./overview.module.css";

type ActivityRow = {
  id: string;
  event: string;
  metadata: string | null;
  created_at: string;
};

function formatEvent(event: string) {
  return event.replaceAll("_", " ");
}

function profileCompleteness(user: {
  linkedin_url: string | null;
  onboarded: number;
}, hasCv: boolean) {
  let score = 0;
  if (user.onboarded) score += 40;
  if (user.linkedin_url) score += 30;
  if (hasCv) score += 30;
  return score;
}

export default async function DashboardOverviewPage() {
  const session = await auth();
  const userId = session!.user.id;

  const user = findUserById(userId)!;
  const cvs = listCvsForUser(userId);
  const applicationCount = countApplicationsForUser(userId);
  const recentActivity = getDb()
    .prepare(
      "SELECT * FROM activity_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 8"
    )
    .all(userId) as ActivityRow[];

  const completeness = profileCompleteness(user, cvs.length > 0);

  return (
    <div>
      <h1 className={styles.title}>
        Welcome back<em>, {user.name ?? "there"}</em>
      </h1>

      <div className={styles.stats}>
        <StatsCard label="Total applications" value={applicationCount} />
        <StatsCard label="CVs uploaded" value={cvs.length} />
        <StatsCard label="Profile completeness" value={`${completeness}%`} />
      </div>

      <div className={styles.grid}>
        <div className={`card ${styles.activityCard}`}>
          <h2 className={styles.sectionTitle}>Recent activity</h2>
          {recentActivity.length === 0 ? (
            <p className={styles.empty}>No activity yet — get started below.</p>
          ) : (
            <ul className={styles.activityList}>
              {recentActivity.map((item) => (
                <li key={item.id} className={styles.activityItem}>
                  <span>{formatEvent(item.event)}</span>
                  <time>{new Date(item.created_at).toLocaleString()}</time>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={`card ${styles.actionsCard}`}>
          <h2 className={styles.sectionTitle}>Quick actions</h2>
          <a href="/dashboard/cvs" className="btn btn-dark" style={{ width: "100%" }}>
            Manage CVs
          </a>
          <a
            href="/dashboard/jobs"
            className="btn btn-outline"
            style={{ width: "100%" }}
          >
            View applications
          </a>
        </div>
      </div>
    </div>
  );
}
