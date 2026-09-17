import { NextResponse } from "next/server";
import { listUsers } from "@/lib/db";

export async function GET() {
  const users = listUsers().map((user) => ({
    id: user.id,
    email: user.email,
    name: user.name,
    created_at: user.created_at,
    onboarded: user.onboarded,
    auth_method: user.google_id ? "google" : "email",
  }));
  return NextResponse.json({ users });
}
