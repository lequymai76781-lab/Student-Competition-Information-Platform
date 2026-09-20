"""Audit the evidence-backed homepage data gates for DATA_READINESS_SPRINT_01.

This is read-only for business tables.  It writes one reproducible JSON report
under data/reports and exits non-zero only when a required homepage gate or a
hard data-integrity invariant fails.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.models import (
    CandidateCompetition,
    CompetitionPolicyRecognition,
    ConferenceEdition,
    ConferenceOpportunity,
    ConferenceSeries,
    PolicyDocument,
)
from app.services.home_data_service import HomeDataService


REPORT = PROJECT_ROOT / "data" / "reports" / "data_readiness_sprint_01_audit.json"
TRUSTED = {"verified_official", "authority_confirmed", "school_confirmed"}


def scalar_int(db, statement) -> int:
    return int(db.scalar(statement) or 0)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def main() -> None:
    now = datetime.now(timezone.utc)
    query_now = now.replace(tzinfo=None)
    service = HomeDataService()
    checks: list[dict[str, object]] = []

    def check(rule_id: str, description: str, passed: bool, *, severity: str = "fail", detail: object = None) -> None:
        status = "pass" if passed else severity
        checks.append(
            {
                "rule_id": rule_id,
                "description": description,
                "status": status,
                "detail": detail,
            }
        )

    with SessionLocal() as db:
        home = service.build(db, now=now)
        deadline_nodes = service._deadline_nodes(db, query_now)

        current_where = (
            CompetitionPolicyRecognition.recognition_status == "recognized",
            CompetitionPolicyRecognition.needs_manual_review.is_(False),
            CompetitionPolicyRecognition.is_demo.is_(False),
            PolicyDocument.is_current.is_(True),
            PolicyDocument.is_verified.is_(True),
            PolicyDocument.is_demo.is_(False),
        )
        current_count = scalar_int(
            db,
            select(func.count())
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(*current_where),
        )
        current_school_count = scalar_int(
            db,
            select(func.count(func.distinct(CompetitionPolicyRecognition.university_id)))
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(*current_where),
        )
        current_source_count = scalar_int(
            db,
            select(func.count(func.distinct(PolicyDocument.id)))
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(*current_where),
        )
        historical_where = (
            CompetitionPolicyRecognition.recognition_status.in_(["recognized", "expired"]),
            CompetitionPolicyRecognition.needs_manual_review.is_(False),
            CompetitionPolicyRecognition.is_demo.is_(False),
            PolicyDocument.is_current.is_(False),
            PolicyDocument.is_verified.is_(True),
            PolicyDocument.is_demo.is_(False),
        )
        historical_count = scalar_int(
            db,
            select(func.count())
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(*historical_where),
        )
        historical_school_count = scalar_int(
            db,
            select(func.count(func.distinct(CompetitionPolicyRecognition.university_id)))
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(*historical_where),
        )
        carry_over_candidates = [
            item
            for item in db.execute(select(CandidateCompetition)).scalars()
            if (item.metadata_json or {}).get("batch") == "RECOGNITION_BATCH_01"
        ]
        unresolved = [
            item
            for item in carry_over_candidates
            if item.needs_manual_review or item.normalized_competition_id is None
        ]

        registration_nodes = [item for item in deadline_nodes if item.action == "registration"]
        submission_nodes = [item for item in deadline_nodes if item.action == "submission"]
        open_registration_nodes = [
            item
            for item in registration_nodes
            if item.current_status == "registration_open"
        ]
        official_nodes = [item for item in deadline_nodes if item.scope_type == "official"]
        school_nodes = [item for item in deadline_nodes if item.scope_type != "official"]
        deadline_windows = {
            str(days): sum(item.deadline <= now + timedelta(days=days) for item in deadline_nodes)
            for days in (30, 60, 90)
        }
        deadline_sources = {item.source_url for item in deadline_nodes}

        recent = service._recent_updates(db, now, item_limit=10_000)
        recent_sources = {item.source_url for item in recent.items}
        conference = service._conferences(db, query_now, item_limit=10_000)
        conference_sources = {item.official_url for item in conference.items}

        conference_series = list(
            db.execute(select(ConferenceSeries).where(ConferenceSeries.is_demo.is_(False))).scalars()
        )
        conference_total = len(conference_series)
        conference_with_website = sum(bool(item.official_website) for item in conference_series)
        ccf_count = sum(
            any("CCF" in json.dumps(entry, ensure_ascii=False).upper() for entry in (item.external_classifications or []))
            for item in conference_series
        )
        cfp_count = scalar_int(
            db,
            select(func.count())
            .select_from(ConferenceEdition)
            .where(ConferenceEdition.call_for_papers_url.is_not(None)),
        )
        edition_deadlines = list(
            db.execute(
                select(ConferenceEdition.paper_deadline).where(
                    ConferenceEdition.paper_deadline.is_not(None),
                    ConferenceEdition.is_verified.is_(True),
                    ConferenceEdition.needs_review.is_(False),
                    ConferenceEdition.verification_status.in_(TRUSTED),
                )
            ).scalars()
        )
        opportunity_deadlines = list(
            db.execute(
                select(ConferenceOpportunity.deadline).where(
                    ConferenceOpportunity.deadline.is_not(None),
                    ConferenceOpportunity.is_verified.is_(True),
                    ConferenceOpportunity.needs_review.is_(False),
                    ConferenceOpportunity.verification_status.in_(TRUSTED),
                )
            ).scalars()
        )
        all_submission_deadlines = [
            value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            for value in edition_deadlines + opportunity_deadlines
        ]
        future_submission_deadlines = [value for value in all_submission_deadlines if value >= now]
        submission_windows = {
            str(days): sum(value <= now + timedelta(days=days) for value in future_submission_deadlines)
            for days in (30, 60, 90)
        }

        missing_current_urls = scalar_int(
            db,
            select(func.count())
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(*current_where, PolicyDocument.source_url == "", PolicyDocument.attachment_url.is_(None)),
        )
        duplicate_recognitions = len(
            db.execute(
                text(
                    "SELECT policy_document_id, competition_id, usage_type, evidence_hash, COUNT(*) "
                    "FROM competition_policy_recognitions "
                    "GROUP BY policy_document_id, competition_id, usage_type, evidence_hash HAVING COUNT(*) > 1"
                )
            ).all()
        )
        duplicate_competitions = len(
            db.execute(
                text(
                    "SELECT lower(trim(name)), COUNT(*) FROM competitions WHERE is_demo = 0 "
                    "GROUP BY lower(trim(name)) HAVING COUNT(*) > 1"
                )
            ).all()
        )
        recognition_document_mismatch = scalar_int(
            db,
            select(func.count())
            .select_from(CompetitionPolicyRecognition)
            .join(PolicyDocument)
            .where(CompetitionPolicyRecognition.university_id != PolicyDocument.university_id),
        )
        orphan_count = scalar_int(
            db,
            text(
                "SELECT "
                "(SELECT COUNT(*) FROM competition_policy_recognitions r "
                " LEFT JOIN competitions c ON c.id=r.competition_id "
                " LEFT JOIN policy_documents d ON d.id=r.policy_document_id "
                " LEFT JOIN universities u ON u.id=r.university_id "
                " WHERE c.id IS NULL OR d.id IS NULL OR u.id IS NULL) + "
                "(SELECT COUNT(*) FROM competition_editions e LEFT JOIN competitions c ON c.id=e.competition_id "
                " WHERE c.id IS NULL) + "
                "(SELECT COUNT(*) FROM university_competition_edition_relations r "
                " LEFT JOIN universities u ON u.id=r.university_id "
                " LEFT JOIN competition_editions e ON e.id=r.competition_edition_id "
                " WHERE u.id IS NULL OR e.id IS NULL)"
            ),
        )
        stale_cross_year = scalar_int(
            db,
            text(
                "SELECT COUNT(*) FROM competition_editions e JOIN competitions c ON c.id=e.competition_id "
                "WHERE c.name='中国国际大学生创新大赛' AND e.year IN (2024, 2025) "
                "AND e.official_registration_deadline >= '2026-01-01'"
            ),
        )
        campus_later_than_national = scalar_int(
            db,
            text(
                "SELECT COUNT(*) FROM competition_editions "
                "WHERE official_registration_deadline IS NOT NULL "
                "AND university_registration_deadline IS NOT NULL "
                "AND university_registration_deadline > official_registration_deadline"
            ),
        )
        contaminated_recognitions = sum(
            1
            for recognition, document in db.execute(
                select(CompetitionPolicyRecognition, PolicyDocument)
                .join(PolicyDocument)
                .where(CompetitionPolicyRecognition.recognition_status.in_(["recognized", "expired"]))
            ).all()
            if (document.metadata_json or {}).get("evidence_type") in {"notification", "participation"}
        )

        check(
            "recognition_shippable_coverage",
            "Current Recognition 至少覆盖 7 所高校",
            current_school_count >= 7,
            detail={"schools": current_school_count, "recognitions": current_count},
        )
        check(
            "recognition_ready_target",
            "Current Recognition 达到 10 所 READY 目标",
            current_school_count >= 10,
            severity="warn",
            detail={"schools": current_school_count},
        )
        check("recognition_unresolved", "Recognition Batch 01 遗留候选已逐条处置", not unresolved, detail=len(unresolved))
        check("open_registration_gate", "开放报名已核验节点至少 10 条", home.open_registrations.readiness.record_count >= 10, detail=home.open_registrations.readiness.record_count)
        check("future_deadline_gate", "未来可行动截止节点至少 20 条", len(deadline_nodes) >= 20, detail=len(deadline_nodes))
        check("recent_update_gate", "近 30 天真实变更至少 10 条", recent.readiness.record_count >= 10, detail=recent.readiness.record_count)
        check("conference_browse_gate", "未来已核验会议至少 3 场", conference.readiness.record_count >= 3, detail=conference.readiness.record_count)
        check(
            "conference_submission_depth",
            "未来会议投稿截止足以形成复杂截稿模块",
            len(future_submission_deadlines) >= 10,
            severity="warn",
            detail=len(future_submission_deadlines),
        )
        check("orphan_relations", "首页相关核心关系不存在孤儿记录", orphan_count == 0, detail=orphan_count)
        check("duplicate_competitions", "无精确同名重复赛事实体", duplicate_competitions == 0, detail=duplicate_competitions)
        check("duplicate_recognitions", "无重复 Recognition 证据键", duplicate_recognitions == 0, detail=duplicate_recognitions)
        check("recognition_document_school_match", "Recognition 高校与证据文件高校一致", recognition_document_mismatch == 0, detail=recognition_document_mismatch)
        check("current_recognition_source_urls", "Current Recognition 均有证据 URL", missing_current_urls == 0, detail=missing_current_urls)
        check("deadline_source_urls", "未来截止节点均有证据 URL", all(item.source_url for item in deadline_nodes), detail=len(deadline_sources))
        check("recent_update_source_urls", "最近更新均有证据 URL", all(item.source_url for item in recent.items), detail=len(recent_sources))
        check("conference_source_urls", "近期会议均有官网或证据 URL", all(item.official_url for item in conference.items), detail=len(conference_sources))
        check("campus_later_than_national", "校内截止不晚于全国截止", campus_later_than_national == 0, detail=campus_later_than_national)
        check("stale_cross_year_deadlines", "历史届次未复制 2026 截止时间", stale_cross_year == 0, detail=stale_cross_year)
        check("recognition_evidence_semantics", "通知/参赛新闻未误升为 Recognition", contaminated_recognitions == 0, detail=contaminated_recognitions)
        check("frontend_ready", "首页最低数据产品条件全部满足", home.frontend_ready, detail=home.blockers)

        summary = {
            "pass": sum(item["status"] == "pass" for item in checks),
            "warn": sum(item["status"] == "warn" for item in checks),
            "fail": sum(item["status"] == "fail" for item in checks),
        }
        report = {
            "batch": "DATA_READINESS_SPRINT_01",
            "generated_at": now.isoformat(),
            "decision": "FRONTEND_READY" if home.frontend_ready else "FRONTEND_NOT_READY",
            "frontend_ready": home.frontend_ready,
            "blockers": home.blockers,
            "recognition": {
                "current": current_count,
                "current_schools": current_school_count,
                "current_documents": current_source_count,
                "historical": historical_count,
                "historical_schools": historical_school_count,
                "carry_over_candidates": len(carry_over_candidates),
                "unresolved": len(unresolved),
                "status": home.current_recognitions.readiness.status,
                "shippable": home.current_recognitions.readiness.shippable,
                "latest": iso(home.current_recognitions.readiness.last_updated_at),
            },
            "deadlines": {
                "actionable_future": len(deadline_nodes),
                "registration": len(registration_nodes),
                "submission": len(submission_nodes),
                "official": len(official_nodes),
                "school_or_college": len(school_nodes),
                "open_registration": home.open_registrations.readiness.record_count,
                "open_registration_source_urls": len({item.source_url for item in open_registration_nodes}),
                "trusted_source_urls": len(deadline_sources),
                "within_days": deadline_windows,
                "latest": iso(home.upcoming_deadlines.readiness.last_updated_at),
            },
            "recent_updates": {
                "count_30_days": recent.readiness.record_count,
                "trusted_source_urls": len({item.source_url for item in recent.items}),
                "derivation": "competition_fact_revisions",
                "latest": iso(recent.readiness.last_updated_at),
            },
            "conferences": {
                "series_total": conference_total,
                "series_with_website": conference_with_website,
                "future_verified": conference.readiness.record_count,
                "cfp_url_count": cfp_count,
                "edition_submission_deadlines": len(edition_deadlines),
                "opportunity_deadlines": len(opportunity_deadlines),
                "future_submission_deadlines": len(future_submission_deadlines),
                "future_submission_within_days": submission_windows,
                "ccf_classified_series": ccf_count,
                "trusted_source_urls": len(conference_sources),
                "latest": iso(conference.readiness.last_updated_at),
            },
            "homepage_sections": {
                "current_recognitions": home.current_recognitions.readiness.model_dump(mode="json"),
                "open_registrations": home.open_registrations.readiness.model_dump(mode="json"),
                "upcoming_deadlines": home.upcoming_deadlines.readiness.model_dump(mode="json"),
                "recent_updates": home.recent_updates.readiness.model_dump(mode="json"),
                "conferences": home.conferences.readiness.model_dump(mode="json"),
            },
            "quality_summary": summary,
            "checks": checks,
        }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if summary["fail"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
