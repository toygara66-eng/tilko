import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const PLAYER =
  "https://www.youtube.com/youtubei/v1/player?key=AIzaSyB-63vPrdThhKuerbB2N_l7Kwwcxj6yUAc&prettyPrint=false";
const IOS_UA =
  "com.google.ios.youtube/20.10.38 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)";

type CaptionLine = { start: number; text: string };

function cors(res: NextResponse) {
  res.headers.set("Access-Control-Allow-Origin", "*");
  res.headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.headers.set("Access-Control-Allow-Headers", "Content-Type");
  return res;
}

export function OPTIONS() {
  return cors(new NextResponse(null, { status: 204 }));
}

function extractVideoId(raw: string): string {
  const value = (raw || "").trim();
  if (VIDEO_ID_RE.test(value)) return value;
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^www\./, "").toLowerCase();
    if (host === "youtu.be") {
      const id = url.pathname.replace(/^\//, "").split("/")[0] || "";
      if (VIDEO_ID_RE.test(id)) return id;
    }
    if (host.endsWith("youtube.com")) {
      const v = url.searchParams.get("v") || "";
      if (VIDEO_ID_RE.test(v)) return v;
      const parts = url.pathname.split("/").filter(Boolean);
      if (
        (parts[0] === "embed" || parts[0] === "shorts") &&
        VIDEO_ID_RE.test(parts[1] || "")
      ) {
        return parts[1];
      }
    }
  } catch {
    /* ignore */
  }
  return "";
}

function pickTrack(tracks: unknown): { baseUrl?: string; languageCode?: string } | null {
  if (!Array.isArray(tracks) || tracks.length === 0) return null;
  const rows = tracks.filter((item) => item && typeof item === "object") as {
    baseUrl?: string;
    languageCode?: string;
  }[];
  return (
    rows.find((track) => (track.languageCode || "").toLowerCase().startsWith("tr")) ||
    rows[0] ||
    null
  );
}

function linesFromJson3(payload: unknown): CaptionLine[] {
  if (!payload || typeof payload !== "object") return [];
  const events = (payload as { events?: unknown }).events;
  if (!Array.isArray(events)) return [];
  const lines: CaptionLine[] = [];
  for (const event of events) {
    if (!event || typeof event !== "object") continue;
    const row = event as { tStartMs?: number; segs?: unknown };
    const segs = Array.isArray(row.segs) ? row.segs : [];
    const text = segs
      .map((seg) =>
        seg && typeof seg === "object"
          ? String((seg as { utf8?: string }).utf8 || "")
          : "",
      )
      .join(" ")
      .replace(/\n/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) continue;
    lines.push({ start: Math.floor(Number(row.tStartMs || 0) / 1000), text });
  }
  return lines;
}

async function fetchViaIos(videoId: string): Promise<CaptionLine[]> {
  const player = await fetch(PLAYER, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": IOS_UA,
      "X-YouTube-Client-Name": "5",
      "X-YouTube-Client-Version": "20.10.38",
      "Accept-Language": "tr-TR,tr;q=0.9",
    },
    body: JSON.stringify({
      context: {
        client: {
          clientName: "IOS",
          clientVersion: "20.10.38",
          deviceMake: "Apple",
          deviceModel: "iPhone16,2",
          osName: "iOS",
          osVersion: "17.5.1.21F90",
          hl: "tr",
          gl: "TR",
        },
      },
      videoId,
      contentCheckOk: true,
      racyCheckOk: true,
    }),
  });
  if (!player.ok) {
    throw new Error(`player ${player.status}`);
  }
  const data = (await player.json()) as {
    captions?: {
      playerCaptionsTracklistRenderer?: { captionTracks?: unknown };
    };
  };
  const track = pickTrack(
    data.captions?.playerCaptionsTracklistRenderer?.captionTracks,
  );
  const base = track?.baseUrl;
  if (!base) throw new Error("track yok");
  const captionUrl = base.includes("fmt=")
    ? base
    : `${base}${base.includes("?") ? "&" : "?"}fmt=json3`;
  const caption = await fetch(captionUrl, {
    headers: {
      "User-Agent": IOS_UA,
      "Accept-Language": "tr-TR,tr;q=0.9",
    },
  });
  if (!caption.ok) throw new Error(`timedtext ${caption.status}`);
  const body = await caption.json();
  const lines = linesFromJson3(body);
  if (!lines.length) throw new Error("altyazı boş");
  return lines;
}

export async function GET(request: NextRequest) {
  const videoId = extractVideoId(
    request.nextUrl.searchParams.get("v") ||
      request.nextUrl.searchParams.get("url") ||
      "",
  );
  if (!videoId) {
    return cors(
      NextResponse.json({ error: "Geçerli YouTube bağlantısı gerekli." }, { status: 400 }),
    );
  }
  try {
    const lines = await fetchViaIos(videoId);
    return cors(NextResponse.json({ video_id: videoId, lines }));
  } catch (err) {
    const message = err instanceof Error ? err.message : "Altyazı alınamadı.";
    return cors(
      NextResponse.json(
        { error: "YouTube altyazısı alınamadı.", detail: message },
        { status: 502 },
      ),
    );
  }
}
