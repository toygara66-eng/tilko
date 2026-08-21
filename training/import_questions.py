"""Elde hazır bulunan KPSS sorularını eğitim kaydına çevirir.

Damıtma verisi modele "büyük modeli taklit et" der. Gerçek ÖSYM soruları ise
"sınavın gerçek üslubunu öğren" der. İkisini karıştırmak en iyi sonucu verir.

Girdi biçimi (CSV veya JSON):
    soru, a, b, c, d, e, dogru, aciklama, konu, zorluk

Kullanım:
    python import_questions.py sorular.csv --subject "Anayasa"
    python import_questions.py sorular.json --subject "Tarih" --batch 5
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.prompts.kpss import QUESTIONS_SYSTEM_PROMPT, build_questions_prompt  # noqa: E402

OUT_DIR = Path(__file__).parent / "data" / "manual"
FIELDS = ("soru", "a", "b", "c", "d", "e", "dogru")


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalise(row: dict) -> dict | None:
    missing = [f for f in FIELDS if not str(row.get(f, "")).strip()]
    if missing:
        print(f"  atlandi (eksik alan: {', '.join(missing)}): {str(row.get('soru'))[:50]}")
        return None
    return {
        "text": str(row["soru"]).strip(),
        "options": {
            "A": str(row["a"]).strip(),
            "B": str(row["b"]).strip(),
            "C": str(row["c"]).strip(),
            "D": str(row["d"]).strip(),
            "E": str(row["e"]).strip(),
        },
        "correct": str(row["dogru"]).strip().upper()[:1],
        "explanation": str(row.get("aciklama") or "").strip()
        or "Bu sorunun cevabı ilgili konu anlatımında açıkça belirtilmiştir.",
        "topic": str(row.get("konu") or "").strip(),
        "difficulty": str(row.get("zorluk") or "orta").strip().lower(),
        "timestamp": 0,
    }


def notes_block_from(questions: list[dict]) -> str:
    """Sorulardan geriye doğru bir 'not' bağlamı kurar; eğitimde girdi tarafını temsil eder."""
    rows = []
    for q in questions:
        correct_text = q["options"].get(q["correct"], "")
        rows.append(f"[0] {q['topic'] or 'Konu'} — {correct_text}. {q['explanation']}")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--subject", default=None)
    parser.add_argument("--batch", type=int, default=5, help="Bir örnekteki soru sayısı")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Dosya bulunamadi: {args.path}")
        return

    questions = [q for q in (normalise(r) for r in read_rows(args.path)) if q]
    print(f"gecerli soru: {len(questions)}")
    if not questions:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"import-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.jsonl"

    written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for start in range(0, len(questions), args.batch):
            batch = questions[start : start + args.batch]
            row = {
                "task": "questions",
                "provider": "manual",
                "model": "osym-gercek-soru",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "system": QUESTIONS_SYSTEM_PROMPT,
                "user": build_questions_prompt(
                    notes_block_from(batch), args.subject, len(batch)
                ),
                "assistant": json.dumps({"questions": batch}, ensure_ascii=False),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    print(f"yazildi: {out_path.name} ({written} egitim ornegi)")
    print("Sonraki adim: python build_dataset.py")


if __name__ == "__main__":
    main()
