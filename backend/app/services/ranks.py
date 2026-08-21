"""XP'ye göre TİLKO rütbesi ve dinamik hitap."""

from __future__ import annotations

from sqlalchemy.orm import Session

RANK_ACEMI = "Acemi Tilki"
RANK_KURNAZ = "Kurnaz Prens"
RANK_KIDEMLI = "Kıdemli Tilki"
RANK_ALFA = "Alfa Tilki"
RANK_EMOJI = "🦊"

# 0–499 Acemi, 500–1499 Kurnaz Prens, 1500–2999 Kıdemli, 3000+ Alfa
RANK_BANDS: tuple[tuple[int, str], ...] = (
    (3000, RANK_ALFA),
    (1500, RANK_KIDEMLI),
    (500, RANK_KURNAZ),
)


def fox_rank(xp: int | None) -> dict[str, str]:
    """Toplam Tilki Puanı’na göre unvan ve emoji."""
    value = max(int(xp or 0), 0)
    for threshold, title in RANK_BANDS:
        if value >= threshold:
            return {"title": title, "emoji": RANK_EMOJI}
    return {"title": RANK_ACEMI, "emoji": RANK_EMOJI}


def address(xp: int | None = None) -> str:
    """Bildirim ve koç metinlerinde kullanılacak hitap."""
    return fox_rank(xp)["title"]


def address_for(db: Session, user_id: str | None) -> str:
    """Kullanıcının güncel XP’sine göre hitap; kayıt yoksa Acemi Tilki."""
    if not user_id:
        return RANK_ACEMI
    from app.database.models import UserStats

    row = db.get(UserStats, user_id)
    return address(row.xp if row is not None else 0)


def fill_title(text: str, title: str) -> str:
    return (text or "").replace("{title}", title)
