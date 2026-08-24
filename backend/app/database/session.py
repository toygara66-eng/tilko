import logging
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

_default_db = Path(__file__).resolve().parents[2] / "data" / "kpss.db"
DB_PATH = Path(settings.database_path) if settings.database_path.strip() else _default_db
DATA_DIR = DB_PATH.parent


def _normalize_database_url(raw: str) -> str:
    """Neon/Heroku postgres:// → SQLAlchemy+psycopg URL."""
    url = (raw or "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    # Neon: sslmode=require çoğu connection string'de var; yoksa ekle
    if "postgresql" in url and "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


DATABASE_URL = _normalize_database_url(settings.database_url)
IS_SQLITE = not bool(DATABASE_URL)


class Base(DeclarativeBase):
    pass


if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=5,
    )
    logger.info(
        "Postgres veritabanı: %s",
        urlparse(DATABASE_URL)._replace(netloc="***").geturl()
        if "://" in DATABASE_URL
        else "postgres",
    )
else:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_busy_wal(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tablo yoksa oluşturur; SQLite'ta eksik sütunları ALTER TABLE ile ekler."""
    from app.database import models as _models  # noqa: F401

    if IS_SQLITE:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if settings.is_production:
            logger.error(
                "PRODUCTION uyarı: DATABASE_URL yok — yerel SQLite (%s) Render "
                "free’de her uykuda silinir. Neon ücretsiz Postgres bağla "
                "(DATABASE_URL).",
                DB_PATH,
            )
        else:
            logger.info("SQLite veritabanı: %s", DB_PATH)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    if IS_SQLITE:
        _rebuild_daily_challenge_exam_unique()
    try:
        from app.services.rag import seed_style_guides

        db = SessionLocal()
        try:
            seed_style_guides(db)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ÖSYM stil rehberi tohumlanamadı: %s", exc)
    try:
        from app.services.exams import seed_exam_schedules

        db = SessionLocal()
        try:
            seed_exam_schedules(db)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sınav takvimi tohumlanamadı: %s", exc)


def _adapt_column_ddl(ddl: str) -> str:
    if IS_SQLITE:
        return ddl
    out = ddl.replace("DATETIME", "TIMESTAMPTZ")
    out = out.replace("BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE")
    out = out.replace("BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE")
    return out


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    specs: dict[str, dict[str, str]] = {
        "trap_notebook": {
            "review_count": "INTEGER DEFAULT 0",
            "next_review_date": "DATETIME",
            "time_spent_seconds": "INTEGER DEFAULT 0",
            "time_trap_triggered": "BOOLEAN DEFAULT 0",
            "distractor_analysis": "TEXT DEFAULT ''",
            "teacher_note": "TEXT DEFAULT ''",
            "subject_type": "VARCHAR(16) DEFAULT 'sozel'",
            "shortcut_tactic": "TEXT DEFAULT ''",
            "steps_json": "TEXT DEFAULT '[]'",
            "premises_json": "TEXT DEFAULT '[]'",
            "misconception_tag": "VARCHAR(64) DEFAULT ''",
            "fen_branch": "VARCHAR(32) DEFAULT ''",
            "is_yks_fen": "BOOLEAN DEFAULT 0",
            "exam_target": "VARCHAR(32) DEFAULT ''",
        },
        "users": {
            "is_penalized": "BOOLEAN DEFAULT 0",
            "penalty_clear_count": "INTEGER DEFAULT 0",
            "updated_at": "DATETIME",
            "discount_percentage": "INTEGER DEFAULT 0",
            "is_free_next_month": "BOOLEAN DEFAULT 0",
            "prize_rank": "INTEGER DEFAULT 0",
            "prize_source_month": "VARCHAR(7) DEFAULT ''",
            "identity_hash": "VARCHAR(128) DEFAULT ''",
            "is_premium": "BOOLEAN DEFAULT 0",
            "ai_credits_left": "INTEGER DEFAULT 7",
            "baseline_score": "REAL DEFAULT 0",
            "is_tested": "BOOLEAN DEFAULT 0",
            "exam_target": "VARCHAR(32) DEFAULT ''",
            "is_onboarded": "BOOLEAN DEFAULT 0",
            "target_score": "REAL DEFAULT 0",
            "password_hash": "VARCHAR(256) DEFAULT ''",
            "google_sub": "VARCHAR(64) DEFAULT ''",
            "email": "VARCHAR(256) DEFAULT ''",
            "phone": "VARCHAR(32) DEFAULT ''",
            "created_at": "DATETIME",
            "daily_ad_rewarded_credits": "INTEGER DEFAULT 1",
            "last_credit_reset_date": "DATE",
            "last_ad_unlock_at": "DATETIME",
            "subscription_product_id": "VARCHAR(64) DEFAULT ''",
            "subscription_status": "VARCHAR(32) DEFAULT ''",
            "subscription_expires_at": "DATETIME",
            "play_purchase_token_hash": "VARCHAR(64) DEFAULT ''",
            "role": "VARCHAR(16) DEFAULT 'student'",
            "teacher_id": "VARCHAR(128) DEFAULT ''",
            "display_name": "VARCHAR(64) DEFAULT ''",
        },
        "user_stats": {
            "last_pomodoro_session": "VARCHAR(64) DEFAULT ''",
        },
        "daily_challenges": {
            "exam_target": "VARCHAR(32) DEFAULT 'kpss_lisans'",
            "subject_type": "VARCHAR(16) DEFAULT 'sozel'",
            "shortcut_tactic": "TEXT DEFAULT ''",
            "steps_json": "TEXT DEFAULT '[]'",
            "premises_json": "TEXT DEFAULT '[]'",
            "misconception_tag": "VARCHAR(64) DEFAULT ''",
            "fen_branch": "VARCHAR(32) DEFAULT ''",
            "is_yks_fen": "BOOLEAN DEFAULT 0",
        },
        "challenge_leaderboard": {
            "is_suspicious": "BOOLEAN DEFAULT 0",
            "is_cheated": "BOOLEAN DEFAULT 0",
            "eligible": "BOOLEAN DEFAULT 0",
            "started_at": "DATETIME",
            "finished_at": "DATETIME",
            "device_id": "VARCHAR(64) DEFAULT ''",
            "ip_hash": "VARCHAR(64) DEFAULT ''",
        },
        "promo_codes": {
            "max_uses": "INTEGER DEFAULT 0",
            "used_count": "INTEGER DEFAULT 0",
            "used_by_json": "TEXT DEFAULT '[]'",
            "status": "VARCHAR(16) DEFAULT 'active'",
            "created_by_teacher_id": "VARCHAR(128) DEFAULT ''",
            "enroll_to_class": "BOOLEAN DEFAULT 0",
        },
    }
    with engine.begin() as conn:
        for table, wanted in specs.items():
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in wanted.items():
                if name in existing:
                    continue
                adapted = _adapt_column_ddl(ddl)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {adapted}"))
                logger.info("%s sütunu eklendi: %s", table, name)


def _rebuild_daily_challenge_exam_unique() -> None:
    """Eski unique(date) kısıtını unique(date, exam_target) ile değiştirir (yalnız SQLite)."""
    inspector = inspect(engine)
    if "daily_challenges" not in inspector.get_table_names():
        return
    with engine.begin() as conn:
        indexes = conn.execute(text("PRAGMA index_list('daily_challenges')")).fetchall()
        date_only_unique = False
        for row in indexes:
            unique = bool(row[2]) if len(row) > 2 else False
            if not unique:
                continue
            cols = conn.execute(text(f"PRAGMA index_info('{row[1]}')")).fetchall()
            names = [item[2] for item in cols]
            if names == ["date"]:
                date_only_unique = True
                break
        if not date_only_unique:
            return
        conn.execute(
            text(
                """
                CREATE TABLE daily_challenges_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_text TEXT NOT NULL,
                    options TEXT DEFAULT '{}',
                    correct_answer VARCHAR(8) DEFAULT '',
                    trap_explanation TEXT DEFAULT '',
                    date DATE,
                    exam_target VARCHAR(32) DEFAULT 'kpss_lisans',
                    UNIQUE (date, exam_target)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO daily_challenges_new
                (id, question_text, options, correct_answer, trap_explanation, date, exam_target)
                SELECT id, question_text, options, correct_answer, trap_explanation, date,
                       CASE WHEN exam_target IS NULL OR exam_target = ''
                            THEN 'kpss_lisans' ELSE exam_target END
                FROM daily_challenges
                """
            )
        )
        conn.execute(text("DROP TABLE daily_challenges"))
        conn.execute(text("ALTER TABLE daily_challenges_new RENAME TO daily_challenges"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_challenges_date ON daily_challenges (date)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_daily_challenges_exam_target "
                "ON daily_challenges (exam_target)"
            )
        )
        logger.info("daily_challenges unique(date, exam_target) olarak yenilendi")
