"""ÖSYM arşivi + hoca vurgusu RAG / self-learning soru motoru."""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    HocaHighlight,
    OsymArchiveChunk,
    OsymArchiveDoc,
    OsymStyleGuide,
    TopicSignal,
)
from app.services.exams import normalize
from app.services.highlights import scan_hoca_highlights, topic_from_snippet

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "osym_archive_docs"
STYLE_FILE = ARCHIVE_DIR / "osym_style_guide.json"
INBOX_DIR = ARCHIVE_DIR / "inbox"
WORD_RE = re.compile(r"[a-zçğıöşü0-9]{3,}", re.IGNORECASE)
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_ARCHIVE_URLS = 12


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(raw) -> list:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            return _json_list(json.loads(raw))
        except json.JSONDecodeError:
            return [raw.strip()]
    return []


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in WORD_RE.findall(text or "")}


def _unique(items: list[str], cap: int = 48) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= cap:
            break
    return out


def _load_seed() -> dict:
    if not STYLE_FILE.exists():
        return {}
    try:
        data = json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Stil rehberi okunamadı: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


def seed_style_guides(db: Session) -> int:
    seed = _load_seed()
    added = 0
    for code, payload in seed.items():
        target = normalize(code)
        if db.get(OsymStyleGuide, target) is not None:
            continue
        db.add(
            OsymStyleGuide(
                exam_target=target,
                years=str(payload.get("years") or "2016-2025"),
                stems_json=json.dumps(_json_list(payload.get("stems")), ensure_ascii=False),
                traps_json=json.dumps(_json_list(payload.get("traps")), ensure_ascii=False),
                topics_json=json.dumps(_json_list(payload.get("topics")), ensure_ascii=False),
                revision=1,
                updated_at=_utcnow(),
            )
        )
        added += 1
    if added:
        db.commit()
    return added


def style_revision(db: Session, exam_target: str | None) -> int:
    seed_style_guides(db)
    row = db.get(OsymStyleGuide, normalize(exam_target))
    return int(getattr(row, "revision", 0) or 0) if row else 0


def style_dict(db: Session, exam_target: str | None) -> dict:
    seed_style_guides(db)
    row = db.get(OsymStyleGuide, normalize(exam_target))
    if row is None:
        return {"stems": [], "traps": [], "topics": [], "years": "", "revision": 0}
    return {
        "stems": _json_list(row.stems_json),
        "traps": _json_list(row.traps_json),
        "topics": _json_list(row.topics_json),
        "years": row.years or "",
        "revision": int(row.revision or 1),
    }


def bump_topic_signal(
    db: Session,
    *,
    exam_target: str,
    topic: str,
    weight: int,
    source: str,
) -> None:
    label = (topic or "genel").strip()[:120] or "genel"
    target = normalize(exam_target)
    row = None
    for obj in list(db.new) + list(db.dirty):
        if (
            isinstance(obj, TopicSignal)
            and obj.exam_target == target
            and obj.topic == label
        ):
            row = obj
            break
    if row is None:
        row = db.scalars(
            select(TopicSignal)
            .where(TopicSignal.exam_target == target)
            .where(TopicSignal.topic == label)
        ).first()
    if row is None:
        try:
            with db.begin_nested():
                db.add(
                    TopicSignal(
                        exam_target=target,
                        topic=label,
                        weight=max(1, int(weight)),
                        source=source,
                        updated_at=_utcnow(),
                    )
                )
                db.flush()
            return
        except IntegrityError:
            row = db.scalars(
                select(TopicSignal)
                .where(TopicSignal.exam_target == target)
                .where(TopicSignal.topic == label)
            ).first()
            if row is None:
                return
    row.weight = int(row.weight or 0) + max(1, int(weight))
    row.source = source
    row.updated_at = _utcnow()


def top_topic_signals(db: Session, exam_target: str | None, limit: int = 8) -> list[dict]:
    target = normalize(exam_target)
    rows = db.scalars(
        select(TopicSignal)
        .where(TopicSignal.exam_target == target)
        .order_by(TopicSignal.weight.desc(), TopicSignal.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        {"topic": row.topic, "weight": int(row.weight or 0), "source": row.source}
        for row in rows
    ]


def ingest_video_signals(
    db: Session,
    *,
    user_id: str,
    video_id: str,
    lines: list[dict],
    subject: str | None,
    exam_target: str | None,
) -> list[dict]:
    seed_style_guides(db)
    hits = scan_hoca_highlights(lines, subject)
    target = normalize(exam_target)
    existing = {
        (row.timestamp, row.cue)
        for row in db.scalars(
            select(HocaHighlight)
            .where(HocaHighlight.video_id == video_id)
            .where(HocaHighlight.exam_target == target)
        ).all()
    }
    stored: list[dict] = []
    for hit in hits:
        key = (int(hit["timestamp"]), hit["cue"])
        if key in existing:
            continue
        db.add(
            HocaHighlight(
                user_id=user_id or "",
                video_id=video_id or "",
                exam_target=target,
                subject=(subject or "")[:128],
                cue=hit["cue"],
                snippet=hit["snippet"],
                topic=hit["topic"],
                timestamp=int(hit["timestamp"]),
                weight=int(hit["weight"]),
            )
        )
        bump_topic_signal(
            db,
            exam_target=target,
            topic=hit["topic"],
            weight=int(hit["weight"]),
            source="hoca_highlight",
        )
        stored.append(hit)
        existing.add(key)
    if stored:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    return stored


def retrieve(db: Session, *, exam_target: str | None, query: str = "", limit: int = 8) -> dict:
    seed_style_guides(db)
    target = normalize(exam_target)
    guide = style_dict(db, target)
    needles = _tokens(query) or set(guide.get("topics") or [])
    chunks = db.scalars(
        select(OsymArchiveChunk)
        .where(OsymArchiveChunk.exam_target == target)
        .order_by(OsymArchiveChunk.id.desc())
        .limit(80)
    ).all()
    ranked = []
    for chunk in chunks:
        score = len(needles & _tokens(f"{chunk.body} {chunk.topic}"))
        if chunk.topic and query and chunk.topic.lower() in query.lower():
            score += 3
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], -item[1].id))
    take = ranked[:limit] if needles else ranked[:limit]
    archive = [
        {"kind": row.kind, "body": row.body, "topic": row.topic, "year": row.exam_year}
        for score, row in take
        if score > 0 or not needles
    ][:limit]

    highlights = db.scalars(
        select(HocaHighlight)
        .where(HocaHighlight.exam_target == target)
        .order_by(HocaHighlight.weight.desc(), HocaHighlight.id.desc())
        .limit(40)
    ).all()
    h_ranked = [
        (len(needles & _tokens(f"{row.snippet} {row.topic} {row.subject}")) + int(row.weight or 0), row)
        for row in highlights
    ]
    h_ranked.sort(key=lambda item: -item[0])
    hoca = [
        {
            "cue": row.cue,
            "topic": row.topic,
            "snippet": row.snippet,
            "timestamp": row.timestamp,
            "weight": row.weight,
        }
        for _, row in h_ranked[:limit]
    ]
    return {
        "exam_target": target,
        "style": guide,
        "archive": archive[:6],
        "hoca_highlights": hoca[:6],
        "topic_signals": top_topic_signals(db, target, 6),
    }


def prompt_block_rag(db: Session, exam_target: str | None, query: str = "") -> str:
    pack = retrieve(db, exam_target=exam_target, query=query)
    guide = pack["style"]
    stems = " | ".join((guide.get("stems") or [])[:6]) or "klasik ÖSYM kökü"
    traps = "\n".join(f"- {item}" for item in (guide.get("traps") or [])[:6]) or "- yakın kavram çeldiricisi"
    hl_lines = "\n".join(
        f"- [{item['cue']}] {item['topic']}: {item['snippet'][:140]}"
        for item in pack["hoca_highlights"][:5]
    ) or "- henüz hoca vurgusu yok"
    archive_lines = "\n".join(
        f"- ({item.get('year') or '?'}) {item['body'][:180]}"
        for item in pack["archive"][:5]
    ) or "- arşiv parçası yok; stil rehberine uy"
    signals = ", ".join(
        f"{item['topic']} ({item['weight']})" for item in pack["topic_signals"][:6]
    ) or "yok"
    return f"""
RAG / ÖĞRENME MOTORU — rastgele soru YASAK.
osym_style_guide (yıllar {guide.get('years') or '2016-2025'}, rev {guide.get('revision') or 1}):
Kök kalıpları: {stems}
Tuzaklar:
{traps}
hoca_highlights (videolardaki banko / dikkat etiketleri):
{hl_lines}
Önemli konu sinyalleri: {signals}
Arşiv referansları:
{archive_lines}
Bu kalıpları ve vurguları taklit et; altyazıda olmayan yıl/kurum uydurma.
"""


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF okumak için pypdf kurulu olmalı.") from exc
    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages[:80]]
    return "\n".join(part for part in pages if part)


def parse_archive_urls(raw) -> list[str]:
    if isinstance(raw, str):
        items = re.split(r"[\s,]+", raw)
    elif isinstance(raw, (list, tuple)):
        items = []
        for item in raw:
            items.extend(re.split(r"[\s,]+", str(item or "")))
    else:
        items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        url = item.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= MAX_ARCHIVE_URLS:
            break
    return out


def _validate_archive_url(url: str) -> str:
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Sadece http veya https PDF linki kabul edilir.")
    host = (parsed.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".local"):
        raise ValueError("Yerel adresler arşiv linki olarak kullanılamaz.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local):
        raise ValueError("İç ağ adresleri arşiv linki olarak kullanılamaz.")
    return cleaned


def _filename_from_url(url: str, headers) -> str:
    disposition = str(headers.get("content-disposition") or "")
    match = re.search(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", disposition, re.IGNORECASE)
    if match:
        name = unquote(match.group(1).strip().strip('"'))
        if name:
            return Path(name).name[:180]
    path_name = unquote(Path(urlparse(url).path).name)
    if path_name:
        return path_name[:180]
    ctype = str(headers.get("content-type") or "").lower()
    if "pdf" in ctype:
        return "arsiv.pdf"
    return "arsiv.bin"


def fetch_archive_url(url: str) -> tuple[str, bytes]:
    import httpx

    cleaned = _validate_archive_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TilkoArsiv/1.0; +https://osym.gov.tr)",
        "Accept": "application/pdf,application/octet-stream,*/*",
        "Referer": f"{urlparse(cleaned).scheme}://{urlparse(cleaned).netloc}/",
    }
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            with client.stream("GET", cleaned) as response:
                response.raise_for_status()
                try:
                    length = int(response.headers.get("content-length") or 0)
                except ValueError:
                    length = 0
                if length > MAX_ARCHIVE_BYTES:
                    raise ValueError("PDF 40 MB sınırını aşıyor.")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise ValueError("PDF 40 MB sınırını aşıyor.")
                    chunks.append(chunk)
                data = b"".join(chunks)
                name = _filename_from_url(str(response.url), response.headers)
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Link açılamadı ({exc.response.status_code}): {cleaned}") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Link indirilemedi: {cleaned}") from exc
    if not data:
        raise ValueError(f"Link boş dosya döndü: {cleaned}")
    preview = data[:800].lstrip().lower()
    if data[:5] != b"%PDF-" and (b"<html" in preview or preview.startswith(b"<!doctype")):
        raise ValueError("Link PDF değil, web sayfası açıldı.")
    if data[:5] == b"%PDF-" and not name.lower().endswith(".pdf"):
        name = f"{name}.pdf" if "." not in name else f"{Path(name).stem}.pdf"
    return name, data


def ingest_upload(db: Session, name: str, data: bytes, exam_target: str | None, exam_year: int = 0) -> dict:
    suffix = Path(name).suffix.lower()
    text = extract_pdf_text(data) if suffix == ".pdf" or data[:5] == b"%PDF-" else data.decode(
        "utf-8", errors="ignore"
    )
    return ingest_document(
        db,
        filename=name,
        text=text,
        exam_target=exam_target,
        exam_year=exam_year,
    )


def _read_file_bytes(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(raw)
    return raw.decode("utf-8", errors="ignore")


def _chunk_text(text: str, size: int = 900) -> list[str]:
    clean = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if not clean:
        return []
    parts: list[str] = []
    buf = ""
    for line in clean.splitlines():
        if len(buf) + len(line) + 1 > size and buf:
            parts.append(buf.strip())
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf.strip():
        parts.append(buf.strip())
    return parts[:40]


def _extract_patterns(text: str, exam_target: str, filename: str) -> dict:
    from app.services.llm import complete_json

    excerpt = text[:12000]
    fallback = {
        "exam_year": 0,
        "stems": [],
        "traps": [],
        "topics": [topic_from_snippet(excerpt[:200])],
        "samples": [],
    }
    try:
        answer = complete_json(
            "ÖSYM soru analisti. Çıktı SADECE geçerli JSON. Telifli soruyu aynen kopyalama; "
            "kalıp, tuzak türü ve konu çıkar.",
            f"""Sınav kodu: {exam_target}
Dosya: {filename}
Metin:
---
{excerpt}
---
Çıktı:
{{
  "exam_year": 2024,
  "stems": ["tekrar eden soru kökü kalıbı"],
  "traps": ["çeldirici / tuzak türü"],
  "topics": ["konu"],
  "samples": [{{"stem": "anonimleştirilmiş kök özeti", "trap": "tuzak", "topic": "konu"}}]
}}
""",
            task="osym_archive_feed",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Arşiv LLM analizi atlandı: %s", exc)
        return fallback
    year = int(answer.get("exam_year") or 0)
    if year < 2015 or year > 2030:
        year = 0
    samples = answer.get("samples") if isinstance(answer.get("samples"), list) else []
    clean_samples = []
    for item in samples[:12]:
        if not isinstance(item, dict):
            continue
        stem = str(item.get("stem") or item.get("text") or "").strip()
        if not stem:
            continue
        clean_samples.append(
            {
                "stem": stem[:400],
                "trap": str(item.get("trap") or "").strip()[:240],
                "topic": str(item.get("topic") or topic_from_snippet(stem))[:120],
            }
        )
    return {
        "exam_year": year,
        "stems": _unique(_json_list(answer.get("stems")), 24),
        "traps": _unique(_json_list(answer.get("traps")), 24),
        "topics": _unique(_json_list(answer.get("topics")), 24),
        "samples": clean_samples,
    }


def _merge_years(current: str, year: int) -> str:
    nums = [int(item) for item in re.findall(r"20\d{2}", current or "")]
    nums.append(year)
    low, high = min(nums), max(nums)
    return f"{low}-{high}" if low != high else str(low)


def merge_style_guide(db: Session, exam_target: str, patterns: dict) -> None:
    target = normalize(exam_target)
    row = db.get(OsymStyleGuide, target)
    if row is None:
        row = OsymStyleGuide(
            exam_target=target,
            years="2016-2025",
            stems_json="[]",
            traps_json="[]",
            topics_json="[]",
            revision=0,
        )
        db.add(row)
        db.flush()
    row.stems_json = json.dumps(
        _unique(_json_list(row.stems_json) + _json_list(patterns.get("stems"))),
        ensure_ascii=False,
    )
    row.traps_json = json.dumps(
        _unique(_json_list(row.traps_json) + _json_list(patterns.get("traps"))),
        ensure_ascii=False,
    )
    row.topics_json = json.dumps(
        _unique(_json_list(row.topics_json) + _json_list(patterns.get("topics"))),
        ensure_ascii=False,
    )
    year = int(patterns.get("exam_year") or 0)
    if year:
        row.years = _merge_years(row.years, year)
    row.revision = int(row.revision or 0) + 1
    row.updated_at = _utcnow()


def ingest_document(
    db: Session,
    *,
    filename: str,
    text: str,
    exam_target: str | None,
    exam_year: int = 0,
) -> dict:
    seed_style_guides(db)
    target = normalize(exam_target)
    blob = (text or "").strip()
    if len(blob) < 40:
        raise ValueError("Arşiv metni çok kısa.")
    digest = hashlib.sha256(blob.encode("utf-8", errors="ignore")).hexdigest()
    existing = db.scalars(
        select(OsymArchiveDoc).where(OsymArchiveDoc.content_hash == digest)
    ).first()
    if existing is not None:
        return {
            "filename": filename,
            "skipped": True,
            "doc_id": existing.id,
            "chunks": existing.chunk_count,
        }

    patterns = _extract_patterns(blob, target, filename)
    year = exam_year or int(patterns.get("exam_year") or 0)
    doc = OsymArchiveDoc(
        filename=(filename or "upload")[:256],
        exam_target=target,
        exam_year=year,
        content_hash=digest,
        text_excerpt=blob[:4000],
        patterns_json=json.dumps(
            {key: patterns[key] for key in ("exam_year", "stems", "traps", "topics") if key in patterns},
            ensure_ascii=False,
        ),
        chunk_count=0,
    )
    db.add(doc)
    db.flush()
    bodies = [sample["stem"] for sample in patterns.get("samples") or [] if sample.get("stem")]
    bodies.extend(_chunk_text(blob)[:12])
    count = 0
    for body in _unique(bodies, 24):
        topic = topic_from_snippet(body)
        db.add(
            OsymArchiveChunk(
                doc_id=doc.id,
                exam_target=target,
                kind="stem",
                body=body[:1200],
                topic=topic,
                exam_year=year,
            )
        )
        bump_topic_signal(db, exam_target=target, topic=topic, weight=2, source="archive")
        count += 1
    for trap in patterns.get("traps") or []:
        db.add(
            OsymArchiveChunk(
                doc_id=doc.id,
                exam_target=target,
                kind="trap",
                body=trap[:1200],
                topic=topic_from_snippet(trap),
                exam_year=year,
            )
        )
        count += 1
    doc.chunk_count = count
    merge_style_guide(db, target, patterns)
    db.commit()
    db.refresh(doc)
    return {
        "filename": filename,
        "skipped": False,
        "doc_id": doc.id,
        "chunks": count,
        "exam_year": year,
        "revision": style_revision(db, target),
    }


def ingest_path(db: Session, path: Path, exam_target: str | None, exam_year: int = 0) -> dict:
    return ingest_document(
        db,
        filename=path.name,
        text=_read_file_bytes(path),
        exam_target=exam_target,
        exam_year=exam_year,
    )


def feed_archives(
    db: Session,
    *,
    exam_target: str | None = None,
    exam_year: int = 0,
    uploads: list[tuple[str, bytes]] | None = None,
    urls: list[str] | None = None,
    scan_inbox: bool | None = None,
) -> dict:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    seed_style_guides(db)
    results: list[dict] = []
    for name, data in uploads or []:
        try:
            results.append(ingest_upload(db, name, data, exam_target, exam_year))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Yükleme atlandı (%s): %s", name, exc)
            results.append({"filename": name, "error": str(exc)})
    parsed_urls = parse_archive_urls(urls)
    for url in parsed_urls:
        try:
            name, data = fetch_archive_url(url)
            row = ingest_upload(db, name, data, exam_target, exam_year)
            row["source_url"] = url
            results.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Link atlandı (%s): %s", url, exc)
            results.append({"filename": url, "error": str(exc)})
    should_scan = INBOX_DIR.exists() and (
        bool(scan_inbox) if scan_inbox is not None else not (uploads or parsed_urls)
    )
    if should_scan:
        for path in sorted(INBOX_DIR.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".pdf", ".txt", ".md", ".json"}:
                continue
            try:
                results.append(ingest_path(db, path, exam_target, exam_year))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Inbox atlandı (%s): %s", path.name, exc)
                results.append({"filename": path.name, "error": str(exc)})
    return {
        "ok": True,
        "processed": len(results),
        "results": results,
        "style_revision": style_revision(db, exam_target),
        "signals": top_topic_signals(db, exam_target, 8),
    }


def rag_status(db: Session, exam_target: str | None = None) -> dict:
    seed_style_guides(db)
    target = normalize(exam_target) if exam_target else "kpss_lisans"
    docs = db.scalar(select(func.count(OsymArchiveDoc.id))) or 0
    chunks = db.scalar(select(func.count(OsymArchiveChunk.id))) or 0
    highlights = db.scalar(select(func.count(HocaHighlight.id))) or 0
    return {
        "docs": int(docs),
        "chunks": int(chunks),
        "highlights": int(highlights),
        "style": style_dict(db, target),
        "topic_signals": top_topic_signals(db, target, 10),
        "archive_dir": str(ARCHIVE_DIR),
    }


def compose_hunt_question(db: Session, exam_target: str, day) -> dict | None:
    from app.services.exams import label_for
    from app.services.llm import complete_json
    from app.services.subjects import parse_premises, parse_steps

    pack = retrieve(db, exam_target=exam_target, query="")
    if not (
        pack["hoca_highlights"]
        or pack["archive"]
        or pack["topic_signals"]
        or pack["style"].get("stems")
        or pack["style"].get("traps")
    ):
        return None
    week = day.isocalendar()[1]
    flavor = "sözel"
    if week % 2 == 0:
        flavor = "sayısal mantık"
    if exam_target == "yks" and week % 4 == 3:
        flavor = "YKS Fen öncüllü (I, II, III)"
    rag = prompt_block_rag(db, exam_target, flavor)
    try:
        answer = complete_json(
            "ÖSYM soru yazarısın. Tek soru. Çıktı SADECE geçerli JSON.",
            f"""Hedef: {label_for(exam_target)}
Haftalık damga: {flavor}
{rag}

Çıktı:
{{
  "question_text": "kök",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
  "correct_answer": "C",
  "trap_explanation": "çeldirici analizi",
  "subject_type": "sozel veya sayisal",
  "shortcut_tactic": "",
  "step_by_step_solution": [],
  "is_yks_fen": false,
  "fen_branch": "",
  "misconception_tag": "",
  "premises": []
}}
""",
            task="sazan_avi_rag",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG Sazan Avı üretilemedi, bankaya düşülecek: %s", exc)
        return None
    text = str(answer.get("question_text") or "").strip()
    options = answer.get("options") if isinstance(answer.get("options"), dict) else {}
    correct = str(answer.get("correct_answer") or answer.get("correct") or "").strip().upper()[:1]
    if not text or len(options) < 4 or correct not in {"A", "B", "C", "D", "E"}:
        return None
    kind = "sayisal" if flavor != "sözel" else "sozel"
    if str(answer.get("subject_type") or "").lower() == "sayisal":
        kind = "sayisal"
    return {
        "question_text": text,
        "options": {str(k): str(v) for k, v in options.items()},
        "correct_answer": correct,
        "trap_explanation": str(answer.get("trap_explanation") or "").strip()
        or "ÖSYM arşiv kalıbı + hoca vurgusu.",
        "subject_type": kind,
        "shortcut_tactic": str(answer.get("shortcut_tactic") or ""),
        "step_by_step_solution": parse_steps(answer.get("step_by_step_solution")),
        "is_yks_fen": bool(answer.get("is_yks_fen") or flavor.startswith("YKS Fen")),
        "fen_branch": str(answer.get("fen_branch") or ""),
        "misconception_tag": str(answer.get("misconception_tag") or ""),
        "premises": parse_premises(answer.get("premises")),
        "exams": [exam_target],
    }
