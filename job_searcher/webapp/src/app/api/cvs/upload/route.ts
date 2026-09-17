import { NextRequest, NextResponse } from "next/server";
import path from "node:path";
import fs from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { auth } from "@/lib/auth";
import { createCv, logActivity } from "@/lib/db";
import { sendDiscordAlert } from "@/lib/discord";

const MAX_SIZE_BYTES = 5 * 1024 * 1024;
const UPLOADS_DIR = path.join(process.cwd(), "uploads");

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const formData = await request.formData().catch(() => null);
  const file = formData?.get("file");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file provided." }, { status: 400 });
  }

  if (file.type !== "application/pdf") {
    return NextResponse.json(
      { error: "Only PDF files are supported." },
      { status: 400 }
    );
  }

  if (file.size > MAX_SIZE_BYTES) {
    return NextResponse.json(
      { error: "File exceeds the 5MB limit." },
      { status: 400 }
    );
  }

  const userDir = path.join(UPLOADS_DIR, session.user.id);
  await fs.mkdir(userDir, { recursive: true });

  const storedName = `${randomUUID()}.pdf`;
  const storedPath = path.join(userDir, storedName);
  const buffer = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(storedPath, buffer);

  const cv = createCv({
    userId: session.user.id,
    filename: file.name,
    filePath: path.join(session.user.id, storedName),
  });

  logActivity({
    userId: session.user.id,
    event: "cv_uploaded",
    metadata: { filename: file.name },
  });
  await sendDiscordAlert("cv_uploaded", {
    user: session.user.email ?? session.user.id,
    filename: file.name,
  });

  return NextResponse.json({ cv });
}
