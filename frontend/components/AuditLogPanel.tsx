"use client";

import { useEffect, useState } from "react";

type AuditRecord = {
  turn_id: string;
  timestamp: string;
  patient_utterance: string;
  guardrail_result: string;
  pi_sections_used: string[];
  agent_response: string;
  compliance_tag: string;
  latency_ms: number;
};

const TAG_STYLES: Record<string, string> = {
  ON_LABEL: "bg-emerald-100 text-emerald-800",
  OUT_OF_SCOPE: "bg-amber-100 text-amber-800",
  OFF_LABEL_REFUSED: "bg-amber-100 text-amber-800",
  EMERGENCY_ESCALATED: "bg-red-100 text-red-800",
};

/**
 * Audit log feed. Polls the backend /audit-log endpoint every 2s and renders
 * each turn as a card with a colour-coded compliance badge — the view an MLR
 * reviewer would audit.
 */
export default function AuditLogPanel({ sessionId }: { sessionId?: string }) {
  const [records, setRecords] = useState<AuditRecord[]>([]);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const q = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
        const res = await fetch(`/api/audit-log${q}`);
        const data = await res.json();
        if (active) setRecords(data.records ?? []);
      } catch {
        // backend not up yet — keep polling
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sessionId]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Audit Log
      </h2>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-lg border border-slate-200 bg-white p-4">
        {records.length === 0 && (
          <p className="text-sm text-slate-400">
            Structured audit records appear here as each turn completes.
          </p>
        )}
        {records.map((r) => (
          <div
            key={r.turn_id}
            className="rounded-md border border-slate-100 bg-slate-50 p-3 text-sm"
          >
            <div className="mb-2 flex items-center justify-between">
              <span
                className={`rounded px-2 py-0.5 text-xs font-semibold ${
                  TAG_STYLES[r.compliance_tag] ?? "bg-slate-200 text-slate-700"
                }`}
              >
                {r.compliance_tag}
              </span>
              <span className="text-xs text-slate-400">{r.latency_ms} ms</span>
            </div>
            <p className="text-slate-700">
              <span className="font-medium">Patient:</span> {r.patient_utterance}
            </p>
            <p className="mt-1 text-slate-700">
              <span className="font-medium">Aria:</span> {r.agent_response}
            </p>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
              <span>guardrail: {r.guardrail_result}</span>
              {r.pi_sections_used?.length > 0 && (
                <span>· PI: {r.pi_sections_used.join(", ")}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
