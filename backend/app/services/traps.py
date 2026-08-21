import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import TrapNotebook

TIME_TRAP_LIMIT = 60
TIME_TRAP_WARNING = (
    "Dikkat! Bilgiden değil, süreden kaybediyorsun. "
    "ÖSYM seni 60 saniyeden fazla oyaladı."
)
# Yanlış: +24 saat. Doğru tekrar: 3 gün, sonra 7, sonra 15.
CORRECT_GAPS_DAYS = (3, 7, 15)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def schedule_after_wrong(now: datetime | None = None) -> tuple[datetime, int]:
    stamp = now or _utcnow()
    return stamp + timedelta(hours=24), 0


def schedule_after_correct(
    review_count: int, now: datetime | None = None
) -> tuple[datetime, int]:
    stamp = now or _utcnow()
    index = min(max(review_count, 0), len(CORRECT_GAPS_DAYS) - 1)
    days = CORRECT_GAPS_DAYS[index]
    return stamp + timedelta(days=days), min(review_count + 1, len(CORRECT_GAPS_DAYS))


def _analysis(chosen: str, correct: str, explanation: str) -> str:
    bits = [
        f"Seçilen çeldirici: {chosen or '?'}.",
        f"Doğru şık: {correct or '?'}.",
    ]
    if explanation:
        bits.append(explanation.strip())
    return " ".join(bits)


def _teacher_note(payload, exam_target: str | None = None) -> str:
    from app.services.ai_engine import style_trap_explanation

    seed = (getattr(payload, "trap_explanation", "") or payload.explanation or "").strip()
    persona = getattr(payload, "teacher_persona", None)
    if persona is None:
        return seed
    return style_trap_explanation(
        persona=persona,
        question_text=payload.question_text,
        chosen=payload.chosen or "",
        correct=payload.correct or "",
        explanation=payload.explanation or "",
        trap_explanation=seed,
        exam_target=exam_target or getattr(payload, "exam_target", None),
    )


def save_wrong_trap(db: Session, payload) -> TrapNotebook:
    from app.services.exams import exam_of
    from app.services.subjects import classify, parse_premises, parse_steps

    now = _utcnow()
    next_date, review_count = schedule_after_wrong(now)
    spent = int(payload.time_spent_seconds or 0)
    time_trap = spent >= TIME_TRAP_LIMIT
    options = payload.options or {}
    exam_target = exam_of(db, getattr(payload, "user_id", None))
    meta = classify(
        subject=getattr(payload, "topic", None) or getattr(payload, "subject", None),
        subject_type=getattr(payload, "subject_type", None),
        exam_target=exam_target,
        is_yks_fen_question=getattr(payload, "is_yks_fen_question", None)
        or getattr(payload, "is_yks_fen", None),
    )
    steps = parse_steps(getattr(payload, "step_by_step_solution", None))
    premises = parse_premises(getattr(payload, "premises", None))
    tactic = str(getattr(payload, "shortcut_tactic", "") or "").strip()
    if meta["subject_type"] == "sayisal" and not tactic:
        from app.services.ai_engine import craft_shortcut_tactic

        tactic = craft_shortcut_tactic(
            question_text=payload.question_text,
            chosen=payload.chosen or "",
            correct=payload.correct or "",
            explanation=payload.explanation or "",
            exam_target=exam_target,
            steps=steps,
        )
    misconception = (
        getattr(payload, "misconception_tag", None)
        or meta["misconception_tag"]
        or ""
    )
    row = TrapNotebook(
        user_id=payload.user_id,
        question_id=payload.question_id or "",
        question_text=payload.question_text,
        options_json=json.dumps(options, ensure_ascii=False),
        correct=(payload.correct or "").strip().upper()[:1],
        chosen=(payload.chosen or "").strip().upper()[:1],
        explanation=payload.explanation or "",
        distractor_analysis=_analysis(
            payload.chosen or "", payload.correct or "", payload.explanation or ""
        ),
        teacher_note=_teacher_note(payload, exam_target),
        topic=payload.topic or "",
        time_spent_seconds=spent,
        time_trap_triggered=time_trap,
        review_count=review_count,
        next_review_date=next_date,
        created_at=now,
        updated_at=now,
        subject_type=meta["subject_type"],
        shortcut_tactic=tactic,
        steps_json=json.dumps(steps, ensure_ascii=False),
        premises_json=json.dumps(premises, ensure_ascii=False),
        misconception_tag=misconception,
        fen_branch=getattr(payload, "fen_branch", None) or meta["fen_branch"],
        is_yks_fen=bool(meta["is_yks_fen_question"]),
        exam_target=exam_target,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _for_exam(db: Session, user_id: str):
    from sqlalchemy import or_

    from app.services.exams import exam_of, family_of

    target = exam_of(db, user_id)
    family = family_of(target)
    query = select(TrapNotebook).where(TrapNotebook.user_id == user_id)
    if family == "kpss":
        query = query.where(
            or_(
                TrapNotebook.exam_target == target,
                TrapNotebook.exam_target == family,
                TrapNotebook.exam_target == "",
            )
        )
    else:
        query = query.where(
            or_(TrapNotebook.exam_target == target, TrapNotebook.exam_target == family)
        )
    return query, target


def due_traps(db: Session, user_id: str) -> list[TrapNotebook]:
    now = _utcnow()
    query, _ = _for_exam(db, user_id)
    rows = db.scalars(
        query.where(TrapNotebook.next_review_date <= now).order_by(
            TrapNotebook.next_review_date.asc(), TrapNotebook.id.asc()
        )
    ).all()
    return list(rows)


def all_traps(db: Session, user_id: str) -> list[TrapNotebook]:
    query, _ = _for_exam(db, user_id)
    rows = db.scalars(query.order_by(TrapNotebook.created_at.desc())).all()
    return list(rows)


def prioritize_weak(rows: list[TrapNotebook], weak_topics: list[str]) -> list[TrapNotebook]:
    if not weak_topics:
        return list(rows)
    needles = [topic.lower() for topic in weak_topics]

    def key(row: TrapNotebook) -> tuple[int, int]:
        topic = (row.topic or "").lower()
        hit = any(needle in topic or topic in needle for needle in needles if needle)
        return (0 if hit else 1, -(row.id or 0))

    return sorted(rows, key=key)


def complete_trap(
    db: Session,
    user_id: str,
    trap_id: int,
    chosen: str,
) -> TrapNotebook:
    row = db.get(TrapNotebook, trap_id)
    if row is None or row.user_id != user_id:
        raise KeyError("Tuzak sorusu bulunamadı.")
    now = _utcnow()
    pick = (chosen or "").strip().upper()[:1]
    row.chosen = pick
    row.updated_at = now
    if pick == (row.correct or "").strip().upper()[:1]:
        row.next_review_date, row.review_count = schedule_after_correct(
            row.review_count, now
        )
    else:
        row.next_review_date, row.review_count = schedule_after_wrong(now)
        row.distractor_analysis = _analysis(pick, row.correct, row.explanation)
    db.commit()
    db.refresh(row)
    return row


def traps_since(db: Session, user_id: str, since: datetime) -> list[TrapNotebook]:
    rows = db.scalars(
        select(TrapNotebook)
        .where(TrapNotebook.user_id == user_id)
        .where(TrapNotebook.created_at >= since)
        .order_by(TrapNotebook.created_at.desc())
    ).all()
    return list(rows)


def to_public(row: TrapNotebook) -> dict:
    try:
        options = json.loads(row.options_json or "{}")
    except json.JSONDecodeError:
        options = {}
    return {
        "id": row.id,
        "user_id": row.user_id,
        "question_id": row.question_id,
        "question_text": row.question_text,
        "options": options,
        "correct": row.correct,
        "chosen": row.chosen,
        "explanation": row.explanation,
        "distractor_analysis": row.distractor_analysis,
        "teacher_note": getattr(row, "teacher_note", "") or row.distractor_analysis,
        "topic": row.topic,
        "time_spent_seconds": row.time_spent_seconds,
        "time_trap_triggered": bool(row.time_trap_triggered),
        "review_count": row.review_count,
        "next_review_date": _aware(row.next_review_date).isoformat()
        if row.next_review_date
        else None,
        "subject_type": getattr(row, "subject_type", "") or "sozel",
        "shortcut_tactic": getattr(row, "shortcut_tactic", "") or "",
        "step_by_step_solution": _parse_json_list(getattr(row, "steps_json", None), kind="steps"),
        "premises": _parse_json_list(getattr(row, "premises_json", None), kind="premises"),
        "misconception_tag": getattr(row, "misconception_tag", "") or "",
        "fen_branch": getattr(row, "fen_branch", "") or "",
        "is_yks_fen": bool(getattr(row, "is_yks_fen", False)),
    }


def _parse_json_list(raw, *, kind: str):
    from app.services.subjects import parse_premises, parse_steps

    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            data = raw
    if kind == "premises":
        return parse_premises(data)
    return parse_steps(data)
