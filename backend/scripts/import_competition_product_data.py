import argparse
import json
import subprocess
from pathlib import Path

from app.database.session import SessionLocal
from app.services.competition_edition_seed_service import CompetitionEditionSeedService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_seed_import_service import CompetitionSeedImportService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_ROOT = PROJECT_ROOT / "references" / "college-competitions-skill"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import competition discovery seeds and verified edition data.")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=REFERENCE_ROOT / "competition-catalog.md",
        help="Markdown, JSON or CSV competition seed file.",
    )
    parser.add_argument(
        "--editions",
        type=Path,
        default=PROJECT_ROOT / "data" / "seeds" / "competition_editions_2026.json",
    )
    args = parser.parse_args()

    commit_sha = None
    if REFERENCE_ROOT.exists():
        commit_sha = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REFERENCE_ROOT.as_posix()}",
                "-C",
                str(REFERENCE_ROOT),
                "rev-parse",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip() or None

    with SessionLocal() as db:
        seed_stats = CompetitionSeedImportService().import_file(
            db,
            args.catalog,
            source_file=args.catalog.name,
            commit_sha=commit_sha,
        )
        intelligence = CompetitionIntelligenceService()
        hierarchy_stats = intelligence.build_hierarchy(db)
        edition_stats = CompetitionEditionSeedService().import_json(db, args.editions)
        tag_stats = intelligence.apply_tags(db)
        score_stats = intelligence.refresh_all(db)

    print(
        json.dumps(
            {
                "seed": seed_stats,
                "hierarchy": hierarchy_stats,
                "editions": edition_stats,
                "tags": tag_stats,
                "scores": score_stats,
                "source_repository": "Tomzkl/college-competitions-skill",
                "commit_sha": commit_sha,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
