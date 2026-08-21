"""Sözel / sayısal ve YKS Fen sınıflandırması."""

from __future__ import annotations

import json

SAYISAL = "sayisal"
SOZEL = "sozel"
MISCONCEPTION = "Kavram Yanılgısı"

NUM_NEEDLES = (
    "matematik",
    "geometri",
    "sayısal",
    "sayisal",
    "mantık",
    "mantik",
    "fizik",
    "kimya",
    "biyoloji",
    "fen",
    "türev",
    "turev",
    "integral",
    "limit",
    "denklem",
    "yüzde",
    "yuzde",
    "oran",
    "problem",
    "sayı",
    "sayi",
    "vektör",
    "vektor",
    "molekül",
    "molekul",
    "gen",
    "hücre",
    "hucre",
)

FEN_BRANCHES = {
    "fizik": ("fizik", "mekanik", "optik", "elektrik", "dalga", "hareket", "kuvvet"),
    "kimya": ("kimya", "molekül", "molekul", "asit", "baz", "bağ", "bag", "element", "tepki"),
    "biyoloji": ("biyoloji", "hücre", "hucre", "gen", "doku", "evrim", "fotosentez", "enzim"),
}


def normalize_type(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {SAYISAL, "numeric", "math", "matematik", "sayısal"}:
        return SAYISAL
    if value in {SOZEL, "verbal", "sözel"}:
        return SOZEL
    return ""


def fen_branch_of(subject: str | None) -> str:
    blob = (subject or "").lower()
    for branch, needles in FEN_BRANCHES.items():
        if any(item in blob for item in needles):
            return branch
    return ""


def is_numerical_subject(subject: str | None, subject_type: str | None = None) -> bool:
    forced = normalize_type(subject_type)
    if forced:
        return forced == SAYISAL
    blob = (subject or "").lower()
    return any(item in blob for item in NUM_NEEDLES)


def is_yks_fen(
    *,
    exam_target: str | None,
    subject: str | None = None,
    flag: bool | None = None,
) -> bool:
    if flag is True:
        return True
    family = (exam_target or "").strip().lower()
    if family != "yks":
        return False
    if fen_branch_of(subject):
        return True
    blob = (subject or "").lower()
    return "fen" in blob


def classify(
    *,
    subject: str | None = None,
    subject_type: str | None = None,
    exam_target: str | None = None,
    is_yks_fen_question: bool | None = None,
) -> dict:
    fen = is_yks_fen(
        exam_target=exam_target,
        subject=subject,
        flag=is_yks_fen_question,
    )
    numerical = is_numerical_subject(subject, subject_type) or fen
    branch = fen_branch_of(subject)
    kind = SAYISAL if numerical else SOZEL
    return {
        "subject_type": kind,
        "is_yks_fen_question": fen,
        "fen_branch": branch,
        "misconception_tag": MISCONCEPTION if fen else "",
    }


def parse_steps(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.startswith("["):
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                pass
        if isinstance(raw, str):
            parts = [
                part.strip(" -•\t")
                for part in raw.replace("\r", "").split("\n")
                if part.strip()
            ]
            return [part for part in parts if part][:8]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("step") or item.get("detail") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            out.append(text)
        if len(out) >= 8:
            break
    return out


def parse_premises(raw) -> list[dict]:
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    labels = ("I", "II", "III")
    out: list[dict] = []
    for index, item in enumerate(raw[:3]):
        if not isinstance(item, dict):
            text = str(item or "").strip()
            if not text:
                continue
            out.append(
                {
                    "id": labels[index],
                    "text": text,
                    "is_correct": False,
                    "why": "",
                }
            )
            continue
        why = str(item.get("why") or item.get("reason") or item.get("explanation") or "").strip()
        out.append(
            {
                "id": str(item.get("id") or labels[index]).strip() or labels[index],
                "text": str(item.get("text") or item.get("statement") or "").strip(),
                "is_correct": bool(item.get("is_correct") or item.get("correct")),
                "why": why,
            }
        )
    return [row for row in out if row.get("text")]
