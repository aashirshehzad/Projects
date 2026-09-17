import { NextRequest, NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { createUser, findUserByEmail, logActivity } from "@/lib/db";
import { sendDiscordAlert } from "@/lib/discord";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const email = typeof body?.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body?.password === "string" ? body.password : "";
  const name = typeof body?.name === "string" ? body.name.trim() : "";

  if (!email || !email.includes("@")) {
    return NextResponse.json({ error: "A valid email is required." }, { status: 400 });
  }
  if (password.length < 8) {
    return NextResponse.json(
      { error: "Password must be at least 8 characters." },
      { status: 400 }
    );
  }

  if (findUserByEmail(email)) {
    return NextResponse.json(
      { error: "An account with this email already exists." },
      { status: 409 }
    );
  }

  const passwordHash = await bcrypt.hash(password, 10);
  const user = createUser({
    email,
    name: name || null,
    passwordHash,
  });

  logActivity({
    userId: user.id,
    event: "user_registered",
    metadata: { method: "credentials" },
  });
  await sendDiscordAlert("user_registered", {
    email: user.email,
    method: "email/password",
  });

  return NextResponse.json({ ok: true });
}
