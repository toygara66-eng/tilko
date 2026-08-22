export type CaptionLine = { start: number; text: string };

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "https://tilko-api.onrender.com";
const PLAYER =
  "https://www.youtube.com/youtubei/v1/player?prettyPrint=false";
const IOS_UA =
  "com.google.ios.youtube/20.10.38 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)";
const RELAYS = ["https://inv.nadeko.net", "https://yt.chocolatemoo53.com"];
const STAMP_LINE = /^(?:\[)?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\])?(?:\s+(.+))?$/;
const CLOCK_BRACKET = /^\[(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\]\s*(.+)$/;
const BRACKET_STAMP = /^\[(\d+)\]\s*(.+)$/;
const TRANSCRIPT_AI = "https://youtube-transcript.ai/transcript";

function captionProxyUrls(id: string): string[] {
  const urls = [`${API_BASE.replace(/\/$/, "")}/captions/${encodeURIComponent(id)}`];
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "tilko.site" || host.endsWith(".vercel.app")) {
      urls.push(`/api/captions/?v=${encodeURIComponent(id)}`);
    }
  }
  return urls;
}

export function extractYoutubeId(raw: string): string {
  const value = (raw || "").trim();
  if (VIDEO_ID_RE.test(value)) return value;
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^www\./, "").toLowerCase();
    if (host === "youtu.be") {
      const id = url.pathname.replace(/^\//, "").split("/")[0] || "";
      return VIDEO_ID_RE.test(id) ? id : "";
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

function cleanText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function stampToSeconds(hour: string | undefined, minute: string, second: string): number {
  return Number(hour || 0) * 3600 + Number(minute) * 60 + Number(second);
}

function usable(lines: CaptionLine[]): CaptionLine[] {
  return lines.filter(
    (row) =>
      row &&
      typeof row.text === "string" &&
      row.text.trim() &&
      Number.isFinite(Number(row.start)),
  );
}

function parseJsonLines(data: unknown): CaptionLine[] {
  const rows =
    data && typeof data === "object" ? (data as { lines?: CaptionLine[] }).lines : [];
  if (!Array.isArray(rows)) return [];
  return usable(rows);
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
    const text = cleanText(
      segs
        .map((seg) =>
          seg && typeof seg === "object"
            ? String((seg as { utf8?: string }).utf8 || "")
            : "",
        )
        .join(" "),
    );
    if (!text) continue;
    lines.push({ start: Math.floor(Number(row.tStartMs || 0) / 1000), text });
  }
  return lines;
}

function linesFromVtt(raw: string): CaptionLine[] {
  const lines: CaptionLine[] = [];
  const blocks = raw.replace(/\r\n/g, "\n").split(/\n\s*\n/);
  for (const block of blocks) {
    const rows = block
      .split("\n")
      .map((row) => row.trim())
      .filter(
        (row) =>
          row &&
          !row.startsWith("WEBVTT") &&
          !row.startsWith("NOTE") &&
          !row.startsWith("Kind:") &&
          !row.startsWith("Language:"),
      );
    let stamp: number | null = null;
    const body: string[] = [];
    for (const row of rows) {
      const match = row.match(
        /(?:(\d+):)?(\d{2}):(\d{2})[\.,]\d{3}\s*-->/,
      );
      if (match) {
        stamp = stampToSeconds(match[1], match[2], match[3]);
        continue;
      }
      if (/^\d+$/.test(row)) continue;
      const cleaned = cleanText(row.replace(/<[^>]+>/g, ""));
      if (cleaned) body.push(cleaned);
    }
    if (stamp == null || !body.length) continue;
    lines.push({ start: stamp, text: body.join(" ") });
  }
  return lines;
}

function linesFromClockBrackets(raw: string): CaptionLine[] {
  const lines: CaptionLine[] = [];
  for (const row of raw.split("\n")) {
    const match = row.trim().match(CLOCK_BRACKET);
    if (!match) continue;
    const text = cleanText(match[4] || "");
    if (!text) continue;
    lines.push({
      start: stampToSeconds(match[1], match[2], match[3]),
      text,
    });
  }
  return lines;
}

async function fetchViaTranscriptAi(id: string): Promise<CaptionLine[]> {
  for (const lang of ["tr", ""]) {
    const url = `${TRANSCRIPT_AI}/${id}.txt${lang ? `?lang=${lang}` : ""}`;
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(12_000) });
      if (!response.ok) continue;
      const parsed = linesFromClockBrackets(await response.text());
      if (parsed.length >= 3) return parsed;
    } catch {
      /* sonraki dil / kaynak */
    }
  }
  return [];
}

/** YouTube "Transkripti göster" kopyası, SRT veya [saniye] satırları. */
export function parseTranscriptPaste(raw: string): CaptionLine[] {
  const text = (raw || "").replace(/\r\n/g, "\n").trim();
  if (!text) return [];

  const clock = linesFromClockBrackets(text);
  if (clock.length >= 3) return clock;

  const bracket: CaptionLine[] = [];
  for (const row of text.split("\n")) {
    const match = row.trim().match(BRACKET_STAMP);
    if (!match) continue;
    bracket.push({ start: Number(match[1]), text: cleanText(match[2]) });
  }
  if (bracket.length >= 3) return bracket;

  const stamped: CaptionLine[] = [];
  const rows = text.split("\n").map((row) => row.trim());
  let pending: number | null = null;
  for (const row of rows) {
    if (!row || /^WEBVTT/i.test(row) || /^\d+$/.test(row)) continue;
    const arrow = row.match(/^(?:(\d{1,2}):)?(\d{2}):(\d{2})[\.,]\d{3}\s*-->/);
    if (arrow) {
      pending = stampToSeconds(arrow[1], arrow[2], arrow[3]);
      continue;
    }
    const match = row.match(STAMP_LINE);
    if (match && (match[1] != null || Number(match[2]) < 60)) {
      const seconds = stampToSeconds(match[1], match[2], match[3]);
      const rest = cleanText(match[4] || "");
      if (rest) {
        stamped.push({ start: seconds, text: rest });
        pending = null;
      } else {
        pending = seconds;
      }
      continue;
    }
    if (pending != null) {
      stamped.push({ start: pending, text: cleanText(row) });
      pending = null;
    }
  }
  if (stamped.length >= 3) return stamped;

  const vtt = linesFromVtt(text);
  if (vtt.length >= 3) return vtt;

  const chunks = text
    .split(/\n\s*\n/)
    .map((chunk) => cleanText(chunk))
    .filter(Boolean);
  if (chunks.length >= 3) {
    return chunks.map((chunk, index) => ({ start: index * 12, text: chunk }));
  }
  return [];
}

async function fetchViaInnertube(id: string): Promise<CaptionLine[]> {
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
      videoId: id,
      contentCheckOk: true,
      racyCheckOk: true,
    }),
    signal: AbortSignal.timeout(12_000),
  });
  if (!player.ok) return [];
  const data = (await player.json()) as {
    captions?: {
      playerCaptionsTracklistRenderer?: {
        captionTracks?: { baseUrl?: string; languageCode?: string }[];
      };
    };
  };
  const tracks = data.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  const track =
    tracks.find((item) => (item.languageCode || "").toLowerCase().startsWith("tr")) ||
    tracks[0];
  const base = track?.baseUrl;
  if (!base) return [];
  const captionUrl = base.includes("fmt=")
    ? base
    : `${base}${base.includes("?") ? "&" : "?"}fmt=json3`;
  const caption = await fetch(captionUrl, {
    headers: { "User-Agent": IOS_UA, "Accept-Language": "tr-TR,tr;q=0.9" },
    signal: AbortSignal.timeout(12_000),
  });
  if (!caption.ok) return [];
  const body = await caption.json();
  return linesFromJson3(body);
}

async function fetchViaRelay(id: string): Promise<CaptionLine[]> {
  for (const host of RELAYS) {
    try {
      const listing = await fetch(`${host}/api/v1/captions/${id}`, {
        signal: AbortSignal.timeout(8_000),
      });
      if (!listing.ok) continue;
      const payload = (await listing.json()) as {
        captions?: { label?: string; languageCode?: string; url?: string }[];
      };
      const captions = payload.captions || [];
      const pick =
        captions.find((item) =>
          (item.languageCode || "").toLowerCase().startsWith("tr"),
        ) ||
        captions.find((item) =>
          (item.languageCode || "").toLowerCase().startsWith("en"),
        ) ||
        captions[0];
      const path = pick?.url;
      if (!path) continue;
      const captionUrl = path.startsWith("http") ? path : `${host}${path}`;
      const caption = await fetch(captionUrl, {
        headers: { Accept: "text/vtt, application/json, text/plain, */*" },
        signal: AbortSignal.timeout(8_000),
      });
      if (!caption.ok) continue;
      const raw = await caption.text();
      if (!raw.trim()) continue;
      const parsed = raw.trim().startsWith("{")
        ? linesFromJson3(JSON.parse(raw))
        : linesFromVtt(raw);
      if (parsed.length >= 3) return parsed;
    } catch {
      /* sonraki köprü */
    }
  }
  return [];
}

export async function fetchCaptionsForVideo(
  videoUrl: string,
): Promise<CaptionLine[]> {
  const id = extractYoutubeId(videoUrl);
  if (!id) return [];

  try {
    const hosted = await fetchViaTranscriptAi(id);
    if (hosted.length >= 3) return hosted;
  } catch {
    /* CORS veya kota; sonraki kaynak */
  }

  try {
    const direct = await fetchViaInnertube(id);
    if (direct.length >= 3) return direct;
  } catch {
    /* tarayıcı CORS; Android native HTTP geçer */
  }

  const relay = await fetchViaRelay(id);
  if (relay.length >= 3) return relay;

  for (const endpoint of captionProxyUrls(id)) {
    try {
      const response = await fetch(endpoint, {
        signal: AbortSignal.timeout(20_000),
      });
      if (!response.ok) continue;
      const lines = parseJsonLines(await response.json());
      if (lines.length >= 3) return lines;
    } catch {
      /* sonraki kaynak */
    }
  }
  return [];
}
