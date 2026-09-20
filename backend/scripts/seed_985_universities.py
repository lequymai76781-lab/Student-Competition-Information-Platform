import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import University

ROOT_DIR = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT_DIR / "data" / "seeds" / "985_universities.json"
EXPECTED_985_COUNT = 39


def load_seed() -> list[dict]:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    names = [item["name"] for item in data]
    if len(data) != EXPECTED_985_COUNT:
        raise ValueError(f"Expected {EXPECTED_985_COUNT} 985 universities, got {len(data)}")
    if len(set(names)) != len(names):
        raise ValueError("985 seed contains duplicate university names")
    missing_domains = [item["name"] for item in data if not item.get("official_domain")]
    if missing_domains:
        raise ValueError(f"Missing official_domain: {', '.join(missing_domains)}")
    return data


def upsert_universities(db: Session, rows: list[dict]) -> tuple[int, int]:
    created = 0
    updated = 0
    for row in rows:
        university = db.execute(select(University).where(University.name == row["name"])).scalar_one_or_none()
        payload = {
            "short_name": row.get("short_name"),
            "english_name": row.get("english_name"),
            "aliases": row.get("aliases", []),
            "province": row.get("province"),
            "city": row.get("city"),
            "university_type": row.get("university_type", "综合类"),
            "is_985": bool(row.get("is_985", True)),
            "is_211": bool(row.get("is_211", True)),
            "is_double_first_class": True,
            "official_website": row.get("official_website"),
            "official_domain": row.get("official_domain"),
            "is_demo": False,
        }
        if university is None:
            university = University(name=row["name"], **payload)
            db.add(university)
            created += 1
        else:
            for key, value in payload.items():
                setattr(university, key, value)
            updated += 1
    return created, updated


def main() -> None:
    rows = load_seed()
    db = SessionLocal()
    try:
        created, updated = upsert_universities(db, rows)
        db.commit()
        print(f"985 universities imported: created={created}, updated={updated}, total={len(rows)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
