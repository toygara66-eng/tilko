import re
from math import ceil
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi


YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(video_url: str) -> str:
    parsed = urlparse(video_url)
    host = (parsed.hostname or "").lower().replace("www.", "")

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/") or parsed.path.startswith("/shorts/"):
            candidate = parsed.path.strip("/").split("/")[1]
        else:
            candidate = ""
    else:
        candidate = ""

    if not YOUTUBE_ID_RE.match(candidate):
        raise ValueError("Geçerli bir YouTube video kimliği bulunamadı.")
    return candidate


def format_timestamp_label(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def build_watch_url(video_id: str, seconds: int | None = None) -> str:
    base = f"https://www.youtube.com/watch?v={video_id}"
    if seconds is None:
        return base
    return f"{base}&t={int(seconds)}s"


PREFERRED_LANGUAGES = ["tr", "tr-TR", "en"]


def _snippet_field(snippet, name: str, default):
    if isinstance(snippet, dict):
        return snippet.get(name, default)
    value = getattr(snippet, name, default)
    return default if value is None else value


def fetch_transcript_lines(video_id: str) -> list[dict]:
    """Altyazıyı saniye damgasıyla çeker (TR tercih, yoksa mevcut ilk dil)."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_fetch_transcript_lines_inner, video_id)
        try:
            return future.result(timeout=25)
        except FuturesTimeout as exc:
            raise ValueError(
                "YouTube altyazısı gecikti. Linki kontrol edip tekrar dene."
            ) from exc


def _fetch_transcript_lines_inner(video_id: str) -> list[dict]:
    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(video_id, languages=PREFERRED_LANGUAGES)
    except Exception:
        available = list(api.list(video_id))
        if not available:
            raise ValueError("Bu video için altyazı bulunamadı.")
        transcript = available[0].fetch()

    lines: list[dict] = []
    for snippet in transcript:
        start = int(float(_snippet_field(snippet, "start", 0)))
        text = str(_snippet_field(snippet, "text", "")).replace("\n", " ").strip()
        lines.append({"start": start, "text": text})
    return lines


def transcript_as_prompt_block(lines: list[dict]) -> str:
    return "\n".join(f"[{item['start']}] {item['text']}" for item in lines if item["text"])


def chunk_transcript(lines: list[dict], max_chars: int = 24000) -> list[str]:
    """Uzun altyazıyı parçalara böler.

    Parça sınırı bilinçli olarak büyük: her parça bir LLM isteği demek ve ücretsiz
    kotalar istek sayısına göre sayılıyor. Modelin bağlamı bu boyutu rahat kaldırıyor.
    """
    chunks: list[str] = []
    current: list[dict] = []
    size = 0
    for item in lines:
        if not item["text"]:
            continue
        entry_size = len(item["text"]) + 12
        if current and size + entry_size > max_chars:
            chunks.append(transcript_as_prompt_block(current))
            current = []
            size = 0
        current.append(item)
        size += entry_size
    if current:
        chunks.append(transcript_as_prompt_block(current))
    return chunks


def slice_transcript(lines: list[dict], window_seconds: int = 300) -> list[dict]:
    """Altyazıyı 5 dakikalık dilimlere böler: [{start, end, label, block}]."""
    usable = [item for item in lines if item.get("text")]
    if not usable:
        return []
    end_at = max(int(item.get("start") or 0) for item in usable) + 1
    slices: list[dict] = []
    start = 0
    while start < end_at:
        stop = start + window_seconds
        piece = [
            item
            for item in usable
            if start <= int(item.get("start") or 0) < stop
        ]
        if piece:
            last = int(piece[-1].get("start") or start)
            slices.append(
                {
                    "start": start,
                    "end": last,
                    "label": f"{format_timestamp_label(start)}–{format_timestamp_label(min(stop, last + 1))}",
                    "block": transcript_as_prompt_block(piece),
                }
            )
        start = stop
    return slices


def compact_transcript(lines: list[dict], max_chars: int = 28000) -> str:
    """Tüm videoyu kapsa: sığmazsa satır atlayarak baş-orta-sonu koru."""
    usable = [item for item in lines if item.get("text")]
    if not usable:
        return ""
    full = transcript_as_prompt_block(usable)
    if len(full) <= max_chars:
        return full
    step = max(1, ceil(len(full) / max_chars))
    sampled = usable[::step]
    if sampled[-1] is not usable[-1]:
        sampled.append(usable[-1])
    out = transcript_as_prompt_block(sampled)
    while len(out) > max_chars and step < len(usable):
        step += 1
        sampled = usable[::step]
        if sampled[-1] is not usable[-1]:
            sampled.append(usable[-1])
        out = transcript_as_prompt_block(sampled)
    return out


def transcript_duration_seconds(lines: list[dict]) -> int:
    if not lines:
        return 0
    return max(int(item.get("start") or 0) for item in lines)
