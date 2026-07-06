"use client";

import { useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
} from "@livekit/components-react";
import TranscriptPanel from "@/components/TranscriptPanel";
import AuditLogPanel from "@/components/AuditLogPanel";

type Conn = { token: string; url: string; room: string };

export default function Home() {
  const [conn, setConn] = useState<Conn | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async () => {
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch(`/api/token`, { method: "POST" });
      if (!res.ok) throw new Error(`token request failed (${res.status})`);
      const data = await res.json();
      setConn({ token: data.token, url: data.url, room: data.room });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to connect");
    } finally {
      setConnecting(false);
    }
  };

  return (
    <main className="mx-auto flex h-screen max-w-6xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Aria — Veralix Patient Support
          </h1>
          <p className="text-sm text-slate-500">
            Clinical voice agent · compliance guardrails · audit logging
          </p>
        </div>
        {!conn ? (
          <button
            onClick={connect}
            disabled={connecting}
            className="rounded-lg bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {connecting ? "Connecting…" : "Start call"}
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-emerald-100 px-3 py-2 text-sm font-medium text-emerald-800">
              Connected · {conn.room}
            </span>
            <button
              onClick={() => setConn(null)}
              className="rounded-lg bg-red-600 px-4 py-2 font-semibold text-white hover:bg-red-700"
            >
              End call
            </button>
          </div>
        )}
      </header>

      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {conn ? (
        <LiveKitRoom
          token={conn.token}
          serverUrl={conn.url}
          connect
          audio
          video={false}
          className="grid min-h-0 flex-1 grid-cols-2 grid-rows-1 gap-4 overflow-hidden"
        >
          <RoomAudioRenderer />
          <StartAudio label="Click to enable audio" />
          <TranscriptPanel />
          <AuditLogPanel sessionId={conn.room} />
        </LiveKitRoom>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-2 grid-rows-1 gap-4 overflow-hidden opacity-60">
          <TranscriptShell />
          <AuditLogPanel />
        </div>
      )}
    </main>
  );
}

/** Placeholder shown before connecting (TranscriptPanel needs a room context). */
function TranscriptShell() {
  return (
    <div className="flex h-full flex-col">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Live Transcript
      </h2>
      <div className="flex-1 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-400">
        Click “Start call” to connect.
      </div>
    </div>
  );
}
