"""Run one policy crawl in an isolated process with a parent-enforced timeout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.crawler.discovery.university_discovery import UniversitySeedLoader
from app.crawler.scheduler import PolicyCrawlerScheduler
from app.database.session import SessionLocal


def main() -> None:
    seed_path, output_path, storage = map(Path, sys.argv[1:4])
    seed = UniversitySeedLoader(seed_path).load_985()[0]
    with SessionLocal() as db:
        scheduler = PolicyCrawlerScheduler(seed_path=seed_path, storage_root=storage, respect_robots=True)
        result = scheduler.pipeline.run_batch(
            db, [seed], max_pages_per_university=2, max_attachments_per_page=2, dry_run=False
        )[0]
        db.commit()
    output_path.write_text(json.dumps({
        "status": result.status, "pages_discovered": result.pages_discovered,
        "pages_fetched": result.pages_fetched, "documents_found": result.documents_found,
        "documents_parsed": result.documents_parsed, "policies_found": result.policies_found,
        "competitions_found": result.competitions_found,
        "errors": [getattr(error, "message", str(error)) for error in result.errors],
    }, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
