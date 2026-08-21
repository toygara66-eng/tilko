"""Pazar akşamı bülteni üretmek için:

    .\\.venv\\Scripts\\python.exe tools\\weekly_bulletin.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal, init_db  # noqa: E402
from app.services.bulletin import generate_bulletin  # noqa: E402


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        row = generate_bulletin(db)
        print(f"bulten: {row.week_id}")
        print(f"baslik: {row.title}")
        print(f"html  : {row.html_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
