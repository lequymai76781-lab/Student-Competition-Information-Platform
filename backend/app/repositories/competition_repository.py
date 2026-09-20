from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    College,
    Competition,
    CompetitionEdition,
    CompetitionPolicyRecognition,
    CompetitionSource,
    CompetitionStatistics,
    UniversityCompetitionEditionRelation,
    PolicyDocument,
    Tag,
    University,
)
from app.schemas.competition import CompetitionCreate, CompetitionUpdate


class CompetitionRepository:
    def list_competitions(
        self,
        db: Session,
        *,
        keyword: str | None = None,
        category: str | None = None,
        competition_level: str | None = None,
        grade: str | None = None,
        team_type: str | None = None,
        status: str | None = None,
        edition_status: str | None = None,
        tag: str | None = None,
        availability: str | None = None,
        policy_coverage_min: int | None = None,
        data_completeness_min: float | None = None,
        has_college_recognition: bool | None = None,
        cross_university: bool | None = None,
        competition_type: str | None = None,
        source_scope: str | None = None,
        university_id: int | None = None,
        college_id: int | None = None,
        year: int | None = None,
        sort: str = "deadline",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Competition]:
        stmt = select(Competition).options(
            selectinload(Competition.tags),
            selectinload(Competition.tracks),
            selectinload(Competition.editions),
            selectinload(Competition.editions).selectinload(CompetitionEdition.university_relations),
            selectinload(Competition.editions)
            .selectinload(CompetitionEdition.university_relations)
            .selectinload(UniversityCompetitionEditionRelation.university),
            selectinload(Competition.editions)
            .selectinload(CompetitionEdition.university_relations)
            .selectinload(UniversityCompetitionEditionRelation.college),
            selectinload(Competition.sources),
            selectinload(Competition.statistics),
            selectinload(Competition.policy_recognitions).selectinload(CompetitionPolicyRecognition.university),
            selectinload(Competition.policy_recognitions).selectinload(CompetitionPolicyRecognition.college),
        )
        stmt = stmt.where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
        # Duplicate / non-competition rows must never surface in the default
        # hall list; they remain queryable through admin tooling.
        stmt = stmt.where(
            Competition.verification_status.notin_(("duplicate", "non_competition"))
        )
        # Unverified rows with no verified evidence stay admin-only: a
        # no-evidence entity must not look identical to confirmed core events.
        stmt = stmt.where(
            or_(
                Competition.verification_status != "unverified",
                Competition.sources.any(
                    and_(
                        CompetitionSource.is_verified.is_(True),
                        CompetitionSource.is_demo.is_(False),
                    )
                ),
            )
        )

        if year is not None:
            stmt = stmt.join(CompetitionEdition).where(CompetitionEdition.year == year)

        if keyword:
            term = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    Competition.name.ilike(term),
                    Competition.short_name.ilike(term),
                    Competition.description.ilike(term),
                    Competition.organizer.ilike(term),
                )
            )
        if category:
            stmt = stmt.where(Competition.category == category)
        if competition_level:
            stmt = stmt.where(Competition.competition_level == competition_level)
        if grade:
            stmt = stmt.where(Competition.recommended_grade.ilike(f"%{grade}%"))
        if team_type:
            stmt = stmt.where(Competition.team_type == team_type)
        if status:
            stmt = stmt.where(Competition.status == status)
        if edition_status:
            stmt = stmt.where(Competition.editions.any(CompetitionEdition.current_status == edition_status))
        if tag:
            stmt = stmt.where(Competition.tags.any(Tag.name == tag))
        if policy_coverage_min is not None:
            stmt = stmt.where(
                Competition.statistics.has(CompetitionStatistics.policy_reference_count >= policy_coverage_min)
            )
        if data_completeness_min is not None:
            stmt = stmt.where(Competition.data_completeness_score >= data_completeness_min)
        if has_college_recognition is not None:
            has_college = Competition.policy_recognitions.any(CompetitionPolicyRecognition.college_id.is_not(None))
            stmt = stmt.where(has_college if has_college_recognition else ~has_college)
        if cross_university is not None:
            stmt = stmt.where(Competition.is_cross_university_supported.is_(cross_university))
        if competition_type:
            stmt = stmt.where(Competition.competition_type == competition_type)
        if source_scope:
            now = datetime.now(timezone.utc)
            if source_scope == "official_current":
                stmt = stmt.where(
                    Competition.editions.any(
                        and_(
                            CompetitionEdition.is_verified.is_(True),
                            CompetitionEdition.year >= now.year,
                            or_(
                                CompetitionEdition.official_notice_url.is_not(None),
                                CompetitionEdition.official_registration_url.is_not(None),
                                CompetitionEdition.official_registration_deadline.is_not(None),
                            ),
                        )
                    )
                )
            elif source_scope == "university_notice":
                stmt = stmt.where(
                    Competition.editions.any(
                        CompetitionEdition.university_relations.any(
                            UniversityCompetitionEditionRelation.is_demo.is_(False)
                        )
                    )
                )
            elif source_scope == "my_university_notice" and university_id is not None:
                stmt = stmt.where(
                    Competition.editions.any(
                        CompetitionEdition.university_relations.any(
                            and_(
                                UniversityCompetitionEditionRelation.university_id == university_id,
                                UniversityCompetitionEditionRelation.is_demo.is_(False),
                            )
                        )
                    )
                )
            elif source_scope == "my_college_notice" and university_id is not None and college_id is not None:
                stmt = stmt.where(
                    Competition.editions.any(
                        CompetitionEdition.university_relations.any(
                            and_(
                                UniversityCompetitionEditionRelation.university_id == university_id,
                                UniversityCompetitionEditionRelation.college_id == college_id,
                                UniversityCompetitionEditionRelation.is_demo.is_(False),
                            )
                        )
                    )
                )
            elif source_scope == "registration_open":
                stmt = stmt.where(
                    Competition.editions.any(
                        and_(
                            CompetitionEdition.is_verified.is_(True),
                            CompetitionEdition.current_status == "registration_open",
                            CompetitionEdition.registration_deadline.is_not(None),
                            CompetitionEdition.registration_deadline >= now,
                        )
                    )
                )
        if availability:
            now = datetime.now(timezone.utc)
            horizon_days = 90
            if availability == "next_30_days":
                horizon_days = 30
            horizon = now + timedelta(days=horizon_days)
            actionable = and_(
                CompetitionEdition.is_verified.is_(True),
                or_(
                    and_(
                        CompetitionEdition.registration_deadline.is_not(None),
                        CompetitionEdition.registration_deadline >= now,
                        CompetitionEdition.registration_deadline <= horizon,
                    ),
                    and_(
                        CompetitionEdition.submission_deadline.is_not(None),
                        CompetitionEdition.submission_deadline >= now,
                        CompetitionEdition.submission_deadline <= horizon,
                    ),
                ),
                CompetitionEdition.current_status.in_(
                    ["registration_open", "registration_upcoming", "submission_open", "upcoming"]
                ),
            )
            stmt = stmt.where(Competition.editions.any(actionable))

        if sort == "latest":
            stmt = stmt.order_by(Competition.updated_at.desc())
        elif sort == "name":
            stmt = stmt.order_by(Competition.name.asc())
        else:
            stmt = stmt.order_by(Competition.updated_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        return list(db.execute(stmt).scalars().unique().all())

    def get_by_id(self, db: Session, competition_id: int) -> Competition | None:
        stmt = (
            select(Competition)
            .options(
                selectinload(Competition.tags),
                selectinload(Competition.tracks),
                selectinload(Competition.editions),
                selectinload(Competition.editions).selectinload(CompetitionEdition.university_relations),
                selectinload(Competition.editions)
                .selectinload(CompetitionEdition.university_relations)
                .selectinload(UniversityCompetitionEditionRelation.university),
                selectinload(Competition.editions)
                .selectinload(CompetitionEdition.university_relations)
                .selectinload(UniversityCompetitionEditionRelation.college),
                selectinload(Competition.sources),
                selectinload(Competition.statistics),
                selectinload(Competition.aliases),
                selectinload(Competition.parent),
                selectinload(Competition.children),
                selectinload(Competition.policy_recognitions).selectinload(CompetitionPolicyRecognition.university),
                selectinload(Competition.policy_recognitions).selectinload(CompetitionPolicyRecognition.college),
            )
            .where(Competition.id == competition_id, Competition.is_competition.is_(True))
        )
        return db.execute(stmt).scalars().unique().one_or_none()

    def create(self, db: Session, competition_in: CompetitionCreate) -> Competition:
        payload = competition_in.model_dump(exclude={"tag_ids"})
        competition = Competition(**payload)
        if competition_in.tag_ids:
            competition.tags = list(db.execute(select(Tag).where(Tag.id.in_(competition_in.tag_ids))).scalars().all())
        db.add(competition)
        db.commit()
        db.refresh(competition)
        return self.get_by_id(db, competition.id) or competition

    def update(self, db: Session, competition: Competition, competition_in: CompetitionUpdate) -> Competition:
        payload = competition_in.model_dump(exclude_unset=True, exclude={"tag_ids"})
        for field, value in payload.items():
            setattr(competition, field, value)
        if competition_in.tag_ids is not None:
            competition.tags = list(db.execute(select(Tag).where(Tag.id.in_(competition_in.tag_ids))).scalars().all())
        db.add(competition)
        db.commit()
        db.refresh(competition)
        return self.get_by_id(db, competition.id) or competition

    def list_recognition(
        self,
        db: Session,
        competition_id: int,
        university_id: int | None = None,
    ) -> list[dict]:
        stmt = (
            select(
                CompetitionPolicyRecognition,
                University.name,
                College.name,
                PolicyDocument.title,
                PolicyDocument.source_url,
                PolicyDocument.attachment_url,
            )
            .join(University, University.id == CompetitionPolicyRecognition.university_id)
            .join(PolicyDocument, PolicyDocument.id == CompetitionPolicyRecognition.policy_document_id)
            .outerjoin(College, College.id == CompetitionPolicyRecognition.college_id)
            .where(
                CompetitionPolicyRecognition.competition_id == competition_id,
                CompetitionPolicyRecognition.is_demo.is_(False),
            )
            .order_by(CompetitionPolicyRecognition.year.desc(), University.name.asc())
        )
        if university_id is not None:
            stmt = stmt.where(CompetitionPolicyRecognition.university_id == university_id)

        rows = db.execute(stmt).all()
        return [
            {
                "id": policy.id,
                "university_id": policy.university_id,
                "university_name": university_name,
                "college_id": policy.college_id,
                "college_name": college_name,
                "policy_document_id": policy.policy_document_id,
                "policy_title": policy_title,
                "source_url": source_url,
                "attachment_url": attachment_url,
                "year": policy.year,
                "recognition_status": policy.recognition_status,
                "recognition_level": policy.recognition_level,
                "award_requirement": policy.award_requirement,
                "score_text": policy.score_text,
                "score_numeric": policy.score_numeric,
                "usage_type": policy.usage_type,
                "evidence_text": policy.evidence_text,
                "evidence_page": policy.evidence_page,
                "confidence": policy.confidence,
                "needs_manual_review": policy.needs_manual_review,
                "is_demo": policy.is_demo,
            }
            for policy, university_name, college_name, policy_title, source_url, attachment_url in rows
        ]

    def list_deadline_before(self, competitions: list[Competition], deadline_before: datetime | None) -> list[Competition]:
        if deadline_before is None:
            return competitions
        result: list[Competition] = []
        for competition in competitions:
            deadlines = [edition.registration_deadline for edition in competition.editions if edition.registration_deadline]
            if any(deadline <= deadline_before for deadline in deadlines):
                result.append(competition)
        return result
