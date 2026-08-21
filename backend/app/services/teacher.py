"""Hoca paneli: sınıf listesi, analiz, Sazan Avı paylaşımı ve kupon eşleşmesi."""

from __future__ import annotations

import json
from collections import Counter
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    TeacherAssignment,
    TeacherStudent,
    User,
    UserStats,
)
from app.services.penalty import get_or_create_user


def _alias(user_id: str) -> str:
    digest = hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:4].upper()
    return f"Aday-{digest}"

ROLES = ("student", "teacher", "admin")
STAFF_ROLES = {"teacher", "admin"}


def normalize_role(raw: str | None, default: str = "student") -> str:
    value = (raw or "").strip().lower()
    if value in ROLES:
        return value
    return default


def dashboard_for(role: str) -> str:
    if role in STAFF_ROLES:
        return "/hoca"
    return "/"


def display_name_of(db: Session, user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        return ""
    user = db.get(User, uid)
    named = ((getattr(user, "display_name", "") or "") if user else "").strip()
    if named:
        return named
    stats = db.get(UserStats, uid)
    if stats and (stats.display_name or "").strip():
        return (stats.display_name or "").strip()
    return _alias(uid)


def set_display_name(db: Session, user_id: str, name: str) -> None:
    label = (name or "").strip()[:64]
    if not label:
        return
    user = get_or_create_user(db, user_id)
    user.display_name = label
    stats = db.get(UserStats, user_id)
    if stats is None:
        stats = UserStats(user_id=user_id, display_name=label, level=1)
        db.add(stats)
    else:
        stats.display_name = label
    db.add(user)
    db.add(stats)


def require_teacher(db: Session, user_id: str) -> User:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Hoca kimliği gerekli.")
    user = get_or_create_user(db, uid)
    role = normalize_role(getattr(user, "role", "") or "student")
    if role not in STAFF_ROLES:
        raise PermissionError("Bu alan yalnızca hoca hesaplarına açık.")
    return user


def enroll_student(
    db: Session,
    teacher_id: str,
    student_id: str,
    *,
    source: str = "promo",
    promo_code: str = "",
) -> bool:
    tid = (teacher_id or "").strip()
    sid = (student_id or "").strip()
    if not tid or not sid or tid == sid:
        return False
    teacher = db.get(User, tid)
    if teacher is None or normalize_role(getattr(teacher, "role", "")) not in STAFF_ROLES:
        return False
    student = get_or_create_user(db, sid)
    student.teacher_id = tid
    db.add(student)
    existing = db.scalar(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == tid,
            TeacherStudent.student_id == sid,
        )
    )
    if existing is None:
        db.add(
            TeacherStudent(
                teacher_id=tid,
                student_id=sid,
                source=(source or "promo")[:16],
                promo_code=(promo_code or "")[:32],
            )
        )
    return True


def _loads_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        uid = str(item or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def _student_ids(db: Session, teacher_id: str) -> list[str]:
    rows = list(
        db.scalars(
            select(TeacherStudent).where(TeacherStudent.teacher_id == teacher_id)
        ).all()
    )
    ids = [row.student_id for row in rows]
    extras = list(
        db.scalars(select(User.user_id).where(User.teacher_id == teacher_id)).all()
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for uid in ids + extras:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        ordered.append(uid)
    return ordered


def _student_card(db: Session, student_id: str) -> dict:
    from app.services import diagnostic as diagnostic_service
    from app.services.traps import all_traps

    user = get_or_create_user(db, student_id)
    stats = db.get(UserStats, student_id)
    diag = diagnostic_service.status(db, student_id)
    baseline = diag.get("baseline") or {}
    traps = all_traps(db, student_id)
    weak = list(diag.get("weak_topics") or [])
    return {
        "user_id": student_id,
        "display_name": display_name_of(db, student_id),
        "baseline_score": float(diag.get("baseline_score") or 0),
        "net_range": baseline.get("net_range") or "",
        "is_tested": bool(diag.get("is_tested")),
        "trap_count": len(traps),
        "traps_cleared": int(getattr(stats, "traps_cleared", 0) or 0),
        "xp": int(getattr(stats, "xp", 0) or 0),
        "weak_topics": weak[:5],
        "exam_target": getattr(user, "exam_target", "") or "",
        "analysis_summary": (baseline.get("analysis_summary") or "")[:280],
    }


def list_classroom(db: Session, teacher_id: str) -> dict:
    teacher = require_teacher(db, teacher_id)
    ids = _student_ids(db, teacher_id)
    students = [_student_card(db, sid) for sid in ids]
    students.sort(key=lambda item: (-float(item["baseline_score"]), -int(item["xp"])))
    for index, item in enumerate(students, start=1):
        item["rank"] = index

    heat: Counter[str] = Counter()
    from app.services.traps import all_traps

    for sid in ids:
        card = next(item for item in students if item["user_id"] == sid)
        for topic in card.get("weak_topics") or []:
            label = str(topic or "").strip()
            if label:
                heat[label] += 2
        for trap in all_traps(db, sid):
            topic = (getattr(trap, "topic", "") or "").strip()
            if topic:
                heat[topic] += 1

    total = max(len(ids), 1)
    hot_topics = [
        {
            "topic": topic,
            "hits": count,
            "intensity": int(round(100 * min(count / (total * 3), 1))),
        }
        for topic, count in heat.most_common(5)
    ]
    avg = (
        round(sum(float(item["baseline_score"]) for item in students) / len(students), 1)
        if students
        else 0.0
    )
    return {
        "teacher_id": teacher.user_id,
        "teacher_name": display_name_of(db, teacher.user_id),
        "role": normalize_role(getattr(teacher, "role", "")),
        "student_count": len(students),
        "class_average": avg,
        "students": students,
        "ranking": students[:20],
        "hot_topics": hot_topics,
    }


def student_analysis(db: Session, teacher_id: str, student_id: str) -> dict:
    require_teacher(db, teacher_id)
    sid = (student_id or "").strip()
    if sid not in _student_ids(db, teacher_id):
        raise PermissionError("Bu öğrenci senin sınıfında değil.")
    from app.services import diagnostic as diagnostic_service
    from app.services import mistake_doctor as doctor_service
    from app.services.traps import all_traps, to_public

    card = _student_card(db, sid)
    doctor = doctor_service.diagnose(db, sid)
    traps = [to_public(row) for row in all_traps(db, sid)[:40]]
    diag = diagnostic_service.status(db, sid)
    return {
        "student": card,
        "doctor": doctor,
        "traps": traps,
        "baseline": diag.get("baseline") or {},
        "weak_topics": diag.get("weak_topics") or [],
        "analysis_summary": (diag.get("baseline") or {}).get("analysis_summary") or "",
    }


def share_resource(
    db: Session,
    teacher_id: str,
    *,
    title: str = "",
    topic: str = "",
    question_text: str = "",
    options: dict | None = None,
    correct: str = "",
    explanation: str = "",
    student_ids: list[str] | None = None,
) -> dict:
    require_teacher(db, teacher_id)
    text = (question_text or "").strip()
    if len(text) < 8:
        raise ValueError("Soru metni en az 8 karakter olmalı.")
    class_ids = _student_ids(db, teacher_id)
    wanted = [str(item or "").strip() for item in (student_ids or []) if str(item or "").strip()]
    targets = [sid for sid in wanted if sid in class_ids] if wanted else list(class_ids)
    if not targets:
        raise ValueError("Sınıfta henüz öğrenci yok. Önce kuponla eşleştir.")
    row = TeacherAssignment(
        teacher_id=teacher_id,
        title=(title or "Sazan Avı").strip()[:128] or "Sazan Avı",
        topic=(topic or "").strip()[:128],
        question_text=text,
        options_json=json.dumps(options or {}, ensure_ascii=False),
        correct=(correct or "").strip()[:8].upper(),
        explanation=(explanation or "").strip(),
        assigned_to_json=json.dumps(targets, ensure_ascii=False),
        completed_by_json="[]",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _assignment_public(row, student_id="")


def _assignment_public(row: TeacherAssignment, student_id: str) -> dict:
    try:
        options = json.loads(row.options_json or "{}")
    except json.JSONDecodeError:
        options = {}
    assigned = _loads_list(row.assigned_to_json)
    done = _loads_list(row.completed_by_json)
    payload = {
        "id": row.id,
        "teacher_id": row.teacher_id,
        "title": row.title,
        "topic": row.topic,
        "question_text": row.question_text,
        "options": options if isinstance(options, dict) else {},
        "assigned_count": len(assigned),
        "completed_count": len(done),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed": bool(student_id and student_id in done),
    }
    if student_id:
        payload["correct"] = ""
        payload["explanation"] = ""
    else:
        payload["correct"] = row.correct
        payload["explanation"] = row.explanation
        payload["assigned_to"] = assigned
    return payload


def list_teacher_assignments(db: Session, teacher_id: str) -> dict:
    require_teacher(db, teacher_id)
    rows = list(
        db.scalars(
            select(TeacherAssignment)
            .where(TeacherAssignment.teacher_id == teacher_id)
            .order_by(TeacherAssignment.created_at.desc())
        ).all()
    )
    items = [_assignment_public(row, student_id="") for row in rows]
    return {"assignments": items, "count": len(items)}


def list_student_assignments(db: Session, student_id: str) -> dict:
    uid = (student_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    user = get_or_create_user(db, uid)
    teacher_id = (getattr(user, "teacher_id", "") or "").strip()
    if not teacher_id:
        return {
            "assignments": [],
            "count": 0,
            "teacher_id": "",
            "teacher_name": "",
        }
    rows = list(
        db.scalars(
            select(TeacherAssignment)
            .where(TeacherAssignment.teacher_id == teacher_id)
            .order_by(TeacherAssignment.created_at.desc())
        ).all()
    )
    items = []
    for row in rows:
        assigned = _loads_list(row.assigned_to_json)
        if assigned and uid not in assigned:
            continue
        items.append(_assignment_public(row, student_id=uid))
    return {
        "assignments": items,
        "count": len(items),
        "teacher_id": teacher_id,
        "teacher_name": display_name_of(db, teacher_id),
    }


def submit_assignment(db: Session, student_id: str, assignment_id: int, chosen: str) -> dict:
    uid = (student_id or "").strip()
    row = db.get(TeacherAssignment, int(assignment_id))
    if row is None:
        raise ValueError("Bu görev bulunamadı.")
    assigned = _loads_list(row.assigned_to_json)
    if assigned and uid not in assigned:
        raise PermissionError("Bu görev sana ait değil.")
    pick = (chosen or "").strip().upper()[:8]
    correct = (row.correct or "").strip().upper()
    ok = bool(correct) and pick == correct
    done = _loads_list(row.completed_by_json)
    if uid not in done:
        done.append(uid)
        row.completed_by_json = json.dumps(done, ensure_ascii=False)
        db.add(row)
        db.commit()
    message = (
        "Doğru. Hocanın avını çözdün."
        if ok
        else (row.explanation or "Yanlış. Tuzak defterine bak, hocan da görecek.")
    )
    return {
        "ok": True,
        "correct": ok,
        "message": message,
        "answer": row.correct if not ok else "",
        "explanation": row.explanation if not ok else "",
    }
