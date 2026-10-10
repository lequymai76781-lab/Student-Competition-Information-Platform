from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    College,
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionFactSource,
    University,
    UniversityCompetitionEditionRelation,
)
from app.repositories.competition_repository import CompetitionRepository
from app.schemas.competition import (
    CompetitionCreate,
    CompetitionDetail,
    CompetitionEditionRead,
    CompetitionFactRevisionRead,
    CompetitionFactSourceRead,
    CompetitionHierarchyItem,
    CompetitionListItem,
    CompetitionRecognitionRead,
    CompetitionUpdate,
    FeaturedRecognition,
    UniversityCompetitionNoticeRead,
)
from app.schemas.tag import TagRead
from app.services.source_credibility_service import SourceCredibilityService
from app.services.deadline_resolution_service import DeadlineResolutionService
from app.services.edition_status_service import ACTIONABLE_STATUSES
from app.services.user_facing_data_policy import UserFacingDataPolicy


class CompetitionService:
    def __init__(self) -> None:
        self.repository = CompetitionRepository()
        self.credibility_service = SourceCredibilityService()
        self.deadline_service = DeadlineResolutionService()

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
        deadline_before: datetime | None = None,
        year: int | None = None,
        sort: str = "deadline",
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[CompetitionListItem]:
        competitions = self.repository.list_competitions(
            db,
            keyword=keyword,
            category=category,
            competition_level=competition_level,
            grade=grade,
            team_type=team_type,
            status=status,
            edition_status=None,
            tag=tag,
            availability=None,
            policy_coverage_min=policy_coverage_min,
            data_completeness_min=data_completeness_min,
            has_college_recognition=has_college_recognition,
            cross_university=cross_university,
            competition_type=competition_type,
            source_scope=None if source_scope == "registration_open" else source_scope,
            university_id=university_id,
            college_id=college_id,
            year=year,
            sort=sort,
            limit=None,
            offset=0,
        )
        now = datetime.now(timezone.utc)
        required_status = edition_status or ("registration_open" if source_scope == "registration_open" else None)
        items = [
            self._to_list_item(competition, university_id=university_id, college_id=college_id,
                               now=now, year=year, required_status=required_status, source_scope=source_scope)
            for competition in competitions
        ]
        if source_scope or year is not None:
            items = [item for item in items if item.current_edition_id is not None]
        if required_status:
            items = [item for item in items if item.current_status == required_status]
        if availability:
            horizon = now + timedelta(days=30 if availability == "next_30_days" else 90)
            items = [item for item in items if item.current_status in ACTIONABLE_STATUSES
                     and item.action_deadline and now <= self._aware(item.action_deadline) <= horizon]
        if deadline_before:
            items = [item for item in items if item.action_deadline
                     and self._aware(item.action_deadline) <= self._aware(deadline_before)]
        if sort == "deadline":
            items = sorted(
                items,
                key=lambda item: self._aware(item.action_deadline) if item.action_deadline else datetime.max.replace(tzinfo=timezone.utc),
            )
        return items[offset:offset + limit] if limit is not None else items[offset:]

    def count_open_competitions(self, db: Session) -> dict[str, int]:
        """Count each competition once per status, using the list's edition rules."""
        competitions = self.repository.list_competitions(db, limit=None)
        now = datetime.now(timezone.utc)
        return {
            status: sum(
                self._current_edition(competition, now=now, required_status=status) is not None
                for competition in competitions
            )
            for status in ("registration_open", "submission_open")
        }

    def get_competition(
        self,
        db: Session,
        competition_id: int,
        *,
        university_id: int | None = None,
        college_id: int | None = None,
        edition_id: int | None = None,
    ) -> CompetitionDetail:
        competition = self.repository.get_by_id(db, competition_id)
        if competition is None or not UserFacingDataPolicy.competition_allowed(competition):
            raise HTTPException(status_code=404, detail="Competition not found")
        if edition_id is not None and not any(edition.id == edition_id for edition in competition.editions):
            raise HTTPException(status_code=404, detail="Competition edition not found")
        fact_sources = list(
            db.execute(
                select(CompetitionFactSource)
                .where(CompetitionFactSource.competition_id == competition_id)
                .order_by(CompetitionFactSource.reliability_tier, CompetitionFactSource.field_name)
            ).scalars()
        )
        notices = self._list_university_notices(db, competition_id)
        revisions = list(
            db.execute(
                select(CompetitionFactRevision)
                .where(CompetitionFactRevision.competition_id == competition_id)
                .order_by(CompetitionFactRevision.changed_at.desc(), CompetitionFactRevision.id.desc())
                .limit(20)
            ).scalars()
        )
        return self._to_detail(
            competition,
            fact_sources,
            notices,
            revisions,
            university_id=university_id,
            college_id=college_id,
            edition_id=edition_id,
        )

    def create_competition(self, db: Session, competition_in: CompetitionCreate) -> CompetitionDetail:
        competition = self.repository.create(db, competition_in)
        return self._to_detail(competition, [], [], [])

    def update_competition(self, db: Session, competition_id: int, competition_in: CompetitionUpdate) -> CompetitionDetail:
        competition = self.repository.get_by_id(db, competition_id)
        if competition is None:
            raise HTTPException(status_code=404, detail="Competition not found")
        updated = self.repository.update(db, competition, competition_in)
        return self._to_detail(updated, [], [], [])

    def list_recognition(
        self,
        db: Session,
        competition_id: int,
        university_id: int | None = None,
    ) -> list[CompetitionRecognitionRead]:
        if self.repository.get_by_id(db, competition_id) is None:
            raise HTTPException(status_code=404, detail="Competition not found")
        rows = self.repository.list_recognition(db, competition_id, university_id)
        return [CompetitionRecognitionRead(**row) for row in rows]

    def _current_edition(self, competition: Competition, *, university_id=None, college_id=None,
                         now=None, year=None, required_status=None, edition_id=None, source_scope=None) -> CompetitionEdition | None:
        editions = [edition for edition in competition.editions
                    if UserFacingDataPolicy.verified_record(edition) and (year is None or edition.year == year)
                    and (edition_id is None or edition.id == edition_id)]
        now = now or datetime.now(timezone.utc)
        if source_scope:
            editions = [edition for edition in editions if self._matches_source_scope(
                edition, source_scope, university_id=university_id, college_id=college_id, now=now)]
        if required_status:
            editions = [edition for edition in editions if self.deadline_service.status(
                edition, university_id=university_id, college_id=college_id, now=now) == required_status]
        if not editions:
            return None
        actionable = [
            edition
            for edition in editions
            if edition.is_verified
            and self.deadline_service.status(edition, university_id=university_id, college_id=college_id, now=now) in ACTIONABLE_STATUSES
        ]
        if actionable:
            return min(
                actionable,
                key=lambda edition: self._aware(self.deadline_service.resolve_action(
                    edition, university_id=university_id, college_id=college_id, now=now)[0])
                    if self.deadline_service.resolve_action(edition, university_id=university_id, college_id=college_id, now=now)[0]
                    else datetime.max.replace(tzinfo=timezone.utc),
            )
        return sorted(
            editions,
            key=lambda edition: (edition.is_verified, edition.year, edition.id),
            reverse=True,
        )[0]

    def _matches_source_scope(self, edition, source_scope, *, university_id, college_id, now):
        if source_scope == "registration_open":
            return self.deadline_service.status(
                edition, university_id=university_id, college_id=college_id, now=now) == "registration_open"
        if source_scope == "official_current":
            return bool(edition.is_verified and edition.year >= now.year and (
                edition.official_notice_url or edition.official_registration_url or edition.official_registration_deadline))
        if source_scope in {"university_notice", "my_university_notice", "my_college_notice"}:
            return any(
                UserFacingDataPolicy.relation_allowed(relation)
                and (source_scope == "university_notice" or relation.university_id == university_id)
                and (source_scope != "my_college_notice" or relation.college_id == college_id)
                for relation in edition.university_relations
            )
        return True

    def _to_list_item(
        self,
        competition: Competition,
        *,
        university_id: int | None = None,
        college_id: int | None = None,
        now: datetime | None = None,
        year: int | None = None,
        required_status: str | None = None,
        edition_id: int | None = None,
        source_scope: str | None = None,
    ) -> CompetitionListItem:
        now = now or datetime.now(timezone.utc)
        edition = self._current_edition(competition, university_id=university_id, college_id=college_id,
                                        now=now, year=year, required_status=required_status, edition_id=edition_id,
                                        source_scope=source_scope)
        action_deadline, action_label, resolution = self.deadline_service.resolve_action(
            edition,
            university_id=university_id,
            college_id=college_id,
            now=now,
        )
        statistics = competition.statistics
        featured = self._featured_recognition(competition)
        recognitions = [item for item in competition.policy_recognitions if UserFacingDataPolicy.recognition_allowed(item)]
        university_count = len({item.university_id for item in recognitions})
        college_count = len(
            {(item.university_id, item.college_id) for item in recognitions if item.college_id is not None}
        )
        return CompetitionListItem(
            id=competition.id,
            name=competition.name,
            short_name=competition.short_name,
            description=competition.description,
            organizer=competition.organizer,
            category=competition.category,
            competition_level=competition.competition_level,
            team_type=competition.team_type,
            difficulty_level=competition.difficulty_level,
            recommended_grade=competition.recommended_grade,
            parent_competition_id=competition.parent_competition_id,
            competition_type=competition.competition_type,
            status=competition.status,
            registration_deadline=edition.registration_deadline if edition else None,
            official_registration_deadline=resolution.official_deadline,
            university_registration_deadline=resolution.university_deadline,
            college_registration_deadline=resolution.college_deadline,
            submission_deadline=edition.submission_deadline if edition else None,
            official_submission_deadline=resolution.official_submission_deadline,
            action_deadline=action_deadline,
            action_deadline_label=action_label,
            effective_deadline=resolution.effective_deadline,
            effective_deadline_type=resolution.effective_deadline_type,
            current_edition_name=edition.edition_name if edition else None,
            current_edition_id=edition.id if edition else None,
            registration_closing_soon=bool(action_deadline and now <= self._aware(action_deadline) <= now + timedelta(days=7)
                and self.deadline_service.status(edition, university_id=university_id, college_id=college_id, now=now) == "registration_open"),
            current_status=self.deadline_service.status(edition, university_id=university_id, college_id=college_id, now=now),
            policy_reference_count=statistics.policy_reference_count if statistics else 0,
            university_inclusion_count=university_count,
            college_inclusion_count=college_count,
            has_college_recognition=any(item.college_id is not None for item in recognitions),
            official_source_count=statistics.official_source_count if statistics else 0,
            source_count=statistics.source_count if statistics else len([source for source in competition.sources if not source.is_demo]),
            university_source_count=statistics.university_source_count if statistics else self._loaded_university_source_count(competition),
            university_notice_count=statistics.university_count if statistics else self._loaded_university_notice_count(competition),
            is_official_verified=competition.is_official_verified,
            verification_status=self._effective_verification_status(competition),
            edition_last_verified_at=edition.last_verified_at if edition else None,
            edition_source_updated_at=edition.source_updated_at if edition else None,
            freshness_status=edition.freshness_status if edition else "unknown",
            featured_recognition=featured,
            tags=[TagRead.model_validate(tag) for tag in competition.tags],
            is_demo=competition.is_demo,
        )

    def _to_detail(
        self,
        competition: Competition,
        fact_sources: list[CompetitionFactSource],
        university_notices: list[UniversityCompetitionNoticeRead],
        fact_revisions: list[CompetitionFactRevision],
        *,
        university_id: int | None = None,
        college_id: int | None = None,
        edition_id: int | None = None,
    ) -> CompetitionDetail:
        now = datetime.now(timezone.utc)
        list_item = self._to_list_item(
            competition,
            university_id=university_id,
            college_id=college_id,
            now=now,
            edition_id=edition_id,
        )
        current_edition = next((edition for edition in competition.editions if edition.id == list_item.current_edition_id), None)
        return CompetitionDetail(
            **list_item.model_dump(),
            english_name=competition.english_name,
            former_names=competition.former_names or [],
            official_website=competition.official_website,
            official_account=competition.official_account,
            founded_year=competition.founded_year,
            first_held_year=competition.first_held_year,
            frequency=competition.frequency,
            edition_count=competition.edition_count,
            co_organizers=competition.co_organizers or [],
            guiding_organizations=competition.guiding_organizations or [],
            undertakers=competition.undertakers or [],
            description_source_url=competition.description_source_url,
            development_history=competition.development_history,
            history_timeline=self._verified_items(competition.history_timeline),
            participation_requirements=self._verified_items(competition.participation_requirements),
            competition_process=self._verified_items(competition.competition_process),
            submission_requirements=self._verified_items(competition.submission_requirements),
            award_settings=self._verified_items(competition.award_settings),
            detail_ready=competition.detail_ready,
            founded_year_candidate=competition.founded_year_candidate,
            competition_format=competition.competition_format,
            competition_scope=competition.competition_scope,
            country_or_region=competition.country_or_region,
            target_students=competition.target_students,
            min_team_size=competition.min_team_size,
            max_team_size=competition.max_team_size,
            is_cross_major_supported=competition.is_cross_major_supported,
            is_cross_university_supported=competition.is_cross_university_supported,
            typical_schedule=competition.typical_schedule,
            aliases=[alias.alias for alias in competition.aliases],
            parent=(
                CompetitionHierarchyItem(
                    id=competition.parent.id,
                    name=competition.parent.name,
                    competition_type=competition.parent.competition_type,
                )
                if competition.parent
                else None
            ),
            children=[
                CompetitionHierarchyItem(id=child.id, name=child.name, competition_type=child.competition_type)
                for child in competition.children
            ],
            tracks=competition.tracks,
            editions=[self._edition_read(edition, university_id=university_id, college_id=college_id, now=now)
                      for edition in competition.editions if UserFacingDataPolicy.verified_record(edition)],
            sources=[item for item in competition.sources if UserFacingDataPolicy.verified_record(item)
                     and item.competition_edition_id in (None, list_item.current_edition_id)],
            fact_sources=[CompetitionFactSourceRead.model_validate(item) for item in fact_sources
                          if item.competition_edition_id in (None, list_item.current_edition_id)
                          and item.verification_status in UserFacingDataPolicy.VERIFIED_FACT_STATUSES],
            fact_revisions=[CompetitionFactRevisionRead.model_validate(item) for item in fact_revisions
                            if item.competition_edition_id in (None, list_item.current_edition_id)
                            and item.verification_status in UserFacingDataPolicy.VERIFIED_FACT_STATUSES],
            university_notices=[item for item in university_notices
                                if item.competition_edition_id == list_item.current_edition_id
                                and (university_id is None or item.university_id == university_id)
                                and (college_id is None or item.college_id in (None, college_id))],
            deadline_resolution=self.deadline_service.resolve_registration(
                current_edition,
                university_id=university_id,
                college_id=college_id,
            ),
            official_verification_status=self._verification_label(self._effective_verification_status(competition)),
            last_verified_at=competition.last_verified_at,
            last_seen_at=competition.last_seen_at,
            updated_at=competition.updated_at,
        )

    def _verified_items(self, items):
        return [item for item in items or [] if isinstance(item, dict)
                and item.get("verification_status") in UserFacingDataPolicy.VERIFIED_FACT_STATUSES]

    def _edition_read(self, edition: CompetitionEdition, *, university_id=None, college_id=None, now=None) -> CompetitionEditionRead:
        return CompetitionEditionRead(
            id=edition.id,
            year=edition.year,
            edition_name=edition.edition_name,
            registration_start=self.deadline_service.registration_start(edition, university_id=university_id, college_id=college_id),
            registration_deadline=edition.registration_deadline,
            official_registration_deadline=edition.official_registration_deadline,
            university_registration_deadline=edition.university_registration_deadline,
            submission_deadline=edition.submission_deadline,
            official_submission_deadline=edition.official_submission_deadline,
            competition_start=edition.competition_start,
            competition_end=edition.competition_end,
            official_competition_date=edition.official_competition_date,
            announcement_date=edition.announcement_date,
            edition_number=edition.edition_number,
            registration_fee=edition.registration_fee,
            fee_notes=edition.fee_notes,
            official_url=edition.official_url,
            official_notice_url=edition.official_notice_url,
            official_registration_url=edition.official_registration_url,
            source_url=edition.source_url,
            is_verified=edition.is_verified,
            verification_status=edition.verification_status,
            last_verified_at=edition.last_verified_at,
            last_seen_at=edition.last_seen_at,
            source_updated_at=edition.source_updated_at,
            next_check_at=edition.next_check_at,
            freshness_status=edition.freshness_status,
            status=self.deadline_service.status(edition, university_id=university_id, college_id=college_id, now=now),
            current_status=self.deadline_service.status(edition, university_id=university_id, college_id=college_id, now=now),
        )

    def _featured_recognition(self, competition: Competition) -> FeaturedRecognition | None:
        recognitions = [item for item in competition.policy_recognitions if UserFacingDataPolicy.recognition_allowed(item)]
        if not recognitions:
            return None
        ordered = sorted(
            recognitions,
            key=lambda item: (
                item.university.name != "武汉体育学院",
                item.college_id is None,
                -(item.year or 0),
            ),
        )
        recognition = ordered[0]
        return FeaturedRecognition(
            university_name=recognition.university.name,
            college_name=recognition.college.name if recognition.college else None,
            recognition_level=recognition.recognition_level,
            year=recognition.year,
        )

    def _list_university_notices(self, db: Session, competition_id: int) -> list[UniversityCompetitionNoticeRead]:
        rows = db.execute(
            select(UniversityCompetitionEditionRelation, University.name, College.name, CompetitionEdition)
            .join(CompetitionEdition, CompetitionEdition.id == UniversityCompetitionEditionRelation.competition_edition_id)
            .join(University, University.id == UniversityCompetitionEditionRelation.university_id)
            .outerjoin(College, College.id == UniversityCompetitionEditionRelation.college_id)
            .where(
                CompetitionEdition.competition_id == competition_id,
                UniversityCompetitionEditionRelation.is_demo.is_(False),
            )
            .order_by(
                UniversityCompetitionEditionRelation.internal_registration_deadline.asc(),
                University.name.asc(),
            )
        ).all()
        return [
            UniversityCompetitionNoticeRead(
                id=relation.id,
                university_id=relation.university_id,
                university_name=university_name,
                college_id=relation.college_id,
                college_name=college_name,
                competition_edition_id=relation.competition_edition_id,
                edition_year=edition.year,
                edition_name=edition.edition_name,
                source_type=relation.source_type,
                source_name=relation.source_name,
                source_platform=relation.source_platform,
                notice_type=relation.notice_type,
                notice_title=relation.notice_title,
                internal_notice_url=relation.internal_notice_url,
                organizing_department=relation.organizing_department,
                internal_contact=relation.internal_contact,
                contact_person=relation.contact_person,
                contact_method=relation.contact_method,
                internal_registration_start=relation.internal_registration_start,
                internal_registration_deadline=relation.internal_registration_deadline,
                internal_submission_deadline=relation.internal_submission_deadline,
                college_registration_start=relation.college_registration_start,
                college_registration_deadline=relation.college_registration_deadline,
                college_submission_deadline=relation.college_submission_deadline,
                official_registration_deadline=relation.official_registration_deadline,
                published_at=relation.published_at,
                observed_at=relation.observed_at,
                last_verified_at=relation.last_verified_at,
                verification_status=relation.verification_status,
                is_verified=relation.is_verified,
            )
            for relation, university_name, college_name, edition in rows
            if UserFacingDataPolicy.relation_allowed(relation)
        ]

    def _loaded_university_source_count(self, competition: Competition) -> int:
        return len(
            [
                source
                for source in competition.sources
                if not source.is_demo and source.source_type in {"university_official", "university_official_notice", "college_official_notice"}
            ]
        )

    def _loaded_university_notice_count(self, competition: Competition) -> int:
        return len(
            {
                relation.university_id
                for edition in competition.editions
                for relation in edition.university_relations
                if not relation.is_demo
            }
        )

    def _aware(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _edition_action_deadline(self, edition: CompetitionEdition, now: datetime) -> datetime | None:
        deadlines = [
            self._aware(value)
            for value in (edition.registration_deadline, edition.submission_deadline)
            if value is not None and self._aware(value) >= now
        ]
        return min(deadlines) if deadlines else None

    def _verification_label(self, status: str) -> str:
        return {
            "verified_manual": "人工核验通过",
            "verified_official": "官方来源已核实",
            "authority_confirmed": "国家级权威已确认",
            "association_confirmed": "高教学会/全国学会目录已收录（非教育部认定）",
            "official_site_confirmed": "官方赛事网站已确认",
            "school_confirmed": "高校来源已确认（全国事实待核实）",
            "pending_verification": "待权威来源核验",
            "verified_multi_source": "多来源交叉核实",
            "secondary_source_only": "仅有二级来源",
            "conflicting": "来源存在冲突",
            "suspected": "对象性质待复核",
            "duplicate": "已判定重复（等待合并处理）",
            "non_competition": "非正式竞赛（不进入赛事大厅）",
            "unverified": "暂未核实",
        }.get(status, "暂未核实")

    def _effective_verification_status(self, competition: Competition) -> str:
        if competition.verification_status == "unverified" and competition.is_official_verified:
            return "verified_official"
        return competition.verification_status
