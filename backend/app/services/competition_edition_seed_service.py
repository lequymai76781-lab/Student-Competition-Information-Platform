from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionEdition, CompetitionSource
from app.services.competition_normalization_service import CompetitionNormalizationService


class CompetitionEditionSeedService:
    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()

    def import_json(self, db: Session, path: Path) -> dict[str, int]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("editions", payload)
        stats = {"created": 0, "updated": 0, "sources_created": 0, "not_found": 0}
        from app.database.review_guard import is_review_guarded
        if is_review_guarded(db):
            from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService
            helper = CompetitionFieldIngestionService()
            stats["candidates_staged"] = 0
            for item in items:
                competition = self._find_competition(db, item["competition_name"])
                source = next(iter(item.get("sources") or []), {})
                record = {**(item.get("competition_updates") or {}),
                    "competition_name": item["competition_name"], "edition": item,
                    "source_type": source.get("source_type", "crawler"),
                    "source_name": source.get("source_name") or path.name,
                    "source_url": source.get("source_url") or item.get("source_url") or item.get("official_notice_url"),
                    "published_at": source.get("published_at")}
                stats["candidates_staged"] += len(helper.stage_record(db, record, producer="edition_seed", competition=competition))
            db.commit()
            return stats
        for item in items:
            competition = self._find_competition(db, item["competition_name"])
            if competition is None:
                stats["not_found"] += 1
                continue
            for field_name, value in (item.get("competition_updates") or {}).items():
                if value and not getattr(competition, field_name, None):
                    setattr(competition, field_name, value)

            edition = db.execute(
                select(CompetitionEdition).where(
                    CompetitionEdition.competition_id == competition.id,
                    CompetitionEdition.year == int(item["year"]),
                )
            ).scalar_one_or_none()
            edition_payload = {
                "edition_name": item.get("edition_name"),
                "registration_start": self._date(item.get("registration_start")),
                "registration_deadline": self._date(item.get("registration_deadline")),
                "submission_deadline": self._date(item.get("submission_deadline")),
                "competition_start": self._date(item.get("competition_start")),
                "competition_end": self._date(item.get("competition_end")),
                "announcement_date": self._date(item.get("announcement_date")),
                "official_url": item.get("official_url"),
                "official_notice_url": item.get("official_notice_url"),
                "official_registration_url": item.get("official_registration_url"),
                "source_url": item.get("source_url"),
                "is_verified": bool(item.get("is_verified", False)),
                "last_verified_at": self._date(item.get("last_verified_at")),
                "current_status": item.get("status", "unknown"),
            }
            if edition is None:
                edition = CompetitionEdition(
                    competition_id=competition.id,
                    year=int(item["year"]),
                    **edition_payload,
                )
                db.add(edition)
                db.flush()
                stats["created"] += 1
            else:
                for field_name, value in edition_payload.items():
                    setattr(edition, field_name, value)
                stats["updated"] += 1

            for source_item in item.get("sources", []):
                source = db.execute(
                    select(CompetitionSource).where(
                        CompetitionSource.competition_id == competition.id,
                        CompetitionSource.competition_edition_id == edition.id,
                        CompetitionSource.source_url == source_item["source_url"],
                    )
                ).scalar_one_or_none()
                if source is None:
                    db.add(
                        CompetitionSource(
                            competition_id=competition.id,
                            competition_edition_id=edition.id,
                            source_type=source_item.get("source_type", "official_notice"),
                            source_name=source_item.get("source_name"),
                            source_url=source_item["source_url"],
                            source_platform=source_item.get("source_platform", "official_website"),
                            published_at=self._date(source_item.get("published_at")),
                            crawled_at=self._date(item.get("last_verified_at")),
                            is_official=bool(source_item.get("is_official", True)),
                            is_verified=bool(source_item.get("is_verified", True)),
                            credibility_score=int(source_item.get("credibility_score", 100)),
                            raw_title=source_item.get("raw_title") or item.get("edition_name"),
                            metadata_json={"edition_seed_file": path.name},
                            is_demo=False,
                        )
                    )
                    stats["sources_created"] += 1
        db.commit()
        return stats

    def _find_competition(self, db: Session, name: str) -> Competition | None:
        normalized = self.normalizer._normalize_text(name)
        competitions = list(db.execute(select(Competition)).scalars().all())
        return next(
            (competition for competition in competitions if self.normalizer._normalize_text(competition.name) == normalized),
            None,
        )

    def _date(self, value: Any) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
