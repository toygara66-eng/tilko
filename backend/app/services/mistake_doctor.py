"""Tuzak Defteri hatalarını tipine göre sınıflandıran Yanlış Analiz Doktoru."""

from __future__ import annotations

import json
import logging
from collections import Counter

from sqlalchemy.orm import Session

from app.database.models import TrapNotebook
from app.services.ranks import address_for
from app.services.traps import all_traps

logger = logging.getLogger(__name__)

TYPE_KNOWLEDGE = "Bilgi eksikliği"
TYPE_ATTENTION = "Dikkat hatası"
TYPE_DISTRACTOR = "ÖSYM çeldirici tuzağı"
TYPE_TIME = "Süre tuzağı"
MISTAKE_TYPES = (TYPE_KNOWLEDGE, TYPE_ATTENTION, TYPE_DISTRACTOR, TYPE_TIME)

OYS_NEEDLES = (
    "çeldirici",
    "celdirici",
    "klasik kaydır",
    "karıştırılan",
    "yakın kavram",
    "şık kaydır",
)
ATTENTION_NEEDLES = ("acele", "okumadan", "dikkatsiz", "şık atladı", "kökü")

PRESCRIPTION = {
    TYPE_KNOWLEDGE: "Zayıf konuyu Tuzak Defteri’nden 3 tekrar yap; video notundaki ezber kırıntısını kırmızıya çek.",
    TYPE_ATTENTION: "Şıkka bakmadan soru kökünü bitir. Anahtar kelimeyi parmakla işaretle, sonra şıklara in.",
    TYPE_DISTRACTOR: "Yakın kavram çiftlerini (1839/1856 gibi) yan yana yaz. ÖSYM’nin klasik kaydırmasını ezberle.",
    TYPE_TIME: "60 saniye kuralı: süre dolunca şık seç, savurma. Kronometre açık çöz.",
}


def _blob(row: TrapNotebook) -> str:
    return " ".join(
        [
            row.question_text or "",
            row.explanation or "",
            row.distractor_analysis or "",
            getattr(row, "teacher_note", "") or "",
            row.topic or "",
        ]
    ).lower()


def classify_trap(row: TrapNotebook) -> str:
    if row.time_trap_triggered:
        return TYPE_TIME
    spent = int(row.time_spent_seconds or 0)
    text = _blob(row)
    if spent and spent < 12:
        return TYPE_ATTENTION
    if any(needle in text for needle in ATTENTION_NEEDLES):
        return TYPE_ATTENTION
    if any(needle in text for needle in OYS_NEEDLES):
        return TYPE_DISTRACTOR
    return TYPE_KNOWLEDGE


def _percentages(counts: Counter[str], total: int) -> list[dict]:
    present = [(name, counts[name]) for name in MISTAKE_TYPES if counts[name] > 0]
    if not present or total <= 0:
        return []
    leftover = 100
    out: list[dict] = []
    for index, (name, count) in enumerate(present):
        if index == len(present) - 1:
            rate = max(leftover, 0)
        else:
            rate = round(100 * count / total)
            leftover -= rate
        out.append({"type": name, "count": count, "rate": rate})
    return sorted(out, key=lambda item: (-item["rate"], item["type"]))


def _topics(rows: list[TrapNotebook]) -> list[str]:
    ranked = Counter((row.topic or "").strip() for row in rows if (row.topic or "").strip())
    return [name for name, _ in ranked.most_common(4)]


def _fallback_copy(title: str, dominant: str | None, trap_count: int) -> tuple[str, str]:
    if trap_count <= 0:
        return (
            f"Hey {title}, defter henüz boş. Birkaç tuzağa düşünce doktor teşhis koyacak.",
            "Dashboard’dan video analiz et, yanlışın deftere düşsün.",
        )
    if dominant == TYPE_ATTENTION:
        summary = (
            f"Hey {title}, düşüşlerin {trap_count} tuzakta ağırlıklı dikkat hatası. "
            "Kökü bitirmeden şıkka atlıyorsun."
        )
    elif dominant == TYPE_DISTRACTOR:
        summary = (
            f"Hey {title}, ÖSYM çeldiricisine yem oluyorsun. Yakın kavramları ayırt etmeden işaretliyorsun."
        )
    elif dominant == TYPE_TIME:
        summary = (
            f"Hey {title}, bilgi değil süre kaybettiriyor. 60 saniyeyi aşınca tuzak kapanıyor."
        )
    else:
        summary = (
            f"Hey {title}, asıl açık bilgi eksikliği. Ezber kırıntısı oturmadan yorum yapıyorsun."
        )
    return summary, PRESCRIPTION.get(dominant or TYPE_KNOWLEDGE, PRESCRIPTION[TYPE_KNOWLEDGE])


def _pack(
    *,
    user_id: str,
    title: str,
    rows: list[TrapNotebook],
    labels: list[str],
    summary: str,
    prescription: str,
    source: str,
) -> dict:
    total = len(rows)
    counts = Counter(labels)
    types = _percentages(counts, total)
    dominant = types[0]["type"] if types else None
    return {
        "user_id": user_id,
        "title": title,
        "trap_count": total,
        "types": types,
        "dominant": dominant,
        "summary": summary,
        "prescription": prescription,
        "weak_topics": _topics(rows),
        "source": source,
    }


def _llm_refine(title: str, rows: list[TrapNotebook], local: dict, exam_target: str | None = None) -> dict | None:
    from app.services.exams import label_for, prompt_block
    from app.services.llm import complete_json

    exam_label = label_for(exam_target)
    sample = []
    for row in rows[:24]:
        sample.append(
            {
                "topic": row.topic or "",
                "chosen": row.chosen or "",
                "correct": row.correct or "",
                "seconds": int(row.time_spent_seconds or 0),
                "time_trap": bool(row.time_trap_triggered),
                "hint": (row.distractor_analysis or row.explanation or "")[:180],
            }
        )
    prompt = f"""Öğrenci rütbesi: {title}
Hedef sınav: {exam_label}
Tuzak Defteri kayıt sayısı: {len(rows)}
Yerel ön sınıflama: {json.dumps(local['types'], ensure_ascii=False)}
Örnek tuzaklar:
{json.dumps(sample, ensure_ascii=False)}

Her kaydı şu tiplerden BİRİNE ayır: {", ".join(MISTAKE_TYPES)}.
Yüzdeler tam 100 olsun. 2 cümlelik TİLKO özeti yaz; öğrenciye '{title}' diye hitap et.
1 cümlelik reçete ver.

JSON:
{{
  "types": [
    {{"type": "Dikkat hatası", "count": 8, "rate": 65}}
  ],
  "dominant": "Dikkat hatası",
  "summary": "...",
  "prescription": "..."
}}
"""
    system = (
        "Sen TİLKO'nun Yanlış Analiz Doktorusun. "
        f"Hedef sınav: {exam_label}. {prompt_block(exam_target)} "
        f"Öğrenciye yalnızca '{title}' diye hitap et. Çıktı SADECE geçerli JSON."
    )
    try:
        data = complete_json(system, prompt, temperature=0.3, task="mistake-doctor")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yanlış Analiz Doktoru LLM düştü: %s", exc)
        return None
    raw_types = data.get("types") or []
    cleaned: list[dict] = []
    allowed = set(MISTAKE_TYPES)
    for item in raw_types:
        name = str(item.get("type") or "").strip()
        if name not in allowed:
            continue
        count = max(int(item.get("count") or 0), 0)
        rate = max(min(int(item.get("rate") or 0), 100), 0)
        if count <= 0 and rate <= 0:
            continue
        cleaned.append({"type": name, "count": count, "rate": rate})
    if not cleaned:
        return None
    leftover = 100
    for index, item in enumerate(cleaned):
        if index == len(cleaned) - 1:
            item["rate"] = max(leftover, 0)
        else:
            leftover -= item["rate"]
    cleaned.sort(key=lambda item: (-item["rate"], item["type"]))
    dominant = str(data.get("dominant") or cleaned[0]["type"]).strip()
    if dominant not in allowed:
        dominant = cleaned[0]["type"]
    summary = str(data.get("summary") or "").strip()
    prescription = str(data.get("prescription") or "").strip()
    return {
        "types": cleaned,
        "dominant": dominant,
        "summary": summary,
        "prescription": prescription or PRESCRIPTION.get(dominant, ""),
    }


def diagnose(db: Session, user_id: str) -> dict:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    title = address_for(db, uid)
    from app.services.exams import exam_of

    exam_target = exam_of(db, uid)
    rows = all_traps(db, uid)
    labels = [classify_trap(row) for row in rows]
    local_summary, local_rx = _fallback_copy(
        title,
        Counter(labels).most_common(1)[0][0] if labels else None,
        len(rows),
    )
    packed = _pack(
        user_id=uid,
        title=title,
        rows=rows,
        labels=labels,
        summary=local_summary,
        prescription=local_rx,
        source="local",
    )
    if not rows:
        return packed
    refined = _llm_refine(title, rows, packed, exam_target=exam_target)
    if not refined:
        return packed
    packed["types"] = refined["types"]
    packed["dominant"] = refined["dominant"]
    packed["summary"] = refined["summary"] or packed["summary"]
    packed["prescription"] = refined["prescription"] or packed["prescription"]
    packed["source"] = "llm"
    return packed
