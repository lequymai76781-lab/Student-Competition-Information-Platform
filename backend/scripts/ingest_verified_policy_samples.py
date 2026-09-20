import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.services.verified_policy_ingest_service import VerifiedPolicyIngestService


def main() -> None:
    db = SessionLocal()
    try:
        result = VerifiedPolicyIngestService().ingest(db)
        db.commit()
        print("Verified policy samples imported:")
        for key, value in result.items():
            print(f"  {key}={value}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
