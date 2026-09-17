import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { listCvsForUser } from "@/lib/db";

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  return NextResponse.json({ cvs: listCvsForUser(session.user.id) });
}
