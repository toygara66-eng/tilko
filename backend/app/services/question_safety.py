"""Soru metni / şık temizliği — cevap sızıntısını azalt."""

from __future__ import annotations

import re

_OPTION_LEAK_RE = re.compile(
    r"\s*[\(\[]?\s*(doğru|dogru|correct|cevap\s*[:\-]?|yan[iı]t\s*[:\-]?)\s*[\)\]]?",
    re.IGNORECASE,
)
_CHECK_RE = re.compile(r"\s*✓\s*")


def sanitize_option_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = _OPTION_LEAK_RE.sub("", raw)
    cleaned = _CHECK_RE.sub(" ", cleaned)
    return cleaned.strip()


def sanitize_options(options: dict) -> dict[str, str]:
    if not isinstance(options, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in options.items():
        letter = str(key).strip().upper()[:1]
        if not letter:
            continue
        out[letter] = sanitize_option_text(str(value))
    return out


def scrub_premises_for_play(premises: list, *, reveal: bool) -> list[dict]:
    rows: list[dict] = []
    for item in premises or []:
        if not isinstance(item, dict):
            text = str(item or "").strip()
            if not text:
                continue
            rows.append({"id": "", "text": text, "is_correct": False, "why": ""})
            continue
        rows.append(
            {
                "id": str(item.get("id") or "").strip(),
                "text": str(item.get("text") or item.get("statement") or "").strip(),
                "is_correct": bool(item.get("is_correct")) if reveal else False,
                "why": str(item.get("why") or "").strip() if reveal else "",
            }
        )
    return [row for row in rows if row.get("text")]
