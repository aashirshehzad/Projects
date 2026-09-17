import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { auth } from "@/lib/auth";
import { getDb } from "@/lib/schema";
import { listApplicationsForUser, logActivity } from "@/lib/db";
import { sendDiscordAlert } from "@/lib/discord";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return NextResponse.json({
    applications: listApplicationsForUser(session.user.id),
  });
}

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  const jobTitle = typeof body?.jobTitle === "string" ? body.jobTitle.trim() : "";
  const company = typeof body?.company === "string" ? body.company.trim() : "";
  const status =
    typeof body?.status === "string" && ["pending", "applied", "rejected"].includes(body.status)
      ? body.status
      : "pending";

  if (!jobTitle || !company) {
    return NextResponse.json(
      { error: "Job title and company are required." },
      { status: 400 }
    );
  }

  const id = randomUUID();
  const appliedAt = new Date().toISOString();
  getDb()
    .prepare(
      `INSERT INTO applications (id, user_id, job_title, company, status, applied_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .run(id, session.user.id, jobTitle, company, status, appliedAt);

  logActivity({
    userId: session.user.id,
    event: "application_submitted",
    metadata: { jobTitle, company },
  });
  await sendDiscordAlert("application_submitted", {
    user: session.user.email ?? session.user.id,
    job: `${jobTitle} at ${company}`,
  });

  return NextResponse.json({ ok: true });
}
