from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionAlias


@dataclass(slots=True)
class CompetitionNormalizationResult:
    competition: Competition | None
    normalized_name: str | None
    confidence: float
    method: str
    needs_manual_review: bool
    reason: str


class CompetitionNormalizationService:
    ambiguous_short_names = {"挑战杯", "互联网+", "创新大赛", "大创"}
    historical_names = {
        "中国互联网+大学生创新创业大赛": "中国国际大学生创新大赛",
        "互联网+大学生创新创业大赛": "中国国际大学生创新大赛",
        "挑战杯中国大学生创业计划大赛": "“挑战杯”中国大学生创业计划竞赛",
    }

    def normalize(self, db: Session, raw_name: str) -> CompetitionNormalizationResult:
        name = self._normalize_text(raw_name)
        if not name:
            return self._unmatched(raw_name, "empty_name")

        if name in self.ambiguous_short_names:
            return self._unmatched(raw_name, "ambiguous_short_name")

        canonical_name = self.historical_names.get(name)
        if canonical_name:
            historical_match = db.execute(
                select(Competition).where(Competition.name == canonical_name)
            ).scalar_one_or_none()
            if historical_match:
                return CompetitionNormalizationResult(
                    historical_match,
                    historical_match.name,
                    1.0,
                    "historical_name",
                    False,
                    "verified historical competition name",
                )

        competition = db.execute(select(Competition).where(Competition.name == raw_name)).scalar_one_or_none()
        if competition:
            return CompetitionNormalizationResult(competition, competition.name, 1.0, "exact_name", False, "exact competition name")

        alias_rows = list(db.execute(select(CompetitionAlias).where(CompetitionAlias.normalized_alias == name)).scalars().all())
        if len(alias_rows) == 1:
            competition = alias_rows[0].competition
            return CompetitionNormalizationResult(competition, competition.name, alias_rows[0].confidence, "exact_alias", False, "exact alias")
        if len(alias_rows) > 1:
            return self._unmatched(raw_name, "ambiguous_alias")

        competitions = list(db.execute(select(Competition)).scalars().all())
        scored = [
            (SequenceMatcher(a=name, b=self._normalize_text(competition.name)).ratio(), competition)
            for competition in competitions
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and scored[0][0] >= 0.88:
            competition = scored[0][1]
            return CompetitionNormalizationResult(competition, competition.name, scored[0][0], "fuzzy_name", False, "high-confidence fuzzy match")
        if scored and scored[0][0] >= 0.72:
            competition = scored[0][1]
            return CompetitionNormalizationResult(competition, competition.name, scored[0][0], "fuzzy_name", True, "low-confidence fuzzy match")

        return self._unmatched(raw_name, "no_match")

    def normalize_or_create(
        self,
        db: Session,
        raw_name: str,
        *,
        trusted_policy: bool,
        source_title: str,
        category: str | None = None,
        source_url: str | None = None,
    ) -> CompetitionNormalizationResult:
        result = self.normalize(db, raw_name)
        from app.database.review_guard import is_review_guarded
        if is_review_guarded(db):
            if result.competition is not None and not result.needs_manual_review:
                return result
            from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService
            CompetitionFieldIngestionService().stage(
                db, entity_type="competition", title=f"高校政策发现：{raw_name}",
                fields={"name": raw_name.strip(), **({"category": category} if category else {})},
                source={"source_type": "university_policy", "source_title": source_title[:255], "source_url": source_url},
                producer="policy_normalization", raw={"raw_name": raw_name, "source_title": source_title,
                    "source_url": source_url, "trusted_policy_claim": trusted_policy},
            )
            return self._unmatched(raw_name, "pending_field_review")
        if result.competition and (not trusted_policy or result.method != "fuzzy_name"):
            if result.competition.name != raw_name.strip():
                self.ensure_alias(
                    db,
                    result.competition,
                    raw_name.strip(),
                    source="verified_policy",
                    confidence=result.confidence,
                    is_verified=True,
                )
            return result
        if not trusted_policy:
            return result

        normalized = self._normalize_text(raw_name)
        if normalized in self.ambiguous_short_names or not (4 <= len(normalized) <= 255):
            return self._unmatched(raw_name, "unsafe_new_competition_name")

        canonical_name = self.historical_names.get(normalized, raw_name.strip())
        competition = Competition(
            name=canonical_name,
            category=category,
            description=f"由已验证高校政策《{source_title}》首次发现。",
            status="active",
            is_demo=False,
        )
        db.add(competition)
        db.flush()
        self.ensure_alias(
            db,
            competition,
            raw_name.strip(),
            source="verified_policy",
            confidence=1.0,
            is_verified=True,
        )
        return CompetitionNormalizationResult(
            competition,
            competition.name,
            1.0,
            "created_from_verified_policy",
            False,
            "created from verified policy evidence",
        )

    def ensure_alias(
        self,
        db: Session,
        competition: Competition,
        alias: str,
        *,
        source: str = "manual",
        confidence: float = 1.0,
        is_verified: bool = False,
        is_demo: bool = False,
    ) -> CompetitionAlias:
        normalized = self._normalize_text(alias)
        existing = db.execute(
            select(CompetitionAlias).where(
                CompetitionAlias.competition_id == competition.id,
                CompetitionAlias.alias == alias,
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        row = CompetitionAlias(
            competition_id=competition.id,
            alias=alias,
            normalized_alias=normalized,
            source=source,
            confidence=confidence,
            is_verified=is_verified,
            is_demo=is_demo,
        )
        db.add(row)
        db.flush()
        return row

    def _unmatched(self, raw_name: str, reason: str) -> CompetitionNormalizationResult:
        return CompetitionNormalizationResult(None, None, 0.0, "none", True, reason)

    def _normalize_text(self, value: str) -> str:
        return (
            value.strip()
            .replace("“", "")
            .replace("”", "")
            .replace("\"", "")
            .replace(" ", "")
            .replace("　", "")
            .lower()
        )
