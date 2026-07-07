import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

// Serve audit records for the right-hand panel. Server-side route: reads Supabase
// with the service key (never exposed to the client).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store"; // never cache the audit query

export async function GET(req: Request) {
  const { SUPABASE_URL, SUPABASE_SERVICE_KEY } = process.env;
  if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
    return NextResponse.json({ records: [], source: "unconfigured" });
  }

  const sessionId = new URL(req.url).searchParams.get("session_id");
  // Force the underlying fetch to bypass Next's App Router fetch cache — otherwise
  // the audit feed serves a stale snapshot and never updates.
  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, {
    global: {
      fetch: (input, init) => fetch(input, { ...init, cache: "no-store" }),
    },
  });

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
