import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.fact_intelligence_service import FactIntelligenceService


GITHUB_ROOT = PROJECT_ROOT / "references" / "contest-ddl"


def main() -> None:
    commit = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={GITHUB_ROOT.as_posix()}",
            "-C",
            str(GITHUB_ROOT),
            "rev-parse",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with SessionLocal() as db:
        result = FactIntelligenceService().run(
            db,
            policy_rows_path=PROJECT_ROOT / "data" / "seeds" / "wuhan_sports_university_journalism_competitions.json",
            github_snapshot_path=GITHUB_ROOT / "data" / "competitions.json",
            university_seed_path=PROJECT_ROOT / "data" / "seeds" / "v04_university_discovery.json",
            github_repository="Nemoyuzx/contest-ddl",
            github_commit=commit,
        )
        intelligence = CompetitionIntelligenceService()
        result["tags"] = intelligence.apply_tags(db)
        result["statistics"] = intelligence.refresh_all(db)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
