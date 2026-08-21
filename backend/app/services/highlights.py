"""Hoca vurgu taraması — transkriptten önemli konu sinyali."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Ağırlık: banko > ÖSYM çıkar > dikkat / altını çiz
CUE_PATTERNS: tuple[tuple[str, int, str], ...] = (
    (r"\bbanko\b", 5, "banko gelir"),
    (r"kesinlikle\s+ç(ı|i)kar", 5, "kesinlikle çıkar"),
    (r"her\s+y(ı|i)l\s+sorar", 5, "her yıl sorar"),
    (r"ösym\s+sever", 4, "ÖSYM sever"),
    (r"alt(ı|i)n(ı|i)\s+çiz", 4, "altını çiziyorum"),
    (r"k(ı|i)rm(ı|i)z(ı|i)\s+kalem", 4, "kırmızı kalem"),
    (r"y(ı|i)ld(ı|i)zl(ı|i)\s+konu", 4, "yıldızlı konu"),
    (r"buras(ı|i)\s+önemli", 3, "burası önemli"),
    (r"dikkat\s+edin", 3, "dikkat edin"),
    (r"dikkat\s+et", 3, "dikkat et"),
    (r"mutlaka\s+(ezber|bil|yaz|sor)", 3, "mutlaka"),
    (r"kar(ı|i)şt(ı|i)rma", 3, "karıştırma"),
    (r"\btuzak\b", 3, "tuzak"),
    (r"ezberleyin", 2, "ezberleyin"),
    (r"şıklar(a|ı)\s+bak", 2, "şıklara bak"),
    (r"çeldirici", 2, "çeldirici"),
)

STOP = {
    "bir",
    "bu",
    "şu",
    "ve",
    "ile",
    "için",
    "gibi",
    "daha",
    "çok",
    "ama",
    "değil",
    "olan",
    "olarak",
    "sonra",
    "önce",
    "yani",
    "işte",
    "bakın",
    "şimdi",
    "evet",
    "hayır",
    "the",
    "and",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def topic_from_snippet(snippet: str, subject: str | None = None) -> str:
    if subject and subject.strip():
        return subject.strip()[:120]
    words = [
        token
        for token in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{4,}", snippet or "")
        if token.lower() not in STOP
    ]
    if not words:
        return "genel"
    return " ".join(words[:4])[:120]


def scan_hoca_highlights(lines: Iterable[dict], subject: str | None = None) -> list[dict]:
    """Transkript satırlarında vurgu kalıplarını tarar."""
    compiled = [(re.compile(pattern, re.IGNORECASE), weight, cue) for pattern, weight, cue in CUE_PATTERNS]
    hits: list[dict] = []
    seen: set[tuple[int, str]] = set()
    buffer: list[dict] = list(lines or [])
    for index, row in enumerate(buffer):
        text = _norm(str(row.get("text") or ""))
        if len(text) < 8:
            continue
        start = int(float(row.get("start") or 0))
        for regex, weight, cue in compiled:
            if not regex.search(text):
                continue
            key = (start, cue)
            if key in seen:
                continue
            seen.add(key)
            neighbor = ""
            if index + 1 < len(buffer):
                neighbor = _norm(str(buffer[index + 1].get("text") or ""))
            snippet = _norm(f"{text} {neighbor}")[:280]
            hits.append(
                {
                    "cue": cue,
                    "snippet": snippet,
                    "timestamp": start,
                    "weight": weight,
                    "topic": topic_from_snippet(snippet, subject),
                }
            )
    hits.sort(key=lambda item: (-int(item["weight"]), int(item["timestamp"])))
    return hits[:40]
