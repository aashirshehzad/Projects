import { randomUUID } from "node:crypto";
import { getDb } from "./schema";

export type User = {
  id: string;
  email: string;
  name: string | null;
  password_hash: string | null;
  google_id: string | null;
  linkedin_url: string | null;
  avatar_url: string | null;
  created_at: string;
  onboarded: number;
};

export type Cv = {
  id: string;
  user_id: string;
  filename: string;
  file_path: string;
  uploaded_at: string;
  is_active: number;
};

export type Application = {
  id: string;
  user_id: string;
  job_title: string;
  company: string;
  status: string;
  applied_at: string;
};

export type TokenUsage = {
  id: string;
  user_id: string | null;
  tokens_in: number;
  tokens_out: number;
  model: string;
  action: string;
  created_at: string;
};

export type ActivityLog = {
  id: string;
  user_id: string | null;
  event: string;
  metadata: string | null;
  created_at: string;
};

export function findUserByEmail(email: string): User | undefined {
  return getDb()
    .prepare("SELECT * FROM users WHERE email = ?")
    .get(email) as User | undefined;
}

export function findUserById(id: string): User | undefined {
  return getDb().prepare("SELECT * FROM users WHERE id = ?").get(id) as
    | User
    | undefined;
}

export function findUserByGoogleId(googleId: string): User | undefined {
  return getDb()
    .prepare("SELECT * FROM users WHERE google_id = ?")
    .get(googleId) as User | undefined;
}

export function createUser(input: {
  email: string;
  name?: string | null;
  passwordHash?: string | null;
  googleId?: string | null;
  avatarUrl?: string | null;
}): User {
  const id = randomUUID();
  const createdAt = new Date().toISOString();
  getDb()
    .prepare(
      `INSERT INTO users (id, email, name, password_hash, google_id, avatar_url, created_at, onboarded)
       VALUES (?, ?, ?, ?, ?, ?, ?, 0)`
    )
    .run(
      id,
      input.email,
      input.name ?? null,
      input.passwordHash ?? null,
      input.googleId ?? null,
      input.avatarUrl ?? null,
      createdAt
    );
  return findUserById(id)!;
}

export function setUserOnboarding(
  userId: string,
  data: { linkedinUrl: string; onboarded: boolean }
) {
  getDb()
    .prepare(
      "UPDATE users SET linkedin_url = ?, onboarded = ? WHERE id = ?"
    )
    .run(data.linkedinUrl, data.onboarded ? 1 : 0, userId);
}

export function listUsers(): User[] {
  return getDb()
    .prepare("SELECT * FROM users ORDER BY created_at DESC")
    .all() as User[];
}

export function listCvsForUser(userId: string): Cv[] {
  return getDb()
    .prepare("SELECT * FROM cvs WHERE user_id = ? ORDER BY uploaded_at DESC")
    .all(userId) as Cv[];
}

export function createCv(input: {
  userId: string;
  filename: string;
  filePath: string;
}): Cv {
  const id = randomUUID();
  const uploadedAt = new Date().toISOString();
  const db = getDb();
  const hasCvs = (
    db.prepare("SELECT COUNT(*) as c FROM cvs WHERE user_id = ?").get(
      input.userId
    ) as { c: number }
  ).c;
  db.prepare(
    `INSERT INTO cvs (id, user_id, filename, file_path, uploaded_at, is_active)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).run(
    id,
    input.userId,
    input.filename,
    input.filePath,
    uploadedAt,
    hasCvs === 0 ? 1 : 0
  );
  return db.prepare("SELECT * FROM cvs WHERE id = ?").get(id) as Cv;
}

export function setActiveCv(userId: string, cvId: string) {
  const db = getDb();
  const tx = db.transaction(() => {
    db.prepare("UPDATE cvs SET is_active = 0 WHERE user_id = ?").run(userId);
    db.prepare(
      "UPDATE cvs SET is_active = 1 WHERE id = ? AND user_id = ?"
    ).run(cvId, userId);
  });
  tx();
}

export function deleteCv(userId: string, cvId: string): Cv | undefined {
  const db = getDb();
  const cv = db
    .prepare("SELECT * FROM cvs WHERE id = ? AND user_id = ?")
    .get(cvId, userId) as Cv | undefined;
  if (!cv) return undefined;
  db.prepare("DELETE FROM cvs WHERE id = ? AND user_id = ?").run(
    cvId,
    userId
  );
  if (cv.is_active) {
    const next = db
      .prepare(
        "SELECT id FROM cvs WHERE user_id = ? ORDER BY uploaded_at DESC LIMIT 1"
      )
      .get(userId) as { id: string } | undefined;
    if (next) {
      db.prepare("UPDATE cvs SET is_active = 1 WHERE id = ?").run(next.id);
    }
  }
  return cv;
}

export function listApplicationsForUser(userId: string): Application[] {
  return getDb()
    .prepare(
      "SELECT * FROM applications WHERE user_id = ? ORDER BY applied_at DESC"
    )
    .all(userId) as Application[];
}

export function countApplicationsForUser(userId: string): number {
  return (
    getDb()
      .prepare("SELECT COUNT(*) as c FROM applications WHERE user_id = ?")
      .get(userId) as { c: number }
  ).c;
}

export function logActivity(input: {
  userId?: string | null;
  event: string;
  metadata?: Record<string, unknown>;
}) {
  const id = randomUUID();
  getDb()
    .prepare(
      `INSERT INTO activity_logs (id, user_id, event, metadata, created_at)
       VALUES (?, ?, ?, ?, ?)`
    )
    .run(
      id,
      input.userId ?? null,
      input.event,
      input.metadata ? JSON.stringify(input.metadata) : null,
      new Date().toISOString()
    );
}

export function listActivityLogs(limit = 200): ActivityLog[] {
  return getDb()
    .prepare("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT ?")
    .all(limit) as ActivityLog[];
}

export function recordTokenUsage(input: {
  userId?: string | null;
  tokensIn: number;
  tokensOut: number;
  model: string;
  action: string;
}) {
  const id = randomUUID();
  getDb()
    .prepare(
      `INSERT INTO token_usage (id, user_id, tokens_in, tokens_out, model, action, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      id,
      input.userId ?? null,
      input.tokensIn,
      input.tokensOut,
      input.model,
      input.action,
      new Date().toISOString()
    );
}

export function listTokenUsage(limit = 500): TokenUsage[] {
  return getDb()
    .prepare("SELECT * FROM token_usage ORDER BY created_at DESC LIMIT ?")
    .all(limit) as TokenUsage[];
}

export function tokenUsageTotals(): {
  totalIn: number;
  totalOut: number;
} {
  const row = getDb()
    .prepare(
      "SELECT COALESCE(SUM(tokens_in),0) as totalIn, COALESCE(SUM(tokens_out),0) as totalOut FROM token_usage"
    )
    .get() as { totalIn: number; totalOut: number };
  return row;
}
