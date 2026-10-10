from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from app.models import CompetitionEdition, UniversityCompetitionEditionRelation
from app.schemas.competition import DeadlineResolutionRead
from app.services.edition_status_service import edition_status
from app.services.user_facing_data_policy import UserFacingDataPolicy

ACTION_NOTICE_TYPES = {"registration_notice", "internal_selection", "submission_notice"}


class DeadlineResolutionService:
    def resolve_registration(
        self,
        edition: CompetitionEdition | None,
        *,
        university_id: int | None = None,
        college_id: int | None = None,
    ) -> DeadlineResolutionRead:
        if not UserFacingDataPolicy.verified_record(edition):
            return DeadlineResolutionRead()

        official_deadline = edition.official_registration_deadline
        relations = self._usable_relations(edition.university_relations, university_id)
        university_relation = self._pick_relation(
            [relation for relation in relations if relation.college_id is None],
            deadline_getter=self._university_registration_deadline,
        )
        college_relation = None
        if college_id is not None:
            college_relation = self._pick_relation(
                [relation for relation in relations if relation.college_id == college_id],
                deadline_getter=self._college_registration_deadline,
            )

        university_deadline = self._university_registration_deadline(university_relation)
        college_deadline = self._college_registration_deadline(college_relation)
        if college_deadline is not None:
            effective_deadline = college_deadline
            effective_type = "college_registration_deadline"
            source_relation = college_relation
        elif university_deadline is not None:
            effective_deadline = university_deadline
            effective_type = "university_registration_deadline"
            source_relation = university_relation
        elif official_deadline is not None:
            effective_deadline = official_deadline
            effective_type = "official_registration_deadline"
            source_relation = None
        else:
            effective_deadline = None
            effective_type = "unverified"
            source_relation = college_relation or university_relation

        return self._read(
            official_deadline=official_deadline,
            official_submission_deadline=edition.official_submission_deadline,
            university_deadline=university_deadline,
            college_deadline=college_deadline,
            effective_deadline=effective_deadline,
            effective_deadline_type=effective_type,
            relation=source_relation,
        )

    def resolve_action(
        self,
        edition: CompetitionEdition | None,
        *,
        university_id: int | None = None,
        college_id: int | None = None,
        now: datetime | None = None,
    ) -> tuple[datetime | None, str | None, DeadlineResolutionRead]:
        registration = self.resolve_registration(edition, university_id=university_id, college_id=college_id)
        if not UserFacingDataPolicy.verified_record(edition):
            return None, None, registration

        current_status = self.status(edition, university_id=university_id, college_id=college_id, now=now)
        if current_status == "registration_upcoming":
            return self.registration_start(edition, university_id=university_id, college_id=college_id), "报名开始", registration

        if current_status == "submission_open":
            submission_deadline, relation, is_official = self._resolve_submission_deadline(
                edition,
                university_id=university_id,
                college_id=college_id,
            )
            return submission_deadline, self._submission_label(relation, is_official), registration

        if registration.effective_deadline is not None:
            return registration.effective_deadline, self._registration_label(registration.effective_deadline_type), registration
        return edition.registration_deadline, "报名截止" if edition.registration_deadline else None, registration

    def registration_start(self, edition, *, university_id=None, college_id=None):
        if not UserFacingDataPolicy.verified_record(edition):
            return None
        relations = self._usable_relations(edition.university_relations, university_id)
        scopes = ([r for r in relations if r.college_id == college_id] if college_id is not None else [],
                  [r for r in relations if r.college_id is None])
        for scoped in scopes:
            # A school/college registration stage may have only a start or only
            # a deadline. A missing start is unknown in that stage, not the
            # start of a different official stage.
            scoped = [r for r in scoped if r.notice_type != "submission_notice" and any((
                r.college_registration_start, r.internal_registration_start,
                r.college_registration_deadline, r.internal_registration_deadline))]
            if scoped:
                starts = [r.college_registration_start or r.internal_registration_start for r in scoped]
                return min((value for value in starts if value is not None), key=self._aware, default=None)
        return edition.registration_start

    def status(self, edition, *, university_id=None, college_id=None, now=None) -> str:
        if edition is None:
            return "unknown"
        registration = self.resolve_registration(edition, university_id=university_id, college_id=college_id)
        submission, _, _ = self._resolve_submission_deadline(edition, university_id=university_id, college_id=college_id)
        return edition_status(edition, now=now,
            registration_start=self.registration_start(edition, university_id=university_id, college_id=college_id),
            registration_deadline=registration.effective_deadline,
            submission_deadline=submission)

    def _resolve_submission_deadline(
        self,
        edition: CompetitionEdition,
        *,
        university_id: int | None,
        college_id: int | None,
    ) -> tuple[datetime | None, UniversityCompetitionEditionRelation | None, bool]:
        relations = self._usable_relations(edition.university_relations, university_id)
        if college_id is not None:
            college_relation = self._pick_relation(
                [relation for relation in relations if relation.college_id == college_id],
                deadline_getter=self._college_submission_deadline,
            )
            college_deadline = self._college_submission_deadline(college_relation)
            if college_deadline is not None:
                return college_deadline, college_relation, False

        university_relation = self._pick_relation(
            [relation for relation in relations if relation.college_id is None],
            deadline_getter=self._university_submission_deadline,
        )
        university_deadline = self._university_submission_deadline(university_relation)
        if university_deadline is not None:
            return university_deadline, university_relation, False
        if edition.official_submission_deadline is not None:
            return edition.official_submission_deadline, None, True
        return edition.submission_deadline, None, False

    def _usable_relations(
        self,
        relations: Iterable[UniversityCompetitionEditionRelation],
        university_id: int | None,
    ) -> list[UniversityCompetitionEditionRelation]:
        if university_id is None:
            return []
        rows = [
            relation
            for relation in relations
            if UserFacingDataPolicy.relation_action(relation)
        ]
        if university_id is not None:
            rows = [relation for relation in rows if relation.university_id == university_id]
        return rows

    def _pick_relation(
        self,
        relations: list[UniversityCompetitionEditionRelation],
        *,
        deadline_getter: object,
    ) -> UniversityCompetitionEditionRelation | None:
        getter = deadline_getter
        dated = [relation for relation in relations if getter(relation) is not None]
        if not dated:
            return relations[0] if relations else None
        return min(dated, key=lambda relation: self._aware(getter(relation)))

    def _university_registration_deadline(
        self,
        relation: UniversityCompetitionEditionRelation | None,
    ) -> datetime | None:
        if relation is None or relation.college_id is not None:
            return None
        return relation.internal_registration_deadline

    def _college_registration_deadline(
        self,
        relation: UniversityCompetitionEditionRelation | None,
    ) -> datetime | None:
        if relation is None or relation.college_id is None:
            return None
        return relation.college_registration_deadline or relation.internal_registration_deadline

    def _university_submission_deadline(
        self,
        relation: UniversityCompetitionEditionRelation | None,
    ) -> datetime | None:
        if relation is None or relation.college_id is not None:
            return None
        return relation.internal_submission_deadline

    def _college_submission_deadline(
        self,
        relation: UniversityCompetitionEditionRelation | None,
    ) -> datetime | None:
        if relation is None or relation.college_id is None:
            return None
        return relation.college_submission_deadline or relation.internal_submission_deadline

    def _read(
        self,
        *,
        official_deadline: datetime | None,
        official_submission_deadline: datetime | None,
        university_deadline: datetime | None,
        college_deadline: datetime | None,
        effective_deadline: datetime | None,
        effective_deadline_type: str,
        relation: UniversityCompetitionEditionRelation | None,
    ) -> DeadlineResolutionRead:
        return DeadlineResolutionRead(
            official_deadline=official_deadline,
            official_submission_deadline=official_submission_deadline,
            university_deadline=university_deadline,
            college_deadline=college_deadline,
            effective_deadline=effective_deadline,
            effective_deadline_type=effective_deadline_type,
            university_id=relation.university_id if relation else None,
            university_name=relation.university.name if relation and relation.university else None,
            college_id=relation.college_id if relation else None,
            college_name=relation.college.name if relation and relation.college else None,
            notice_id=relation.id if relation else None,
            notice_title=relation.notice_title if relation else None,
            notice_type=relation.notice_type if relation else None,
            source_url=relation.internal_notice_url if relation else None,
            source_name=relation.source_name if relation else None,
            source_level="LEVEL_3" if relation and relation.college_id is not None else "LEVEL_3" if relation else "LEVEL_1",
            last_verified_at=relation.last_verified_at if relation else None,
        )

    def _registration_label(self, deadline_type: str | None) -> str | None:
        return {
            "college_registration_deadline": "学院报名截止",
            "university_registration_deadline": "校内报名截止",
            "official_registration_deadline": "官方报名截止",
            "unverified": None,
        }.get(deadline_type or "unverified")

    def _submission_label(self, relation: UniversityCompetitionEditionRelation | None, is_official: bool) -> str:
        if relation and relation.college_id is not None:
            return "学院作品截止"
        if relation:
            return "校内作品截止"
        return "官方作品截止" if is_official else "作品提交截止"

    def _aware(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.max.replace(tzinfo=timezone.utc)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
