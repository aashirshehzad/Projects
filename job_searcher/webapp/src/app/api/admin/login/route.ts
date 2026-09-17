import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifyAdminCredentials, createAdminSessionToken } from "@/lib/admin-auth";
import { ADMIN_COOKIE_NAME } from "@/lib/admin-constants";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const username = typeof body?.username === "string" ? body.username : "";
  const password = typeof body?.password === "string" ? body.password : "";

  const valid = await verifyAdminCredentials(username, password);
  if (!valid) {
    return NextResponse.json({ error: "Invalid credentials." }, { status: 401 });
  }

  const token = await createAdminSessionToken();
  const cookieStore = await cookies();
  cookieStore.set(ADMIN_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 8 * 60 * 60,
  });

  return NextResponse.json({ ok: true });
}
