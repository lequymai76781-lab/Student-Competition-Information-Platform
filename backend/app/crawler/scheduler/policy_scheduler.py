from pathlib import Path

from sqlalchemy.orm import Session

from app.crawler.base import CrawlerRunResult
from app.crawler.discovery.university_discovery import UniversitySeedLoader
from app.crawler.pipelines.university_policy_pipeline import UniversityPolicyPipeline


class PolicyCrawlerScheduler:
    def __init__(self, *, seed_path: Path, storage_root: Path, respect_robots: bool = True) -> None:
        self.seed_loader = UniversitySeedLoader(seed_path)
        self.pipeline = UniversityPolicyPipeline(storage_root=storage_root, respect_robots=respect_robots)

    def run_first_batch(self, db: Session, *, max_pages_per_university: int = 5, dry_run: bool = False) -> list[CrawlerRunResult]:
        return self.pipeline.run_batch(
            db,
            self.seed_loader.first_batch(),
            max_pages_per_university=max_pages_per_university,
            dry_run=dry_run,
        )

    def run_all_985(self, db: Session, *, max_pages_per_university: int = 3, dry_run: bool = False) -> list[CrawlerRunResult]:
        return self.pipeline.run_batch(
            db,
            self.seed_loader.load_985(),
            max_pages_per_university=max_pages_per_university,
            dry_run=dry_run,
        )
