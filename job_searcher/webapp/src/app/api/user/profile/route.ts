import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { setUserOnboarding, logActivity } from "@/lib/db";

const LINKEDIN_URL_PATTERN = /^https?:\/\/(www\.)?linkedin\.com\/.+/i;

export async function PATCH(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  const linkedinUrl =
    typeof body?.linkedinUrl === "string" ? body.linkedinUrl.trim() : "";

  if (!LINKEDIN_URL_PATTERN.test(linkedinUrl)) {
    return NextResponse.json(
      { error: "Please enter a valid LinkedIn profile URL." },
      { status: 400 }
    );
  }

  setUserOnboarding(session.user.id, { linkedinUrl, onboarded: true });
  logActivity({
    userId: session.user.id,
    event: "user_onboarded",
    metadata: { linkedinUrl },
  });

  return NextResponse.json({ ok: true });
}
