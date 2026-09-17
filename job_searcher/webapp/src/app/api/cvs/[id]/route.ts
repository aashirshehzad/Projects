import { NextRequest, NextResponse } from "next/server";
import path from "node:path";
import fs from "node:fs/promises";
import { auth } from "@/lib/auth";
import { deleteCv } from "@/lib/db";

const UPLOADS_DIR = path.join(process.cwd(), "uploads");

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const cv = deleteCv(session.user.id, id);
  if (!cv) {
    return NextResponse.json({ error: "CV not found." }, { status: 404 });
  }

  await fs.unlink(path.join(UPLOADS_DIR, cv.file_path)).catch(() => {});

  return NextResponse.json({ ok: true });
}
