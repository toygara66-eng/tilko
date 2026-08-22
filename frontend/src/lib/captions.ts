export type CaptionLine = { start: number; text: string };

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;

function captionsEndpoint(): string {
  if (typeof window === "undefined") return "https://tilko.site/api/captions";
  const host = window.location.hostname;
  if (host === "tilko.site" || host.endsWith(".vercel.app")) {
    return "/api/captions";
  }
  return "https://tilko.site/api/captions";
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

export async function fetchCaptionsForVideo(
  videoUrl: string,
): Promise<CaptionLine[]> {
  const id = extractYoutubeId(videoUrl);
  if (!id) return [];
  const endpoint = `${captionsEndpoint()}?v=${encodeURIComponent(id)}`;
  try {
    const response = await fetch(endpoint, {
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) return [];
    const data = (await response.json()) as { lines?: CaptionLine[] };
    const lines = Array.isArray(data.lines) ? data.lines : [];
    return lines.filter(
      (row) =>
        row &&
        typeof row.text === "string" &&
        row.text.trim() &&
        Number.isFinite(Number(row.start)),
    );
  } catch {
    return [];
  }
}
