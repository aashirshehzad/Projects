import { NextRequest, NextResponse } from "next/server";
import { jwtVerify } from "jose";
import { ADMIN_COOKIE_NAME } from "@/lib/admin-constants";

export const config = {
  matcher: ["/admin/:path*", "/api/admin/:path*"],
};

async function hasValidAdminSession(request: NextRequest): Promise<boolean> {
  const token = request.cookies.get(ADMIN_COOKIE_NAME)?.value;
  if (!token) return false;
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) return false;
  try {
    const { payload } = await jwtVerify(
      token,
      new TextEncoder().encode(secret)
    );
    return payload.role === "admin";
  } catch {
    return false;
  }
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname === "/admin" || pathname === "/api/admin/login") {
    return NextResponse.next();
  }

  const authorized = await hasValidAdminSession(request);
  if (!authorized) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.redirect(new URL("/admin", request.url));
  }

  return NextResponse.next();
}
