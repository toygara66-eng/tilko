"""Ham LLM kayıtlarını LoRA eğitimi için sohbet biçimli veri setine çevirir.

Kullanım:
    python build_dataset.py
    python build_dataset.py --min-notes 4 --val-ratio 0.1

Girdi : training/data/raw/*.jsonl   (uygulama CAPTURE_TRAINING_DATA=true iken üretir)
        training/data/manual/*.jsonl (elle hazırlanan örnekler, aynı biçim)
Çıktı : training/data/train.jsonl, training/data/val.jsonl
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RAW_DIRS = [DATA_DIR / "raw", DATA_DIR / "manual"]
TRAIN_PATH = DATA_DIR / "train.jsonl"
VAL_PATH = DATA_DIR / "val.jsonl"

OPTION_KEYS = ("A", "B", "C", "D", "E")


def iter_raw_rows() -> list[dict]:
    rows: list[dict] = []
    for directory in RAW_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  atlandi (bozuk satir): {path.name}:{line_no}")
    return rows


def valid_notes(payload: dict, min_notes: int) -> bool:
    notes = payload.get("notes")
    if not isinstance(notes, list) or len(notes) < min_notes:
        return False
    for note in notes:
        if not isinstance(note, dict):
            return False
        if not str(note.get("title") or "").strip():
            return False
        if len(str(note.get("detail") or "")) < 80:
            return False
        if not str(note.get("mnemonic") or "").strip():
            return False
        if note.get("timestamp") is None:
            return False
    return True


def valid_questions(payload: dict, min_questions: int) -> bool:
    questions = payload.get("questions")
    if not isinstance(questions, list) or len(questions) < min_questions:
        return False
    for question in questions:
        if not isinstance(question, dict):
            return False
        options = question.get("options")
        if not isinstance(options, dict):
            return False
        keys = {str(k).strip().upper() for k in options}
        if not set(OPTION_KEYS).issubset(keys):
            return False
        if any(not str(v).strip() for v in options.values()):
            return False
        correct = str(question.get("correct") or "").strip().upper()[:1]
        if correct not in OPTION_KEYS:
            return False
        if len(str(question.get("text") or "")) < 20:
            return False
        if not str(question.get("explanation") or "").strip():
            return False
    return True


def is_useful(row: dict, min_notes: int, min_questions: int) -> bool:
    """Zayıf örnek öğretmez, zarar verir: eksik alanlı yanıtları eleriz."""
    try:
        payload = json.loads(row["assistant"])
    except (KeyError, json.JSONDecodeError):
        return False
    if row.get("task") == "notes":
        return valid_notes(payload, min_notes)
    if row.get("task") == "questions":
        return valid_questions(payload, min_questions)
    return False


def to_chat(row: dict) -> dict:
    """Eğitim biçimi, uygulamanın çalışma anındaki istem biçimiyle birebir aynı olmalı."""
    return {
        "task": row.get("task", "genel"),
        "messages": [
            {"role": "system", "content": row["system"]},
            {"role": "user", "content": row["user"]},
            {"role": "assistant", "content": row["assistant"]},
        ],
    }


def fingerprint(row: dict) -> str:
    return hashlib.sha1(
        (row.get("user", "") + row.get("assistant", "")).encode("utf-8")
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-notes", type=int, default=3)
    parser.add_argument("--min-questions", type=int, default=3)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = iter_raw_rows()
    print(f"ham kayit: {len(rows)}")
    if not rows:
        print(
            "Kayit yok. backend/.env icinde CAPTURE_TRAINING_DATA=true yapip "
            "guclu bir saglayici ile video analiz edin."
        )
        return

    seen: set[str] = set()
    kept: list[dict] = []
    for row in rows:
        key = fingerprint(row)
        if key in seen:
            continue
        seen.add(key)
        if not is_useful(row, args.min_notes, args.min_questions):
            continue
        kept.append(to_chat(row))

    print(f"tekil ve kaliteli kayit: {len(kept)}")
    by_task: dict[str, int] = {}
    for row in kept:
        by_task[row["task"]] = by_task.get(row["task"], 0) + 1
    for task, count in sorted(by_task.items()):
        print(f"  {task}: {count}")

    if len(kept) < 20:
        print(
            "\nUYARI: 20'den az ornek var. Ince ayar icin en az birkac yuz ornek "
            "toplamak gerekir; daha fazla video analiz edin."
        )

    random.Random(args.seed).shuffle(kept)
    split = max(1, int(len(kept) * args.val_ratio)) if len(kept) > 10 else 0
    val, train = kept[:split], kept[split:]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path, items in ((TRAIN_PATH, train), (VAL_PATH, val)):
        with path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"yazildi: {path.name} ({len(items)} ornek)")


if __name__ == "__main__":
    main()
