import path from "node:path";
import fs from "node:fs";
import Database from "better-sqlite3";

const DATA_DIR = path.join(process.cwd(), "data");
const DB_PATH = path.join(DATA_DIR, "easypezee.db");

if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const UPLOADS_DIR = path.join(process.cwd(), "uploads");
if (!fs.existsSync(UPLOADS_DIR)) {
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

declare global {
  var __easypezeeDb: Database.Database | undefined;
}

function createConnection(): Database.Database {
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");

  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      name TEXT,
      password_hash TEXT,
      google_id TEXT,
      linkedin_url TEXT,
      avatar_url TEXT,
      created_at TEXT NOT NULL,
      onboarded INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS cvs (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      filename TEXT NOT NULL,
      file_path TEXT NOT NULL,
      uploaded_at TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS applications (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_title TEXT NOT NULL,
      company TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      applied_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS token_usage (
      id TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
      tokens_in INTEGER NOT NULL DEFAULT 0,
      tokens_out INTEGER NOT NULL DEFAULT 0,
      model TEXT NOT NULL,
      action TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
      id TEXT PRIMARY KEY,
      user_id TEXT,
      event TEXT NOT NULL,
      metadata TEXT,
      created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_cvs_user ON cvs(user_id);
    CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id);
    CREATE INDEX IF NOT EXISTS idx_token_usage_user ON token_usage(user_id);
    CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON activity_logs(user_id);
  `);

  return db;
}

export function getDb(): Database.Database {
  if (!global.__easypezeeDb) {
    global.__easypezeeDb = createConnection();
  }
  return global.__easypezeeDb;
}
