"""V0.9 school_competitions canonical layer.

Rebuilds school_competitions from the two legacy evidence tables
(competition_policy_recognitions + university_competition_edition_relations).
Original rows are never deleted; school_competitions is a derived, idempotent
read model whose unique key is (school_id, competition_id).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    College,
    Competition,
    CompetitionEdition,
    CompetitionPolicyRecognition,
    SchoolCompetition,
    UniversityCompetitionEditionRelation,
)


class SchoolCompetitionService:
    def rebuild(self, db: Session) -> dict[str, Any]:
        db.execute(delete(SchoolCompetition))
        db.flush()

        recognitions = list(
            db.execute(
                select(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.is_demo.is_(False)
                )
            ).scalars()
        )
        relations = list(
            db.execute(
                select(UniversityCompetitionEditionRelation, CompetitionEdition, College)
                .join(
                    CompetitionEdition,
                    CompetitionEdition.id
                    == UniversityCompetitionEditionRelation.competition_edition_id,
                )
                .outerjoin(
                    College,
                    College.id == UniversityCompetitionEditionRelation.college_id,
                )
                .where(UniversityCompetitionEditionRelation.is_demo.is_(False))
            ).all()
        )
        competition_ids = {
            competition.id: competition
            for competition in db.execute(
                select(Competition).where(Competition.is_demo.is_(False))
            ).scalars()
        }

        rec_by_key: dict[tuple[int, int], list[CompetitionPolicyRecognition]] = defaultdict(list)
        for recognition in recognitions:
            rec_by_key[(recognition.university_id, recognition.competition_id)].append(recognition)

        rel_by_key: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for relation, edition, college in relations:
            rel_by_key[(relation.university_id, edition.competition_id)].append(
                {
                    "relation": relation,
                    "edition": edition,
                    "college": college,
                }
            )

        keys = set(rec_by_key) | set(rel_by_key)
        created = 0
        merged = 0
        recognition_only = 0
        relation_only = 0
        conflicts: list[dict[str, Any]] = []
        recognition_ids_total = 0
        relation_ids_total = 0

        for school_id, competition_id in sorted(keys):
            competition = competition_ids.get(competition_id)
            if competition is None:
                continue
            rec_rows = rec_by_key.get((school_id, competition_id), [])
            rel_rows = rel_by_key.get((school_id, competition_id), [])
            recognition_ids_total += len(rec_rows)
            relation_ids_total += len(rel_rows)
            if rec_rows and rel_rows:
                merged += 1
            elif rec_rows:
                recognition_only += 1
            else:
                relation_only += 1

            recognition = self._latest_recognition(rec_rows) or {}
            relation_payload = self._primary_relation(rel_rows) or {}
            conflict_notes, needs_review = self._conflicts(rec_rows, rel_rows, competition)
            if conflict_notes:
                conflicts.append(
                    {
                        "school_id": school_id,
                        "competition_id": competition_id,
                        "competition_name": competition.name,
                        "notes": conflict_notes,
                    }
                )

            record_status = "school_confirmed"
            if competition.verification_status == "verified_official":
                record_status = "verified_official"
            elif competition.verification_status == "authority_confirmed":
                record_status = "authority_confirmed"

            provenance = {
                "competition_policy_recognition_ids": [row.id for row in rec_rows],
                "university_competition_edition_relation_ids": [
                    row["relation"].id for row in rel_rows
                ],
            }
            verified_at = self._verified_at(rec_rows, rel_rows)
            db.add(
                SchoolCompetition(
                    school_id=school_id,
                    competition_id=competition_id,
                    competition_edition_id=relation_payload.get("edition_id"),
                    recognition_status=recognition.get("recognition_status", "unknown")
                    if recognition
                    else "unknown",
                    school_level=recognition.get("school_level"),
                    school_category=recognition.get("school_category"),
                    participation_status=self._participation_status(rel_rows),
                    responsible_department=relation_payload.get("responsible_department"),
                    college_id=relation_payload.get("college_id"),
                    responsible_college=relation_payload.get("responsible_college"),
                    campus_registration_start=relation_payload.get("campus_registration_start"),
                    campus_registration_deadline=relation_payload.get(
                        "campus_registration_deadline"
                    ),
                    campus_selection_date=relation_payload.get("campus_selection_date"),
                    notice_url=relation_payload.get("notice_url"),
                    credit_policy=None,
                    award_policy=recognition.get("award_policy"),
                    record_status=record_status,
                    needs_review=needs_review,
                    conflict_notes=conflict_notes,
                    provenance=provenance,
                    verified_at=verified_at,
                )
            )
            created += 1

        db.flush()
        return {
            "recognition_input_rows": len(recognitions),
            "relation_input_rows": len(relations),
            "recognition_pairs": len(rec_by_key),
            "relation_pairs": len(rel_by_key),
            "school_competition_rows": created,
            "merged_rows": merged,
            "recognition_only_rows": recognition_only,
            "relation_only_rows": relation_only,
            "recognition_ids_attached": recognition_ids_total,
            "relation_ids_attached": relation_ids_total,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "needs_human_review_count": sum(1 for _ in rel_by_key if False)
            + len(conflicts),
        }

    def _latest_recognition(
        self,
        rows: list[CompetitionPolicyRecognition],
    ) -> dict[str, Any] | None:
        if not rows:
            return None
        ordered = sorted(
            rows,
            key=lambda row: ((row.year or 0), row.id),
        )
        latest = ordered[-1]
        return {
            "recognition_status": latest.recognition_status,
            "school_level": latest.recognition_level,
            "school_category": latest.usage_type,
            "award_policy": latest.award_requirement,
            "year": latest.year,
        }

    def _primary_relation(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {}
        ordered = sorted(
            rows,
            key=lambda row: ((row["edition"].year or 0), row["edition"].id),
        )
        chosen = ordered[-1]
        relation = chosen["relation"]
        edition = chosen["edition"]
        college = chosen["college"]
        deadline = relation.internal_registration_deadline
        start = relation.internal_registration_start or relation.college_registration_start
        selection_date = None
        if relation.notice_type == "internal_selection":
            selection_date = relation.internal_registration_deadline
        return {
            "edition_id": edition.id,
            "responsible_department": relation.organizing_department,
            "college_id": relation.college_id,
            "responsible_college": college.name if college else None,
            "campus_registration_start": start,
            "campus_registration_deadline": deadline,
            "campus_selection_date": selection_date,
            "notice_url": relation.internal_notice_url,
        }

    def _participation_status(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "unknown"
        notice_types = {row["relation"].notice_type for row in rows}
        if notice_types.intersection({"participation_news", "award_news"}):
            return "participated"
        return "notified"

    def _conflicts(
        self,
        rec_rows: list[CompetitionPolicyRecognition],
        rel_rows: list[dict[str, Any]],
        competition: Competition,
    ) -> tuple[str | None, bool]:
        notes: list[str] = []
        levels = {row.recognition_level for row in rec_rows if row.recognition_level}
        statuses = {row.recognition_status for row in rec_rows}
        if len(levels) > 1:
            notes.append(f"目录级别冲突: {sorted(levels)}")
        if len(statuses) > 1:
            notes.append(f"目录状态冲突: {sorted(statuses)}")
        years = {row["edition"].year for row in rel_rows}
        if len(years) > 1:
            notes.append(f"关系跨多个年份: {sorted(years)}")
        if competition.entity_type not in {"competition", "series", "track"}:
            notes.append(f"实体类型异常: {competition.entity_type}")
        return ("；".join(notes), bool(notes)) if notes else (None, False)

    def _verified_at(
        self,
        rec_rows: list[CompetitionPolicyRecognition],
        rel_rows: list[dict[str, Any]],
    ) -> datetime | None:
        values = [
            row.created_at or row.updated_at
            for row in rec_rows
            if row.created_at or row.updated_at
        ]
        for row in rel_rows:
            relation = row["relation"]
            value = relation.last_verified_at or relation.observed_at or relation.created_at
            if value:
                values.append(value)
        if not values:
            return None
        return max(values)
