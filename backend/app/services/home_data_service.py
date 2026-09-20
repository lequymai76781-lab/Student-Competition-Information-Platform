from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionPolicyRecognition,
    ConferenceEdition,
    ConferenceOpportunity,
    ConferenceSeries,
    PolicyDocument,
    UniversityCompetitionEditionRelation,
)
from app.schemas.home import (
    HomeConferenceItem,
    HomeDataRead,
    HomeDeadlineItem,
    HomeReadiness,
    HomeRecentUpdateItem,
    HomeRecognitionItem,
    HomeSection,
)


TRUSTED_STATUSES = {"verified_official", "authority_confirmed", "school_confirmed"}
ACTION_NOTICE_TYPES = {"registration_notice", "internal_selection", "submission_notice"}
RECENT_FACT_FIELDS = {
    "edition_name": "届次名称更新",
    "edition_status": "届次状态更新",
    "current_status": "赛事状态更新",
    "official_registration_deadline": "官方报名截止更新",
    "registration_deadline": "报名截止更新",
    "official_submission_deadline": "官方作品截止更新",
    "submission_deadline": "作品截止更新",
    "competition_start": "比赛开始时间更新",
    "competition_end": "比赛结束时间更新",
    "official_competition_date": "比赛日期更新",
    "official_notice_url": "官方通知更新",
    "official_registration_url": "报名入口更新",
    "official_url": "赛事官网更新",
    "source_url": "来源页面更新",
    "organizer": "主办单位更新",
    "participation_requirements": "参赛要求更新",
    "submission_requirements": "提交要求更新",
}


class HomeDataService:
    recognition_ready_schools = 10
    recognition_shippable_schools = 7
    open_registration_ready = 10
    deadline_ready = 20
    recent_update_ready = 10
    conference_ready = 10

    def build(self, db: Session, *, now: datetime | None = None, item_limit: int = 10) -> HomeDataRead:
        aware_now = self._aware(now or datetime.now(timezone.utc))
        query_now = aware_now.replace(tzinfo=None)

        recognition_section = self._recognitions(db, item_limit=item_limit)
        deadline_nodes = self._deadline_nodes(db, query_now)
        deadline_section = self._deadline_section(deadline_nodes, item_limit=item_limit)
        open_section = self._open_registration_section(deadline_nodes, item_limit=item_limit)
        recent_section = self._recent_updates(db, aware_now, item_limit=item_limit)
        conference_section = self._conferences(db, query_now, item_limit=item_limit)

        blockers = []
        if not recognition_section.readiness.shippable:
            blockers.append("当前高校认定覆盖未达到 7 所可上线下限")
        if open_section.readiness.status != "READY":
            blockers.append("开放报名赛事未达到 10 个已核验节点")
        if deadline_section.readiness.status != "READY":
            blockers.append("未来可执行截止节点未达到 20 条")
        if recent_section.readiness.status != "READY":
            blockers.append("近 30 天真实变更不足 10 条")
        if conference_section.readiness.status == "BLOCKED":
            blockers.append("未来已核验学术会议不足 3 场")
        frontend_ready = not blockers

        return HomeDataRead(
            as_of=aware_now,
            decision="FRONTEND_READY" if frontend_ready else "FRONTEND_NOT_READY",
            frontend_ready=frontend_ready,
            blockers=blockers[:3],
            current_recognitions=recognition_section,
            open_registrations=open_section,
            upcoming_deadlines=deadline_section,
            recent_updates=recent_section,
            conferences=conference_section,
        )

    def _recognitions(self, db: Session, *, item_limit: int) -> HomeSection[HomeRecognitionItem]:
        rows = list(
            db.execute(
                select(CompetitionPolicyRecognition)
                .options(
                    joinedload(CompetitionPolicyRecognition.competition),
                    joinedload(CompetitionPolicyRecognition.university),
                    joinedload(CompetitionPolicyRecognition.policy_document),
                )
                .join(PolicyDocument)
                .where(
                    CompetitionPolicyRecognition.recognition_status == "recognized",
                    CompetitionPolicyRecognition.needs_manual_review.is_(False),
                    CompetitionPolicyRecognition.is_demo.is_(False),
                    PolicyDocument.is_current.is_(True),
                    PolicyDocument.is_verified.is_(True),
                    PolicyDocument.is_demo.is_(False),
                )
            ).scalars()
        )
        rows.sort(
            key=lambda row: (
                self._sort_dt(row.policy_document.published_at),
                row.year or 0,
                row.id,
            ),
            reverse=True,
        )
        school_ids = {row.university_id for row in rows}
        status = "READY" if len(school_ids) >= self.recognition_ready_schools else "PARTIAL" if len(school_ids) >= 3 else "BLOCKED"
        shippable = len(school_ids) >= self.recognition_shippable_schools

        selected = []
        seen_school_ids = set()
        for row in rows:
            if row.university_id not in seen_school_ids:
                selected.append(row)
                seen_school_ids.add(row.university_id)
            if len(selected) >= item_limit:
                break
        if len(selected) < item_limit:
            selected_ids = {row.id for row in selected}
            selected.extend(
                [row for row in rows if row.id not in selected_ids][
                    : item_limit - len(selected)
                ]
            )

        items = [
            HomeRecognitionItem(
                recognition_id=row.id,
                competition_id=row.competition_id,
                competition_name=row.competition.name,
                university_id=row.university_id,
                university_name=row.university.name,
                recognition_level=row.recognition_level,
                usage_type=row.usage_type,
                year=row.year,
                evidence_title=row.policy_document.title,
                evidence_url=row.policy_document.attachment_url or row.policy_document.source_url,
                published_at=self._aware_or_none(row.policy_document.published_at),
            )
            for row in selected
        ]
        latest = max((row.policy_document.published_at for row in rows if row.policy_document.published_at), default=None)
        reason = (
            f"{len(school_ids)} 所高校、{len(rows)} 条当前认定；达到可上线下限，未达到 {self.recognition_ready_schools} 所 READY 目标。"
            if shippable and status != "READY"
            else f"{len(school_ids)} 所高校、{len(rows)} 条当前认定。"
        )
        return HomeSection(
            readiness=HomeReadiness(
                status=status,
                shippable=shippable,
                record_count=len(rows),
                verified_count=len(rows),
                threshold=self.recognition_ready_schools,
                reason=reason,
                last_updated_at=self._aware_or_none(latest),
                metrics={"school_count": len(school_ids), "shippable_school_threshold": self.recognition_shippable_schools},
            ),
            items=items,
        )

    def _deadline_nodes(self, db: Session, query_now: datetime) -> list[HomeDeadlineItem]:
        nodes: list[HomeDeadlineItem] = []
        editions = list(
            db.execute(
                select(CompetitionEdition)
                .options(
                    joinedload(CompetitionEdition.competition),
                    selectinload(CompetitionEdition.sources),
                )
                .where(
                    CompetitionEdition.year >= query_now.year,
                    CompetitionEdition.is_verified.is_(True),
                    CompetitionEdition.verification_status.in_(TRUSTED_STATUSES),
                )
            ).scalars()
        )
        official_fields = (
            ("official_registration_deadline", "官方报名截止", "registration"),
            ("official_submission_deadline", "官方作品截止", "submission"),
        )
        for edition in editions:
            has_national_proof = any(
                source.is_verified and source.authority_level in {"S", "A"}
                for source in edition.sources
            )
            if not has_national_proof:
                continue
            for field_name, label, action in official_fields:
                deadline = getattr(edition, field_name)
                if deadline is None or deadline < query_now:
                    continue
                source = next(
                    (
                        source
                        for source in edition.sources
                        if source.is_verified and source.authority_level in {"S", "A"}
                    ),
                    None,
                )
                source_url = (
                    source.source_url
                    if source
                    else edition.official_notice_url or edition.source_url or edition.official_url
                )
                if not source_url:
                    continue
                nodes.append(
                    HomeDeadlineItem(
                        node_id=f"edition:{edition.id}:{field_name}",
                        competition_id=edition.competition_id,
                        competition_name=edition.competition.name,
                        edition_id=edition.id,
                        edition_year=edition.year,
                        deadline=self._aware(deadline),
                        deadline_type=field_name,
                        deadline_label=label,
                        action=action,
                        scope_type="official",
                        current_status=edition.current_status,
                        source_url=source_url,
                        source_name=source.source_name if source else None,
                        verification_status=edition.verification_status,
                        last_verified_at=self._aware_or_none(edition.last_verified_at),
                    )
                )

        relations = list(
            db.execute(
                select(UniversityCompetitionEditionRelation)
                .options(
                    joinedload(UniversityCompetitionEditionRelation.university),
                    joinedload(UniversityCompetitionEditionRelation.college),
                    joinedload(UniversityCompetitionEditionRelation.competition_edition).joinedload(
                        CompetitionEdition.competition
                    ),
                )
                .where(
                    UniversityCompetitionEditionRelation.is_verified.is_(True),
                    UniversityCompetitionEditionRelation.verification_status.in_(TRUSTED_STATUSES),
                    UniversityCompetitionEditionRelation.notice_type.in_(ACTION_NOTICE_TYPES),
                )
            ).scalars()
        )
        for relation in relations:
            if relation.competition_edition.year < query_now.year:
                continue
            if relation.college_id:
                fields = (
                    (
                        "college_registration_deadline",
                        relation.college_registration_deadline or relation.internal_registration_deadline,
                        "学院报名截止",
                        "registration",
                    ),
                    (
                        "college_submission_deadline",
                        relation.college_submission_deadline or relation.internal_submission_deadline,
                        "学院作品截止",
                        "submission",
                    ),
                )
                scope_type = "college"
            else:
                fields = (
                    (
                        "university_registration_deadline",
                        relation.internal_registration_deadline,
                        "校内报名截止",
                        "registration",
                    ),
                    (
                        "university_submission_deadline",
                        relation.internal_submission_deadline,
                        "校内作品截止",
                        "submission",
                    ),
                )
                scope_type = "university"
            for field_name, deadline, label, action in fields:
                if deadline is None or deadline < query_now or not relation.internal_notice_url:
                    continue
                edition = relation.competition_edition
                nodes.append(
                    HomeDeadlineItem(
                        node_id=f"relation:{relation.id}:{field_name}",
                        competition_id=edition.competition_id,
                        competition_name=edition.competition.name,
                        edition_id=edition.id,
                        edition_year=edition.year,
                        deadline=self._aware(deadline),
                        deadline_type=field_name,
                        deadline_label=label,
                        action=action,
                        scope_type=scope_type,
                        current_status=edition.current_status,
                        university_id=relation.university_id,
                        university_name=relation.university.name,
                        college_id=relation.college_id,
                        college_name=relation.college.name if relation.college else None,
                        source_url=relation.internal_notice_url,
                        source_name=relation.source_name,
                        verification_status=relation.verification_status,
                        last_verified_at=self._aware_or_none(relation.last_verified_at),
                    )
                )
        nodes.sort(key=lambda item: (item.deadline, item.node_id))
        return nodes

    def _deadline_section(self, nodes: list[HomeDeadlineItem], *, item_limit: int) -> HomeSection[HomeDeadlineItem]:
        status = "READY" if len(nodes) >= self.deadline_ready else "PARTIAL" if len(nodes) >= 10 else "BLOCKED"
        latest = max((item.last_verified_at for item in nodes if item.last_verified_at), default=None)
        official_count = sum(item.scope_type == "official" for item in nodes)
        school_count = len(nodes) - official_count
        return HomeSection(
            readiness=HomeReadiness(
                status=status,
                shippable=status == "READY",
                record_count=len(nodes),
                verified_count=len(nodes),
                threshold=self.deadline_ready,
                reason=f"{official_count} 条官方节点、{school_count} 条校级/院级节点，均保留来源层级。",
                last_updated_at=latest,
                metrics={"official_nodes": official_count, "school_nodes": school_count},
            ),
            items=nodes[:item_limit],
        )

    def _open_registration_section(
        self,
        nodes: list[HomeDeadlineItem],
        *,
        item_limit: int,
    ) -> HomeSection[HomeDeadlineItem]:
        open_nodes = [
            item
            for item in nodes
            if item.action == "registration" and item.current_status == "registration_open"
        ]
        status = "READY" if len(open_nodes) >= self.open_registration_ready else "PARTIAL" if len(open_nodes) >= 5 else "BLOCKED"
        latest = max((item.last_verified_at for item in open_nodes if item.last_verified_at), default=None)
        return HomeSection(
            readiness=HomeReadiness(
                status=status,
                shippable=status == "READY",
                record_count=len(open_nodes),
                verified_count=len(open_nodes),
                threshold=self.open_registration_ready,
                reason="只计 current_status=registration_open 且截止时间仍在未来的已核验节点。",
                last_updated_at=latest,
                metrics={"unique_competitions": len({item.competition_id for item in open_nodes})},
            ),
            items=open_nodes[:item_limit],
        )

    def _recent_updates(
        self,
        db: Session,
        aware_now: datetime,
        *,
        item_limit: int,
    ) -> HomeSection[HomeRecentUpdateItem]:
        cutoff = (aware_now - timedelta(days=30)).replace(tzinfo=None)
        rows = list(
            db.execute(
                select(CompetitionFactRevision, Competition, CompetitionEdition)
                .join(Competition, Competition.id == CompetitionFactRevision.competition_id)
                .outerjoin(CompetitionEdition, CompetitionEdition.id == CompetitionFactRevision.competition_edition_id)
                .where(
                    CompetitionFactRevision.changed_at >= cutoff,
                    CompetitionFactRevision.verification_status.in_(TRUSTED_STATUSES),
                    CompetitionFactRevision.field_name.in_(RECENT_FACT_FIELDS),
                    CompetitionFactRevision.new_value.is_not(None),
                    Competition.is_demo.is_(False),
                )
                .order_by(CompetitionFactRevision.changed_at.desc(), CompetitionFactRevision.id.desc())
            ).all()
        )
        items = []
        seen = set()
        for revision, competition, edition in rows:
            if revision.new_value is None or revision.old_value == revision.new_value:
                continue
            key = (revision.competition_id, revision.competition_edition_id, revision.field_name)
            if key in seen:
                continue
            seen.add(key)
            title = RECENT_FACT_FIELDS[revision.field_name]
            items.append(
                HomeRecentUpdateItem(
                    update_key=f"revision:{revision.id}",
                    update_type="competition_fact_changed",
                    entity_type="competition_edition" if edition else "competition",
                    entity_id=edition.id if edition else competition.id,
                    changed_fields=[revision.field_name],
                    competition_id=competition.id,
                    competition_name=competition.name,
                    edition_id=edition.id if edition else None,
                    edition_year=edition.year if edition else None,
                    title=title,
                    field_name=revision.field_name,
                    old_value=revision.old_value,
                    new_value=revision.new_value,
                    occurred_at=self._aware(revision.changed_at),
                    source_url=revision.source_url,
                    source_name=revision.source_name,
                    verification_status=revision.verification_status,
                )
            )
        status = "READY" if len(items) >= self.recent_update_ready else "PARTIAL" if items else "BLOCKED"
        latest = max((item.occurred_at for item in items), default=None)
        return HomeSection(
            readiness=HomeReadiness(
                status=status,
                shippable=status == "READY",
                record_count=len(items),
                verified_count=len(items),
                threshold=self.recent_update_ready,
                reason="由已核验事实修订记录实时派生；同一赛事、届次、字段只保留最新一条。",
                last_updated_at=latest,
                metrics={"window_days": 30, "dedupe_key": "competition+edition+field"},
            ),
            items=items[:item_limit],
        )

    def _conferences(
        self,
        db: Session,
        query_now: datetime,
        *,
        item_limit: int,
    ) -> HomeSection[HomeConferenceItem]:
        rows = list(
            db.execute(
                select(ConferenceEdition, ConferenceSeries)
                .join(ConferenceSeries, ConferenceSeries.id == ConferenceEdition.conference_series_id)
                .where(
                    ConferenceEdition.start_date >= query_now,
                    ConferenceEdition.is_verified.is_(True),
                    ConferenceEdition.needs_review.is_(False),
                    ConferenceEdition.verification_status.in_(TRUSTED_STATUSES),
                    ConferenceSeries.is_verified.is_(True),
                    ConferenceSeries.needs_review.is_(False),
                    ConferenceSeries.is_demo.is_(False),
                )
                .order_by(ConferenceEdition.start_date, ConferenceEdition.id)
            ).all()
        )
        rows = [row for row in rows if row[0].edition_official_url or row[0].source_url or row[1].official_website]
        submission_count = len(
            list(
                db.execute(
                    select(ConferenceOpportunity.id).where(
                        ConferenceOpportunity.deadline >= query_now,
                        ConferenceOpportunity.is_verified.is_(True),
                        ConferenceOpportunity.needs_review.is_(False),
                        ConferenceOpportunity.verification_status.in_(TRUSTED_STATUSES),
                    )
                ).scalars()
            )
        )
        items = [
            HomeConferenceItem(
                series_id=series.id,
                series_name=series.name,
                short_name=series.short_name,
                edition_id=edition.id,
                edition_name=edition.edition_name,
                edition_year=edition.year,
                start_date=self._aware(edition.start_date),
                end_date=self._aware_or_none(edition.end_date),
                location=edition.location,
                discipline=series.discipline,
                is_international=series.is_international,
                edition_status=edition.edition_status,
                official_url=edition.edition_official_url or edition.source_url or series.official_website,
                verification_status=edition.verification_status,
                last_verified_at=self._aware_or_none(edition.last_verified_at),
            )
            for edition, series in rows[:item_limit]
        ]
        status = "READY" if len(rows) >= self.conference_ready else "PARTIAL" if len(rows) >= 3 else "BLOCKED"
        latest = max((edition.last_verified_at for edition, _ in rows if edition.last_verified_at), default=None)
        return HomeSection(
            readiness=HomeReadiness(
                status=status,
                shippable=status != "BLOCKED",
                record_count=len(rows),
                verified_count=len(rows),
                threshold=self.conference_ready,
                reason="基础近期会议浏览已可用；投稿机会单独计数，不把会议日期冒充投稿截止。",
                last_updated_at=self._aware_or_none(latest),
                metrics={"future_submission_opportunities": submission_count},
            ),
            items=items,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _aware_or_none(self, value: datetime | None) -> datetime | None:
        return self._aware(value) if value else None

    @staticmethod
    def _sort_dt(value: datetime | None) -> float:
        if value is None:
            return 0.0
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.timestamp()
