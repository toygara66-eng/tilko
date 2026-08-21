import json
import logging
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import TrapNotebook, WeeklyBulletin

logger = logging.getLogger(__name__)

BULLETIN_DIR = Path(__file__).resolve().parents[2] / "data" / "bulletins"
NON_WORD_RE = __import__("re").compile(r"[^a-z0-9]+")


def week_id_for(moment: datetime | None = None) -> str:
    stamp = moment or datetime.now(timezone.utc)
    iso = stamp.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_bounds(week_id: str) -> tuple[datetime, datetime]:
    year, week = week_id.split("-W")
    start = datetime.fromisocalendar(int(year), int(week), 1).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return start, end


def _fingerprint(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return NON_WORD_RE.sub(" ", folded).strip()[:90]


def _trap_key(row: TrapNotebook) -> str:
    if row.question_id:
        return f"id:{row.question_id}"
    return f"t:{_fingerprint(row.question_text or '')}"


def collect_top_traps(db: Session, week_id: str, limit: int = 3) -> dict:
    start, end = week_bounds(week_id)
    rows = list(
        db.scalars(
            select(TrapNotebook)
            .where(TrapNotebook.created_at >= start)
            .where(TrapNotebook.created_at < end)
        ).all()
    )
    users = {row.user_id for row in rows}
    buckets: dict[str, dict] = defaultdict(
        lambda: {
            "falls": 0,
            "users": set(),
            "time_traps": 0,
            "question_text": "",
            "topic": "",
            "explanation": "",
            "chosen": defaultdict(int),
        }
    )
    for row in rows:
        key = _trap_key(row)
        bucket = buckets[key]
        bucket["falls"] += 1
        bucket["users"].add(row.user_id)
        if row.time_trap_triggered:
            bucket["time_traps"] += 1
        bucket["question_text"] = bucket["question_text"] or (row.question_text or "")
        bucket["topic"] = bucket["topic"] or (row.topic or "Genel")
        bucket["explanation"] = bucket["explanation"] or (row.explanation or "")
        if row.chosen:
            bucket["chosen"][row.chosen] += 1

    ranked = sorted(buckets.values(), key=lambda b: (len(b["users"]), b["falls"]), reverse=True)
    top = []
    total_users = max(len(users), 1)
    for index, bucket in enumerate(ranked[:limit], start=1):
        user_count = len(bucket["users"])
        pct = round(100 * user_count / total_users)
        popular = ""
        if bucket["chosen"]:
            popular = max(bucket["chosen"], key=bucket["chosen"].get)
        top.append(
            {
                "rank": index,
                "topic": bucket["topic"],
                "question_text": bucket["question_text"],
                "falls": bucket["falls"],
                "user_count": user_count,
                "percent": pct,
                "time_trap_count": bucket["time_traps"],
                "popular_wrong": popular,
                "explanation": bucket["explanation"],
                "headline": (
                    f"Tuzak defterine düşen adayların %{pct}'i bu hafta bu soruya takıldı"
                    if pct
                    else "Bu hafta bu tuzak öne çıktı"
                ),
            }
        )
    return {
        "week_id": week_id,
        "period_start": start.date().isoformat(),
        "period_end": (end - timedelta(days=1)).date().isoformat(),
        "candidate_count": len(users),
        "trap_count": len(rows),
        "traps": top,
    }


def _render_html(payload: dict) -> str:
    cards = []
    if not payload["traps"]:
        cards.append(
            """
            <article class="empty">
              <h2>Bu hafta henüz tuzak yok</h2>
              <p>Adaylar defteri doldurdukça pazar akşamı manşet burada belirir.</p>
            </article>
            """
        )
    for item in payload["traps"]:
        time_note = (
            f'<p class="time">Süre tuzağı: {item["time_trap_count"]} aday 60 saniyeyi aştı.</p>'
            if item["time_trap_count"]
            else ""
        )
        wrong = (
            f'<p class="wrong">En çok kayılan şık: <strong>{item["popular_wrong"]}</strong></p>'
            if item["popular_wrong"]
            else ""
        )
        cards.append(
            f"""
            <article class="story">
              <div class="kicker">TUZAK #{item["rank"]} · {item["topic"]}</div>
              <h2>{item["headline"]}</h2>
              <p class="lede">{item["question_text"]}</p>
              {wrong}
              {time_note}
              <p class="why">{item["explanation"] or "Çeldirici yakın kavramdan geliyor; tanımı değil ayrımı soruyor."}</p>
              <p class="stat">{item["user_count"]} aday · {item["falls"]} düşüş</p>
            </article>
            """
        )
    stories = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Haftanın Tuzakları · {payload["week_id"]}</title>
  <style>
    :root {{ --ink:#1b1a17; --paper:#f6f0e4; --rule:#c4b79a; --red:#8b1e1e; --muted:#6b6254; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:#ddd4c2; color:var(--ink); font-family:"Georgia", "Times New Roman", serif; }}
    .sheet {{ max-width:820px; margin:1.5rem auto; background:var(--paper); padding:2rem 2.2rem 2.6rem; box-shadow:0 12px 40px rgba(0,0,0,.18); }}
    .masthead {{ text-align:center; border-top:4px solid var(--ink); border-bottom:1px solid var(--rule); padding:0.6rem 0 0.9rem; }}
    .masthead .flag {{ letter-spacing:.28em; font-size:.72rem; font-family:system-ui,sans-serif; }}
    h1 {{ font-size:2.4rem; margin:.15rem 0; font-weight:800; }}
    .date {{ font-family:system-ui,sans-serif; color:var(--muted); font-size:.85rem; }}
    .banner {{ background:var(--red); color:#f6f0e4; text-align:center; font-family:system-ui,sans-serif; font-weight:700; padding:.55rem; margin:1rem 0 1.4rem; }}
    .grid {{ display:grid; gap:1.2rem; }}
    .story {{ border-bottom:1px solid var(--rule); padding-bottom:1rem; }}
    .kicker {{ font-family:system-ui,sans-serif; font-size:.7rem; letter-spacing:.14em; color:var(--red); }}
    h2 {{ font-size:1.35rem; line-height:1.25; margin:.3rem 0 .5rem; }}
    .lede {{ font-size:1.05rem; }}
    .stat, .wrong, .time, .why {{ font-family:system-ui,sans-serif; font-size:.88rem; color:var(--muted); }}
    .empty {{ text-align:center; padding:2rem 1rem; }}
    footer {{ margin-top:1.4rem; font-size:.75rem; color:var(--muted); font-family:system-ui,sans-serif; text-align:center; }}
    @media print {{
      body {{ background:white; }}
      .sheet {{ box-shadow:none; margin:0; }}
    }}
  </style>
</head>
<body>
  <div class="sheet">
    <header class="masthead">
      <div class="flag">KPSS PREP · ANONİM TOPLULUK VERİSİ</div>
      <h1>Haftanın Tuzakları</h1>
      <div class="date">{payload["period_start"]} — {payload["period_end"]} · {payload["week_id"]}</div>
    </header>
    <div class="banner">{payload["candidate_count"]} adayın tuzak defteri tarandı · {payload["trap_count"]} düşüş</div>
    <div class="grid">
      {stories}
    </div>
    <footer>Kimlik yok, yalnızca tuzaklar. Yazdır → PDF için tarayıcıda Ctrl+P.</footer>
  </div>
</body>
</html>
"""


def generate_bulletin(db: Session, week_id: str | None = None) -> WeeklyBulletin:
    wid = week_id or week_id_for()
    payload = collect_top_traps(db, wid)
    title = "Haftanın Tuzakları"
    if payload["traps"]:
        title = payload["traps"][0]["headline"]
    BULLETIN_DIR.mkdir(parents=True, exist_ok=True)
    html_path = BULLETIN_DIR / f"{wid}.html"
    html_path.write_text(_render_html(payload), encoding="utf-8")
    row = db.get(WeeklyBulletin, wid)
    if row is None:
        row = WeeklyBulletin(week_id=wid)
        db.add(row)
    row.title = title
    row.html_path = str(html_path)
    row.payload_json = json.dumps(payload, ensure_ascii=False)
    row.created_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    logger.info("Bülten yazıldı: %s", wid)
    return row


def load_bulletin(db: Session, week_id: str | None = None) -> WeeklyBulletin | None:
    wid = week_id or week_id_for()
    return db.get(WeeklyBulletin, wid)


def bulletin_public(row: WeeklyBulletin) -> dict:
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "week_id": row.week_id,
        "title": row.title,
        "html_url": f"/bulletin/{row.week_id}.html",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        **payload,
    }
