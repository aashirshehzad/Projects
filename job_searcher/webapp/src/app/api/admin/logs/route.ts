import { NextRequest, NextResponse } from "next/server";
import { listActivityLogs } from "@/lib/db";

export async function GET(request: NextRequest) {
  const search = request.nextUrl.searchParams.get("q")?.toLowerCase() ?? "";
  const logs = listActivityLogs(500).filter((log) => {
    if (!search) return true;
    return (
      log.event.toLowerCase().includes(search) ||
      (log.metadata ?? "").toLowerCase().includes(search) ||
      (log.user_id ?? "").toLowerCase().includes(search)
    );
  });
  return NextResponse.json({ logs });
}
