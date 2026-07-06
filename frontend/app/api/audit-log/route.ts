import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

// Serve audit records for the right-hand panel. Server-side route: reads Supabase
// with the service key (never exposed to the client).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const { SUPABASE_URL, SUPABASE_SERVICE_KEY } = process.env;
  if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
    return NextResponse.json({ records: [], source: "unconfigured" });
  }

  const sessionId = new URL(req.url).searchParams.get("session_id");
  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

  let query = supabase
    .from("audit_log")
    .select("*")
    .order("timestamp", { ascending: false })
    .limit(50);
  if (sessionId) query = query.eq("session_id", sessionId);

  const { data, error } = await query;
  if (error) {
    // Most common cause: the audit_log table hasn't been created yet.
    if (error.code === "PGRST205") {
      return NextResponse.json({
        records: [],
        source: "table_missing",
        hint: "Run data/schema.sql (or `make db`) to create the audit_log table.",
      });
    }
    return NextResponse.json({ records: [], source: "error", error: error.message });
  }

  return NextResponse.json({ records: data ?? [], source: "supabase" });
}
