"""Aylık Sazan Avı ödüllerini bağlar.

Kullanım (backend klasöründen):
    .\\.venv\\Scripts\\python.exe tools\\settle_monthly_prizes.py
    .\\.venv\\Scripts\\python.exe tools\\settle_monthly_prizes.py --month 2026-07
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal, init_db  # noqa: E402
from app.services import prizes as prize_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Aylık kurnaz ödüllerini hesapla")
    parser.add_argument("--month", help="Kaynak ay YYYY-MM (varsayılan: geçen ay)")
    args = parser.parse_args()
    init_db()
    db = SessionLocal()
    try:
        try:
            result = prize_service.settle_month(db, args.month)
        except ValueError as exc:
            print(str(exc))
            return 1
        status = "zaten bagli" if result["already"] else "yeni baglandi"
        print(
            f"{result['source_month']} {status} — {result['winner_count']} odul, "
            f"{result.get('total_active_users', 0)} aktif, asama {result.get('prize_stage', '?')}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
