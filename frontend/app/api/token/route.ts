import { AccessToken } from "livekit-server-sdk";
import { NextResponse } from "next/server";

// Mint a LiveKit join token for the patient (browser) participant.
// Server-side route: reads LIVEKIT_* from env (never exposed to the client).
export const runtime = "nodejs";

export async function POST() {
  const { LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL } = process.env;
  if (!LIVEKIT_API_KEY || !LIVEKIT_API_SECRET || !LIVEKIT_URL) {
    return NextResponse.json(
      { error: "LiveKit credentials not configured" },
      { status: 500 },
    );
  }

  const room = `veralix-${crypto.randomUUID().slice(0, 8)}`;
  const identity = `patient-${crypto.randomUUID().slice(0, 6)}`;

  const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
    identity,
    name: "Patient",
  });
  at.addGrant({ roomJoin: true, room });

  const token = await at.toJwt();
  return NextResponse.json({ token, url: LIVEKIT_URL, room, identity });
}
