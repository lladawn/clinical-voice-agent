"use client";

import { useEffect, useState } from "react";
import { useRoomContext } from "@livekit/components-react";
import { RoomEvent, TranscriptionSegment, Participant } from "livekit-client";

type Line = {
  id: string;
  text: string;
  final: boolean;
  fromAgent: boolean;
};

/**
 * Live transcript. Listens to LiveKit TranscriptionReceived events and renders
 * interim results in grey, finals in black. Agent (Aria) turns are visually
 * distinguished from the patient's.
 */
export default function TranscriptPanel() {
  const room = useRoomContext();
  const [lines, setLines] = useState<Record<string, Line>>({});

  useEffect(() => {
    const handler = (
      segments: TranscriptionSegment[],
      participant?: Participant,
    ) => {
      const fromAgent = participant?.isAgent ?? false;
      setLines((prev) => {
        const next = { ...prev };
        for (const seg of segments) {
          next[seg.id] = {
            id: seg.id,
            text: seg.text,
            final: seg.final,
            fromAgent,
          };
        }
        return next;
      });
    };

    room.on(RoomEvent.TranscriptionReceived, handler);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, handler);
    };
  }, [room]);

  const ordered = Object.values(lines);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Live Transcript
      </h2>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-lg border border-slate-200 bg-white p-4">
        {ordered.length === 0 && (
          <p className="text-sm text-slate-400">
            Connect and start speaking — transcript will appear here.
          </p>
        )}
        {ordered.map((line) => (
          <div key={line.id} className="text-sm leading-relaxed">
            <span
              className={
                line.fromAgent
                  ? "font-semibold text-emerald-700"
                  : "font-semibold text-slate-700"
              }
            >
              {line.fromAgent ? "Aria" : "Patient"}:{" "}
            </span>
            <span className={line.final ? "text-slate-900" : "text-slate-400"}>
              {line.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
