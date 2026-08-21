"""Kişiselleştirilmiş anlık deneme: ÖSYM DNA + Tuzak Defteri."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.database.models import DynamicExam, UserBaseline
from app.services.exams import (
    SECONDS_PER_QUESTION,
    catalog_for,
    exam_of,
    label_for,
    normalize,
    prompt_block,
    subjects_for,
)
from app.services.ranks import RANK_ACEMI, address_for
from app.services.subjects import classify, parse_premises, parse_steps

logger = logging.getLogger(__name__)

MIN_COUNT = 5
MAX_COUNT = 25
LLM_BATCH = 8
MAX_TRAP_SAVES = 5
FAST_SECONDS_PER_Q = 4

FALLBACK_BANK = [
    {
        "topic": "Tarih",
        "question_text": "Lozan Antlaşması hangi yılda imzalanmıştır?",
        "options": {"A": "1920", "B": "1921", "C": "1922", "D": "1923", "E": "1924"},
        "correct": "D",
        "explanation": "Lozan 24 Temmuz 1923’te imzalandı. 1920 Sevr’dir.",
    },
    {
        "topic": "Tarih",
        "question_text": "Saltanat hangi tarihte kaldırılmıştır?",
        "options": {
            "A": "23 Nisan 1920",
            "B": "1 Kasım 1922",
            "C": "29 Ekim 1923",
            "D": "3 Mart 1924",
            "E": "20 Ocak 1921",
        },
        "correct": "B",
        "explanation": "Saltanat 1 Kasım 1922’de kaldırıldı; hilafet 3 Mart 1924.",
    },
    {
        "topic": "Vatandaşlık",
        "question_text": "1982 Anayasası’na göre yasama yetkisi kime aittir?",
        "options": {
            "A": "Cumhurbaşkanı",
            "B": "Bakanlar Kurulu",
            "C": "TBMM",
            "D": "Anayasa Mahkemesi",
            "E": "Hâkimler ve Savcılar Kurulu",
        },
        "correct": "C",
        "explanation": "Yasama TBMM’nindir; yürütme Cumhurbaşkanı’ndadır.",
    },
    {
        "topic": "Vatandaşlık",
        "question_text": "2017 Anayasa değişikliği ile hangi hükümet sistemine geçilmiştir?",
        "options": {
            "A": "Parlamenter sistem",
            "B": "Yarı başkanlık",
            "C": "Cumhurbaşkanlığı hükümet sistemi",
            "D": "Meclis hükümeti",
            "E": "Anayasal monarşi",
        },
        "correct": "C",
        "explanation": "2017 ile Cumhurbaşkanlığı hükümet sistemine geçildi.",
    },
    {
        "topic": "Coğrafya",
        "question_text": "Van Gölü hangi havza tipindedir?",
        "options": {
            "A": "Açık havza",
            "B": "Kapalı havza",
            "C": "Delta havzası",
            "D": "Karstik havza",
            "E": "Gelgit havzası",
        },
        "correct": "B",
        "explanation": "Van Gölü kapalı havzadır; gideğeni yoktur.",
    },
    {
        "topic": "Coğrafya",
        "question_text": "Akdeniz ikliminin Türkiye’deki tipik özelliği hangisidir?",
        "options": {
            "A": "Yazlar serin ve yağışlı, kışlar kurak",
            "B": "Yazlar sıcak ve kurak, kışlar ılık ve yağışlı",
            "C": "Yıl boyu bol yağış ve orman",
            "D": "Kışın don, yazın muson yağmuru",
            "E": "Çöl etkisi ve gece-gündüz farkı yok",
        },
        "correct": "B",
        "explanation": "Akdeniz iklimi: yaz sıcak-kurak, kış ılık-yağışlı.",
    },
    {
        "topic": "Türkçe",
        "question_text": "“Okuldan çıkınca eve gittim.” cümlesinde “çıkınca” sözcüğünün görevi nedir?",
        "options": {
            "A": "Zarf-fiil (ulaç)",
            "B": "Sıfat-fiil (ortaç)",
            "C": "İsim-fiil (mastar)",
            "D": "Edat",
            "E": "Bağlaç",
        },
        "correct": "A",
        "explanation": "-ınca eki zarf-fiildir; zaman bildirir.",
    },
    {
        "topic": "Türkçe",
        "question_text": "Aşağıdaki sözcüklerden hangisinde büyük ünlü uyumu yoktur?",
        "options": {
            "A": "kapı",
            "B": "anne",
            "C": "yıldız",
            "D": "elma",
            "E": "kitap",
        },
        "correct": "B",
        "explanation": "anne: a-e karışımı büyük ünlü uyumunu bozar.",
    },
    {
        "topic": "Güncel",
        "question_text": "Türkiye Büyük Millet Meclisi hangi tarihte açılmıştır?",
        "options": {
            "A": "19 Mayıs 1919",
            "B": "23 Nisan 1920",
            "C": "30 Ağustos 1922",
            "D": "29 Ekim 1923",
            "E": "3 Mart 1924",
        },
        "correct": "B",
        "explanation": "TBMM 23 Nisan 1920’de açıldı.",
    },
    {
        "topic": "Matematik",
        "question_text": "Bir sayının %20’si 16 ise sayının kendisi kaçtır?",
        "options": {"A": "64", "B": "72", "C": "80", "D": "96", "E": "120"},
        "correct": "C",
        "explanation": "x · 0,20 = 16 → x = 80.",
        "subject_type": "sayisal",
        "step_by_step_solution": [
            "Yüzde 20, sayının 1/5’idir.",
            "x / 5 = 16",
            "x = 16 · 5 = 80",
        ],
        "shortcut_tactic": "16’yı 5 ile çarp: yüzde 20 = 1/5.",
    },
    {
        "topic": "Matematik",
        "question_text": "2x + 6 = 18 ise x kaçtır?",
        "options": {"A": "4", "B": "5", "C": "6", "D": "8", "E": "12"},
        "correct": "C",
        "explanation": "2x = 12 → x = 6.",
        "subject_type": "sayisal",
        "step_by_step_solution": ["2x + 6 = 18", "2x = 12", "x = 6"],
        "shortcut_tactic": "6’yı karşıya at, 12’yi 2’ye böl.",
    },
    {
        "topic": "Fizik",
        "question_text": "Newton’un ikinci yasası hangisidir?",
        "options": {
            "A": "Etki tepkiye eşittir",
            "B": "F = m · a",
            "C": "Enerji yoktan var olmaz",
            "D": "Cisimler eylemsizdir yalnızca",
            "E": "Basınç derinlikle artmaz",
        },
        "correct": "B",
        "explanation": "II. yasa: net kuvvet kütle çarpı ivmedir (F = ma).",
        "subject_type": "sayisal",
        "is_yks_fen_question": True,
        "fen_branch": "fizik",
        "misconception_tag": "Kavram Yanılgısı",
    },
    {
        "topic": "Kimya",
        "question_text": "Suyun kimyasal formülü hangisidir?",
        "options": {"A": "CO2", "B": "H2O", "C": "NaCl", "D": "O2", "E": "CH4"},
        "correct": "B",
        "explanation": "Su iki hidrojen bir oksijendir: H2O.",
        "subject_type": "sayisal",
        "is_yks_fen_question": True,
        "fen_branch": "kimya",
        "misconception_tag": "Kavram Yanılgısı",
    },
    {
        "topic": "Biyoloji",
        "question_text": "Hücrenin genetik materyali esas olarak nerede bulunur?",
        "options": {
            "A": "Mitokondri zarı",
            "B": "Golgi aygıtı",
            "C": "Çekirdek",
            "D": "Lizozom",
            "E": "Koful",
        },
        "correct": "C",
        "explanation": "DNA esas olarak çekirdektedir (mitokondride de az bulunur).",
        "subject_type": "sayisal",
        "is_yks_fen_question": True,
        "fen_branch": "biyoloji",
        "misconception_tag": "Kavram Yanılgısı",
    },
    {
        "topic": "Fen",
        "question_text": "Fotosentezde bitki hangisini üretir?",
        "options": {
            "A": "Yalnız karbondioksit",
            "B": "Yalnız azot",
            "C": "Glikoz ve oksijen",
            "D": "Yalnız su",
            "E": "Amonyak",
        },
        "correct": "C",
        "explanation": "Fotosentez: CO2 + su → glikoz + O2.",
        "subject_type": "sayisal",
        "is_yks_fen_question": True,
        "fen_branch": "biyoloji",
        "misconception_tag": "Kavram Yanılgısı",
    },
    {
        "topic": "İnkılap",
        "question_text": "Harf İnkılabı hangi yılda yapılmıştır?",
        "options": {"A": "1923", "B": "1924", "C": "1926", "D": "1928", "E": "1934"},
        "correct": "D",
        "explanation": "Yeni Türk harfleri 1928’de kabul edildi.",
    },
    {
        "topic": "Alan bilgisi",
        "question_text": "Bloom taksonomisinde en üst basamak hangisidir?",
        "options": {
            "A": "Bilgi",
            "B": "Kavrama",
            "C": "Uygulama",
            "D": "Analiz",
            "E": "Değerlendirme / yaratma",
        },
        "correct": "E",
        "explanation": "Güncel Bloom’da zirve yaratma/değerlendirmedir.",
    },
    {
        "topic": "Ölçme-değerlendirme",
        "question_text": "Bir testin aynı koşullarda benzer sonuç vermesi hangi kavramdır?",
        "options": {
            "A": "Geçerlik",
            "B": "Güvenirlik",
            "C": "Kullanışlılık",
            "D": "Ayırt edicilik",
            "E": "Madde güçlüğü",
        },
        "correct": "B",
        "explanation": "Güvenirlik tutarlılıktır; geçerlik amaca uygunluktur.",
    },
    {
        "topic": "Öğrenme kuramı",
        "question_text": "Klasik koşullanmayı kim ortaya koymuştur?",
        "options": {
            "A": "Skinner",
            "B": "Pavlov",
            "C": "Bandura",
            "D": "Piaget",
            "E": "Bruner",
        },
        "correct": "B",
        "explanation": "Pavlov klasik, Skinner edimsel koşullanmadır.",
    },
    {
        "topic": "Genel kültür",
        "question_text": "Türkiye’nin başkenti hangisidir?",
        "options": {
            "A": "İstanbul",
            "B": "İzmir",
            "C": "Ankara",
            "D": "Bursa",
            "E": "Konya",
        },
        "correct": "C",
        "explanation": "Başkent 13 Ekim 1923’ten beri Ankara’dır.",
    },
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _loads(raw: str, fallback):
    try:
        return json.loads(raw or "")
    except json.JSONDecodeError:
        return fallback


def _clamp_count(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 10
    return max(MIN_COUNT, min(MAX_COUNT, value))


def _pick_subjects(exam_target: str, wanted: list[str] | None) -> list[str]:
    catalog = subjects_for(exam_target)
    cleaned = []
    seen: set[str] = set()
    for item in wanted or []:
        name = str(item or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        match = next((row for row in catalog if row.casefold() == key), name)
        cleaned.append(match)
    return cleaned or list(catalog)


def _letter(value: str | None) -> str:
    return (value or "").strip().upper()[:1]


def _options(raw) -> dict[str, str]:
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        letters = "ABCDE"
        pairs = [(letters[i], item) for i, item in enumerate(raw[:5])]
    else:
        pairs = []
    out: dict[str, str] = {}
    for key, value in pairs:
        letter = _letter(str(key))
        if letter in "ABCDE" and str(value or "").strip():
            out[letter] = str(value).strip()
    return out


def _qid(exam_id: int, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{exam_id}:{index}:{text}".encode("utf-8")).hexdigest()[:10]
    return f"dx_{exam_id}_{index}_{digest}"


def public_question(item: dict) -> dict:
    return {
        "id": item.get("id") or "",
        "topic": item.get("topic") or "",
        "question_text": item.get("question_text") or item.get("text") or "",
        "options": item.get("options") or {},
        "difficulty": item.get("difficulty") or "orta",
        "subject_type": item.get("subject_type") or "sozel",
        "is_yks_fen_question": bool(item.get("is_yks_fen_question")),
        "fen_branch": item.get("fen_branch") or "",
        "premises": [
            {
                "id": str(row.get("id") or ""),
                "text": str(row.get("text") or ""),
                "is_correct": False,
                "why": "",
            }
            for row in item.get("premises") or []
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ],
    }


def remaining_seconds(row: DynamicExam, now: datetime | None = None) -> int:
    stamp = now or _utcnow()
    start = row.started_at or row.created_at or stamp
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    elapsed = int((stamp - start).total_seconds())
    return max(0, int(row.duration_seconds or 0) - elapsed)


def catalog(db: Session, user_id: str, exam_target: str | None = None) -> dict:
    from app.services.penalty import get_or_create_user

    get_or_create_user(db, user_id)
    target = exam_of(db, user_id)
    pack = catalog_for(target)
    pack["user_id"] = user_id
    return pack


def _trap_digest(db: Session, user_id: str, limit: int = 12) -> list[dict]:
    from app.services import diagnostic as diagnostic_service
    from app.services import traps as trap_service

    weak = []
    baseline = db.get(UserBaseline, user_id)
    if baseline:
        weak = _loads(baseline.weak_topics, [])
    if not weak:
        weak = diagnostic_service.status(db, user_id).get("weak_topics") or []
    rows = trap_service.prioritize_weak(trap_service.all_traps(db, user_id), weak)
    digest = []
    for row in rows[:limit]:
        digest.append(
            {
                "topic": row.topic or "",
                "question_text": (row.question_text or "")[:280],
                "explanation": (row.explanation or row.teacher_note or "")[:220],
                "chosen": row.chosen or "",
                "correct": row.correct or "",
                "misconception_tag": row.misconception_tag or "",
            }
        )
    return digest


def _build_notes(db: Session, exam_target: str, subjects: list[str], traps: list[dict]) -> list[dict]:
    from app.services import rag as rag_service

    notes: list[dict] = []
    query = " ".join(subjects)
    pack = rag_service.retrieve(db, exam_target=exam_target, query=query, limit=8)
    guide = pack.get("style") or {}
    for trap in traps:
        notes.append(
            {
                "title": trap.get("topic") or "Tuzak",
                "text": (
                    f"Öğrenci bu tuzakta düştü: {trap.get('question_text')}. "
                    f"Doğru {trap.get('correct')}, seçilen {trap.get('chosen')}. "
                    f"{trap.get('explanation')}"
                ),
                "key_points": [trap.get("topic") or "", trap.get("misconception_tag") or ""],
                "mnemonic": "",
                "exam_tip": "Aynı çeldiriciyi yeni bir kökte tekrar sor.",
                "timestamp": 0,
            }
        )
    for chunk in pack.get("archive") or []:
        notes.append(
            {
                "title": chunk.get("topic") or "ÖSYM arşivi",
                "text": str(chunk.get("body") or "")[:700],
                "key_points": [str(chunk.get("topic") or "")],
                "mnemonic": "",
                "exam_tip": "Arşivdeki kök ve çeldirici DNA’sını taklit et.",
                "timestamp": 0,
            }
        )
    for item in pack.get("hoca_highlights") or []:
        notes.append(
            {
                "title": item.get("topic") or "Hoca vurgusu",
                "text": f"[{item.get('cue')}] {item.get('snippet')}",
                "key_points": [item.get("topic") or ""],
                "mnemonic": "",
                "exam_tip": "Banko gelen bu konuyu soruya çevir.",
                "timestamp": int(item.get("timestamp") or 0),
            }
        )
    if not notes:
        traps_txt = "\n".join(f"- {item}" for item in (guide.get("traps") or [])[:6])
        notes.append(
            {
                "title": ", ".join(subjects) or label_for(exam_target),
                "text": (
                    f"{prompt_block(exam_target)}\n"
                    f"Dersler: {', '.join(subjects)}.\n"
                    f"Kök kalıpları: {' | '.join((guide.get('stems') or [])[:6])}\n"
                    f"Tuzaklar:\n{traps_txt or '- yakın kavram çeldiricisi'}"
                ),
                "key_points": list(subjects),
                "mnemonic": "",
                "exam_tip": "ÖSYM üslubunda, 5 şık, tek doğru.",
                "timestamp": 0,
            }
        )
    return notes


def _normalize_item(raw: dict, *, exam_target: str, fallback_topic: str) -> dict | None:
    text = str(raw.get("question_text") or raw.get("text") or "").strip()
    options = _options(raw.get("options"))
    correct = _letter(str(raw.get("correct") or raw.get("correct_answer") or ""))
    if not text or len(options) < 5 or correct not in options:
        return None
    topic = str(raw.get("topic") or fallback_topic or "").strip() or fallback_topic
    meta = classify(
        subject=topic,
        subject_type=raw.get("subject_type"),
        exam_target=exam_target,
        is_yks_fen_question=raw.get("is_yks_fen_question") or raw.get("is_yks_fen"),
    )
    return {
        "topic": topic,
        "question_text": text,
        "options": options,
        "correct": correct,
        "explanation": str(raw.get("explanation") or "").strip(),
        "trap_explanation": str(
            raw.get("trap_explanation") or raw.get("explanation") or ""
        ).strip(),
        "difficulty": str(raw.get("difficulty") or "orta").strip().lower() or "orta",
        "subject_type": meta["subject_type"],
        "is_yks_fen_question": bool(meta["is_yks_fen_question"]),
        "fen_branch": str(raw.get("fen_branch") or meta["fen_branch"] or ""),
        "misconception_tag": str(raw.get("misconception_tag") or meta["misconception_tag"] or ""),
        "step_by_step_solution": parse_steps(raw.get("step_by_step_solution")),
        "shortcut_tactic": str(raw.get("shortcut_tactic") or "").strip(),
        "premises": parse_premises(raw.get("premises")),
        "source": str(raw.get("source") or "llm"),
    }


def _llm_batch(
    *,
    exam_target: str,
    subjects: list[str],
    count: int,
    traps: list[dict],
    rag_block: str,
    notes_block: str,
    avoid: list[str],
) -> list[dict]:
    from app.services.llm import complete_json

    title_block = prompt_block(exam_target)
    trap_lines = "\n".join(
        f"- [{item.get('topic')}] {item.get('question_text')[:160]} "
        f"(doğru {item.get('correct')}, düşülen {item.get('chosen')})"
        for item in traps[:8]
    ) or "- tuzak kaydı yok; zayıf konulara ağırlık ver"
    avoid_block = "\n".join(f"- {text[:140]}" for text in avoid[:12]) or "- yok"
    prompt = f"""{title_block}

{rag_block}

Kaynak notları (ÖSYM arşivi + hoca vurgusu + tuzaklar):
{notes_block or "- stil rehberine uy"}

Görev: {count} adet yepyeni çoktan seçmeli deneme sorusu üret.
Dersler (yalnızca bunlar): {", ".join(subjects)}
Tuzak Defteri (öğrencinin düştüğü yerler — aynı hatayı yeni kökte ölç, soruyu kopyalama):
{trap_lines}

Kaçınılacak kökler:
{avoid_block}

Kurallar:
- 5 şık A-E, tek doğru.
- ÖSYM kökü: hangisi doğrudur / hangisi yanlıştır / hangisi değildir.
- Tuzak defterindeki kavramlara soruların en az üçte birini ayır.
- Sayısal derslerde step_by_step_solution (3-6 adım) ve shortcut_tactic doldur.
- YKS fen ise I-II-III öncül + premises dizisi.
- Aynı bilgiyi iki kez sorma.

JSON:
{{
  "questions": [
    {{
      "topic": "Tarih",
      "question_text": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "correct": "A",
      "explanation": "...",
      "trap_explanation": "...",
      "difficulty": "orta",
      "subject_type": "sozel",
      "is_yks_fen_question": false,
      "fen_branch": "",
      "misconception_tag": "",
      "step_by_step_solution": [],
      "shortcut_tactic": "",
      "premises": []
    }}
  ]
}}
"""
    system = (
        "Sen TİLKO'nun ÖSYM DNA'sını taklit eden soru yazarısın. "
        "Çıktı SADECE geçerli JSON. Markdown yok. Türkçe yaz."
    )
    data = complete_json(system, prompt, temperature=0.55, task="dynamic-exam")
    out = []
    for raw in data.get("questions") or []:
        item = _normalize_item(raw, exam_target=exam_target, fallback_topic=subjects[0])
        if item:
            out.append(item)
    return out


def _llm_questions(
    db: Session,
    *,
    exam_target: str,
    subjects: list[str],
    count: int,
    traps: list[dict],
) -> list[dict]:
    from app.services import rag as rag_service

    rag_block = rag_service.prompt_block_rag(db, exam_target, " ".join(subjects))
    notes = _build_notes(db, exam_target, subjects, traps)
    notes_block = "\n".join(
        f"- {item.get('title')}: {str(item.get('text') or '')[:280]}"
        for item in notes[:10]
    )
    collected: list[dict] = []
    seen: set[str] = set()

    def take(raw_list: list[dict], source: str) -> None:
        for raw in raw_list:
            if len(collected) >= count:
                return
            item = _normalize_item(
                {**raw, "source": source},
                exam_target=exam_target,
                fallback_topic=subjects[0],
            )
            if not item:
                continue
            key = hashlib.sha1(item["question_text"].encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)

    while len(collected) < count:
        missing = min(LLM_BATCH, count - len(collected))
        try:
            batch = _llm_batch(
                exam_target=exam_target,
                subjects=subjects,
                count=missing,
                traps=traps,
                rag_block=rag_block,
                notes_block=notes_block,
                avoid=[item["question_text"] for item in collected],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dinamik deneme LLM tamamlama düştü: %s", exc)
            break
        before = len(collected)
        take(batch, "osym-dna")
        if len(collected) == before:
            break
    return collected


def _fallback_questions(
    subjects: list[str], count: int, salt: str, exam_target: str
) -> list[dict]:
    from app.services.diagnostic import bank_for
    from app.services.exams import matches_exam

    wanted = {name.casefold() for name in subjects}
    isolated = [item for item in bank_for(exam_target)]
    if not isolated:
        isolated = [
            item for item in FALLBACK_BANK if matches_exam(item, exam_target)
        ]
    pool = [
        item
        for item in isolated
        if not wanted or (item.get("topic") or "").casefold() in wanted
    ]
    if not pool:
        pool = isolated
    ranked = sorted(
        pool,
        key=lambda item: hashlib.sha1(
            f"{salt}:{item.get('question_text') or item.get('id')}".encode("utf-8")
        ).hexdigest(),
    )
    out = []
    for raw in ranked:
        packed = {
            "topic": raw.get("topic") or "",
            "question_text": raw.get("question_text") or raw.get("text") or "",
            "options": raw.get("options") or {},
            "correct": raw.get("correct") or raw.get("correct_answer") or "",
            "explanation": raw.get("explanation") or raw.get("trap_explanation") or "",
            "source": "bank",
        }
        item = _normalize_item(
            packed,
            exam_target=exam_target,
            fallback_topic=subjects[0] if subjects else "Genel",
        )
        if item:
            out.append(item)
        if len(out) >= count:
            break
    while len(out) < count and out:
        clone = dict(out[len(out) % len(out)])
        out.append(clone)
    return out[:count]


def generate(
    db: Session,
    *,
    user_id: str,
    exam_target: str | None = None,
    subjects: list[str] | None = None,
    question_count: int = 10,
) -> dict:
    from app.services.penalty import get_or_create_user

    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    get_or_create_user(db, uid)
    target = exam_of(db, uid)
    picked = _pick_subjects(target, subjects)
    count = _clamp_count(question_count)
    traps = _trap_digest(db, uid)
    questions = _llm_questions(
        db, exam_target=target, subjects=picked, count=count, traps=traps
    )
    if len(questions) < count:
        pad = _fallback_questions(
            picked, count - len(questions), f"{uid}:{target}", target
        )
        seen = {item["question_text"] for item in questions}
        for item in pad:
            if item["question_text"] in seen:
                continue
            questions.append(item)
            if len(questions) >= count:
                break
    questions = questions[:count]
    if not questions:
        raise RuntimeError("Deneme sorusu üretilemedi. Biraz sonra yeniden dene.")

    now = _utcnow()
    duration = count * SECONDS_PER_QUESTION
    row = DynamicExam(
        user_id=uid,
        exam_target=target,
        subjects_json=json.dumps(picked, ensure_ascii=False),
        question_count=len(questions),
        duration_seconds=duration,
        questions_json="[]",
        status="pending",
        started_at=now,
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    stored = []
    for index, item in enumerate(questions, start=1):
        packed = dict(item)
        packed["id"] = _qid(row.id, index, item["question_text"])
        stored.append(packed)
    row.questions_json = json.dumps(stored, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return _public_exam(row)


def _public_exam(row: DynamicExam) -> dict:
    questions = _loads(row.questions_json, [])
    return {
        "exam_id": row.id,
        "status": row.status,
        "exam_target": row.exam_target,
        "exam_label": label_for(row.exam_target),
        "subjects": _loads(row.subjects_json, []),
        "question_count": row.question_count,
        "duration_seconds": row.duration_seconds,
        "remaining_seconds": remaining_seconds(row) if row.status == "pending" else 0,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "questions": [public_question(item) for item in questions],
        "trap_blend": True,
        "osym_dna": True,
        "report": _loads(row.report_json, None) if row.status == "submitted" else None,
    }


def get_exam(db: Session, user_id: str, exam_id: int) -> dict:
    row = db.get(DynamicExam, exam_id)
    if row is None or row.user_id != user_id:
        raise KeyError("Deneme bulunamadı.")
    return _public_exam(row)


def _grade(questions: list[dict], answers: list[dict]) -> dict:
    chosen_map = {
        str(item.get("question_id") or item.get("id") or ""): _letter(
            str(item.get("chosen") or "")
        )
        for item in answers
    }
    rows = []
    topic_hits: dict[str, list[bool]] = {}
    for item in questions:
        qid = str(item.get("id") or "")
        chosen = chosen_map.get(qid, "")
        correct = _letter(str(item.get("correct") or ""))
        ok = bool(chosen) and chosen == correct
        topic = str(item.get("topic") or "Genel")
        topic_hits.setdefault(topic, []).append(ok)
        rows.append(
            {
                "question_id": qid,
                "topic": topic,
                "question_text": item.get("question_text") or "",
                "options": item.get("options") or {},
                "chosen": chosen,
                "correct": correct,
                "is_correct": ok,
                "explanation": item.get("explanation") or "",
                "trap_explanation": item.get("trap_explanation") or "",
                "subject_type": item.get("subject_type") or "sozel",
                "is_yks_fen_question": bool(item.get("is_yks_fen_question")),
                "fen_branch": item.get("fen_branch") or "",
                "misconception_tag": item.get("misconception_tag") or "",
                "step_by_step_solution": item.get("step_by_step_solution") or [],
                "shortcut_tactic": item.get("shortcut_tactic") or "",
                "premises": item.get("premises") or [],
            }
        )
    total = len(rows) or 1
    right = sum(1 for row in rows if row["is_correct"])
    score = round(100.0 * right / total, 1)
    breakdown = {}
    weak = []
    strong = []
    for topic, hits in topic_hits.items():
        ratio = sum(hits) / max(len(hits), 1)
        breakdown[topic] = {
            "correct": sum(hits),
            "total": len(hits),
            "ratio": round(ratio, 2),
        }
        if ratio < 0.67:
            weak.append(topic)
        elif ratio >= 0.8:
            strong.append(topic)
    if not weak and breakdown:
        weakest = min(breakdown.items(), key=lambda pair: pair[1]["ratio"])
        if weakest[1]["ratio"] < 1:
            weak = [weakest[0]]
    return {
        "reviews": rows,
        "score": score,
        "correct_count": right,
        "total": len(rows),
        "weak_topics": weak,
        "strong_topics": strong,
        "topic_breakdown": breakdown,
    }


def _fallback_report(graded: dict, title: str, traps: list[dict], cheated: bool) -> dict:
    weak = graded["weak_topics"]
    strong = graded["strong_topics"]
    trap_topics = [item.get("topic") for item in traps if item.get("topic")]
    hit = [topic for topic in trap_topics if topic in weak]
    cheat_line = (
        " Süre çok kısaydı; karnenin bir kısmı tempo şüphesi taşıyor." if cheated else ""
    )
    if graded["score"] >= 80:
        summary = (
            f"Güzel tempo {title}. {graded['correct_count']}/{graded['total']} isabet. "
            f"{', '.join(strong) or 'Genel'} tarafın oturuyor; "
            f"{', '.join(weak) or 'küçük kaçaklar'} hâlâ ÖSYM’nin sevdiği kaydırma."
        )
    elif graded["score"] >= 50:
        summary = (
            f"Hey {title}, deneme orta bantta ({graded['score']:.0f}). "
            f"Kale: {', '.join(strong) or 'henüz net değil'}. "
            f"Açık: {', '.join(weak) or 'dağınık hatalar'}. Tuzak Defteri buradan beslenecek."
        )
    else:
        summary = (
            f"{title}, bu set seni dürüstçe tarttı ({graded['score']:.0f}). "
            f"{', '.join(weak) or 'Temel kavramlar'} tuzaklarında sazan oldun. "
            f"Panik yok — aynı DNA’yı deftere alıp tekrar avlarız."
        )
    prescription = (
        f"{', '.join(weak[:3]) or 'Zayıf konular'} için 2 pomodoro + Tuzak Defteri tekrarı. "
        "Yanlışların çeldiricisini ezberleme; neden doğru sandığını yaz."
    )
    return {
        "coach_summary": summary + cheat_line,
        "weakness_analysis": (
            f"Zayıf bant: {', '.join(weak) or 'yok'}. "
            f"Tuzak Defteri yankısı: {', '.join(hit) or 'bu sette eski tuzak tekrar etmedi'}."
        ),
        "prescription": prescription,
        "weak_topics": weak,
        "strong_topics": strong,
        "traps_hit": hit,
        "net_range": _net_range(graded["score"]),
    }


def _net_range(score: float) -> str:
    if score >= 85:
        return "85-95"
    if score >= 70:
        return "75-85"
    if score >= 55:
        return "65-80"
    if score >= 40:
        return "55-70"
    return "40-55"


def _llm_report(
    graded: dict,
    *,
    title: str,
    exam_target: str,
    traps: list[dict],
    cheated: bool,
) -> dict:
    from app.services.llm import complete_json

    local = _fallback_report(graded, title, traps, cheated)
    prompt = f"""Öğrencinin dinamik deneme karnesi (hedef: {label_for(exam_target)}):
hitap: yalnızca '{title}'
skor: {graded['score']}
doğru: {graded['correct_count']}/{graded['total']}
kırılım: {json.dumps(graded['topic_breakdown'], ensure_ascii=False)}
zayıf: {graded['weak_topics']}
güçlü: {graded['strong_topics']}
tuzak defteri konuları: {[item.get('topic') for item in traps]}
süre şüphesi: {cheated}

Koç üslubu: cam gibi net, biraz sataşkan, küçümseme yok. Türkçe.
3-5 cümle coach_summary, 2-3 cümle weakness_analysis, 1-2 cümle prescription.

JSON:
{{
  "coach_summary": "...",
  "weakness_analysis": "...",
  "prescription": "...",
  "weak_topics": ["Coğrafya"],
  "strong_topics": ["Tarih"],
  "traps_hit": ["Vatandaşlık"],
  "net_range": "65-80"
}}
"""
    system = (
        f"Sen TİLKO'nun kurnaz sınav koçusun. Öğrenciye yalnızca '{title}' de. "
        f"{prompt_block(exam_target)} Çıktı SADECE geçerli JSON."
    )
    try:
        data = complete_json(system, prompt, temperature=0.5, task="dynamic-report")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deneme karnesi LLM düştü: %s", exc)
        return local
    summary = str(data.get("coach_summary") or "").strip()
    if not summary:
        return local
    weak = data.get("weak_topics") or graded["weak_topics"]
    strong = data.get("strong_topics") or graded["strong_topics"]
    return {
        "coach_summary": summary,
        "weakness_analysis": str(data.get("weakness_analysis") or local["weakness_analysis"]),
        "prescription": str(data.get("prescription") or local["prescription"]),
        "weak_topics": [str(item) for item in weak],
        "strong_topics": [str(item) for item in strong],
        "traps_hit": [str(item) for item in (data.get("traps_hit") or local["traps_hit"])],
        "net_range": str(data.get("net_range") or local["net_range"]),
    }


def _save_traps(db: Session, user_id: str, reviews: list[dict], spent: int) -> int:
    from app.services import traps as trap_service

    per = max(int(spent / max(len(reviews), 1)), 0)
    saved = 0
    for item in reviews:
        if item.get("is_correct") or saved >= MAX_TRAP_SAVES:
            continue
        payload = SimpleNamespace(
            user_id=user_id,
            question_id=item.get("question_id") or "",
            question_text=item.get("question_text") or "",
            options=item.get("options") or {},
            correct=item.get("correct") or "",
            chosen=item.get("chosen") or "",
            explanation=item.get("explanation") or "",
            trap_explanation=item.get("trap_explanation") or "",
            topic=item.get("topic") or "",
            time_spent_seconds=per,
            subject_type=item.get("subject_type"),
            is_yks_fen_question=item.get("is_yks_fen_question"),
            fen_branch=item.get("fen_branch") or "",
            misconception_tag=item.get("misconception_tag") or "",
            step_by_step_solution=item.get("step_by_step_solution") or [],
            shortcut_tactic=item.get("shortcut_tactic") or "",
            premises=item.get("premises") or [],
            teacher_persona=None,
        )
        try:
            trap_service.save_wrong_trap(db, payload)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deneme tuzağı yazılamadı: %s", exc)
    return saved


def submit(
    db: Session,
    *,
    user_id: str,
    exam_id: int,
    answers: list[dict],
    time_spent_seconds: int | None = None,
) -> dict:
    from app.services import diagnostic as diagnostic_service
    from app.services import gamification

    uid = (user_id or "").strip()
    row = db.get(DynamicExam, exam_id)
    if row is None or row.user_id != uid:
        raise KeyError("Deneme bulunamadı.")
    if row.status == "submitted" and row.report_json:
        report = _loads(row.report_json, {})
        report["already"] = True
        return report

    questions = _loads(row.questions_json, [])
    graded = _grade(questions, answers)
    now = _utcnow()
    start = row.started_at or row.created_at or now
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    elapsed = int((now - start).total_seconds())
    if time_spent_seconds is not None:
        try:
            elapsed = max(elapsed, int(time_spent_seconds))
        except (TypeError, ValueError):
            pass
    cheated = elapsed < max(FAST_SECONDS_PER_Q * max(graded["total"], 1), 8)
    traps = _trap_digest(db, uid)
    title = address_for(db, uid)
    analysis = _llm_report(
        graded, title=title, exam_target=row.exam_target, traps=traps, cheated=cheated
    )
    traps_saved = _save_traps(db, uid, graded["reviews"], elapsed)
    xp = gamification.award_dynamic_exam(
        db, uid, correct_count=graded["correct_count"], already=False
    )
    videos = diagnostic_service.recommended_videos(analysis["weak_topics"])
    report = {
        "exam_id": row.id,
        "already": False,
        "score": graded["score"],
        "correct_count": graded["correct_count"],
        "total": graded["total"],
        "weak_topics": analysis["weak_topics"],
        "strong_topics": analysis["strong_topics"],
        "topic_breakdown": graded["topic_breakdown"],
        "net_range": analysis["net_range"],
        "coach_summary": analysis["coach_summary"],
        "weakness_analysis": analysis["weakness_analysis"],
        "prescription": analysis["prescription"],
        "traps_hit": analysis["traps_hit"],
        "reviews": graded["reviews"],
        "recommended_videos": videos,
        "is_cheated": cheated,
        "traps_saved": traps_saved,
        "time_spent_seconds": elapsed,
        "exam_target": row.exam_target,
        "exam_label": label_for(row.exam_target),
        "subjects": _loads(row.subjects_json, []),
        **xp,
    }
    row.answers_json = json.dumps(answers, ensure_ascii=False)
    row.report_json = json.dumps(report, ensure_ascii=False)
    row.status = "submitted"
    row.score = graded["score"]
    row.correct_count = graded["correct_count"]
    row.is_cheated = cheated
    row.finished_at = now
    db.commit()
    return report
