export type CaptionLine = { start: number; text: string };

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "https://tilko-api.onrender.com";

function captionUrls(id: string): string[] {
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

function parseLines(data: unknown): CaptionLine[] {
  const rows = data && typeof data === "object" ? (data as { lines?: CaptionLine[] }).lines : [];
  if (!Array.isArray(rows)) return [];
  return rows.filter(
    (row) =>
      row &&
      typeof row.text === "string" &&
      row.text.trim() &&
      Number.isFinite(Number(row.start)),
  );
}

export async function fetchCaptionsForVideo(
  videoUrl: string,
): Promise<CaptionLine[]> {
  const id = extractYoutubeId(videoUrl);
  if (!id) return [];
  for (const endpoint of captionUrls(id)) {
    try {
      const response = await fetch(endpoint, {
        signal: AbortSignal.timeout(35_000),
      });
      if (!response.ok) continue;
      const lines = parseLines(await response.json());
      if (lines.length >= 3) return lines;
    } catch {
      /* sonraki kaynak */
    }
  }
  return [];
}
