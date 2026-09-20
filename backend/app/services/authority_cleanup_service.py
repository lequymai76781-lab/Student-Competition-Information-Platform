"""Targeted V1 authority cleanup / repair helpers.

Rules implemented here are conservative and evidence-driven:

1. link S/A competition-level sources to their matching edition (year or
   第X届) so edition authority is evaluated independently;
2. where an edition's ``official_registration_deadline`` is byte-identical to
   a school's campus deadline and the edition has no S/A source, the value is
   a school-copied national field: clear it and keep campus evidence;
3. fix two known legacy mis-files (comp 1 edition 17 polluted by school
   deadlines; comp 4 edition 1 with 2025 schedule stored under 2026) using
   official documents; every change writes a CompetitionFactRevision.

Nothing is deleted: original notices, school relations, fact rows and source
rows stay intact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionSource,
)
from app.services.authority_match_service import (
    extract_edition_number,
    extract_year,
    host_of,
)
from app.services.source_authority_service import authority_level_for


_SCHOOL_HOST_MARKERS = ("edu.cn", ".edu.", "edu.")


def _is_school_host(url: str | None) -> bool:
    host = host_of(url)
    return any(marker in host for marker in _SCHOOL_HOST_MARKERS) or host.endswith("cn") and (
        "university" in host or "college" in host
    )


def _values_equal(left: Any, right: Any) -> bool:
    def key(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()[:19]
        return str(value)[:19]

    return key(left) == key(right)


def _write_revision(
    db: Session,
    *,
    edition: CompetitionEdition,
    field: str,
    old_value: Any,
    new_value: Any,
    source_url: str,
    source_name: str | None,
    stamp: datetime,
    verification_status: str,
    note: str | None = None,
) -> None:
    def safe(value: Any) -> Any:
        return value.isoformat() if isinstance(value, datetime) else value

    label = source_name or ""
    if note:
        label = f"{label}｜{note}"
    db.add(
        CompetitionFactRevision(
            competition_id=edition.competition_id,
            competition_edition_id=edition.id,
            field_name=field,
            old_value=safe(old_value),
            new_value=safe(new_value),
            changed_at=stamp,
            source_url=source_url,
            source_name=label,
            verification_status=verification_status,
        )
    )


def link_sources_to_matching_editions(db: Session, *, dry_run: bool) -> list[dict[str, Any]]:
    """Link unbound S/A sources to the matching edition via year / 第X届."""
    changes: list[dict[str, Any]] = []
    sources = list(
        db.execute(
            select(CompetitionSource).where(
                CompetitionSource.competition_edition_id.is_(None),
                CompetitionSource.competition_id.is_not(None),
                CompetitionSource.is_verified.is_(True),
            )
        ).scalars()
    )
    for source in sources:
        level = source.authority_level or authority_level_for(source.source_type)
        if level not in {"S", "A"}:
            continue
        competition = source.competition
        if competition is None:
            continue
        blobs = [source.raw_title, source.source_name]
        if isinstance(source.metadata_json, dict):
            blobs.append(source.metadata_json.get("doc_number"))
        text_blob = " ".join(x for x in blobs if x)
        year = extract_year(text_blob)
        number = extract_edition_number(text_blob)
        candidates: list[CompetitionEdition] = []
        if year:
            candidates = [edition for edition in competition.editions if edition.year == year]
        if not candidates and number:
            candidates = [
                edition
                for edition in competition.editions
                if (edition.edition_number or 0) == number
                or (edition.edition_name and extract_edition_number(edition.edition_name) == number)
            ]
        if len(candidates) != 1:
            continue
        edition = candidates[0]
        changes.append(
            {
                "source_id": source.id,
                "competition_id": competition.id,
                "edition_id": edition.id,
                "year": edition.year,
                "reason": "official source title year/edition matches a single edition",
            }
        )
        if not dry_run:
            source.competition_edition_id = edition.id
    return changes


def repair_school_copied_national_deadlines(db: Session, *, dry_run: bool) -> list[dict[str, Any]]:
    """Clear national deadline fields that byte-equal a school campus deadline."""
    stamp = datetime.utcnow()
    changes: list[dict[str, Any]] = []
    rows = db.execute(
        text(
            """
            SELECT DISTINCT e.id AS edition_id, e.competition_id, e.year,
                   e.official_registration_deadline AS official_deadline,
                   rel.internal_notice_url AS notice_url
            FROM competition_editions e
            JOIN university_competition_edition_relations rel
              ON rel.competition_edition_id = e.id
            WHERE e.official_registration_deadline IS NOT NULL
              AND rel.internal_registration_deadline IS NOT NULL
              AND datetime(e.official_registration_deadline)
                  = datetime(rel.internal_registration_deadline)
              AND NOT EXISTS (
                SELECT 1 FROM competition_sources s
                WHERE s.competition_edition_id = e.id
                  AND s.authority_level IN ('S','A') AND s.is_verified = 1
              )
            """
        )
    ).mappings().all()
    for row in rows:
        edition = db.get(CompetitionEdition, row["edition_id"])
        if edition is None or edition.official_registration_deadline is None:
            continue
        official_value = edition.official_registration_deadline
        changes.append(
            {
                "edition_id": edition.id,
                "competition_id": edition.competition_id,
                "year": edition.year,
                "field": "official_registration_deadline",
                "old_value": official_value.isoformat(),
                "notice_url": row["notice_url"],
                "reason": "official field byte-equals school campus deadline and no S/A edition source exists",
            }
        )
        if not dry_run:
            _write_revision(
                db,
                edition=edition,
                field="official_registration_deadline",
                old_value=official_value,
                new_value=None,
                source_url=row["notice_url"],
                source_name="school notice (campus deadline)",
                stamp=stamp,
                verification_status="school_confirmed",
                note="校内截止时间误写入全国字段：清空全国字段，校内值保留在学校关系层",
            )
            edition.official_registration_deadline = None
    return changes


def repair_edition_source_url_to_official(db: Session, *, dry_run: bool) -> list[dict[str, Any]]:
    """Point edition.source_url to the highest S/A source when it is a school page."""
    stamp = datetime.utcnow()
    changes: list[dict[str, Any]] = []
    editions = list(db.execute(select(CompetitionEdition)).scalars())
    for edition in editions:
        official_sources = [
            source
            for source in edition.sources
            if (source.authority_level or authority_level_for(source.source_type)) in {"S", "A"}
            and source.source_url
        ]
        if not official_sources:
            continue
        official_sources.sort(key=lambda s: (s.authority_level or "D", s.id))
        best = official_sources[-1]
        current = edition.source_url
        if current and _is_school_host(current) and current.strip().rstrip("/") != best.source_url.strip().rstrip("/"):
            changes.append(
                {
                    "edition_id": edition.id,
                    "competition_id": edition.competition_id,
                    "old_source_url": current,
                    "new_source_url": best.source_url,
                    "source_id": best.id,
                }
            )
            if not dry_run:
                _write_revision(
                    db,
                    edition=edition,
                    field="source_url",
                    old_value=current,
                    new_value=best.source_url,
                    source_url=best.source_url,
                    source_name=best.source_name,
                    stamp=stamp,
                    verification_status="verified_official",
                    note="edition.source_url 从高校页面修正为最高S/A来源URL",
                )
                edition.source_url = best.source_url
    return changes


def repair_known_edition_misfiles(db: Session, *, dry_run: bool) -> list[dict[str, Any]]:
    """Fix comp1-edition-2026 and comp4-edition-2026 using official documents."""
    stamp = datetime.utcnow()
    changes: list[dict[str, Any]] = []

    # --- 中国国际大学生创新大赛（2026）edition row ---
    comp1 = db.execute(select(Competition).where(Competition.id == 1)).scalar_one_or_none()
    if comp1 is not None:
        edition = db.execute(
            select(CompetitionEdition).where(
                CompetitionEdition.competition_id == 1,
                CompetitionEdition.year == 2026,
            )
        ).scalar_one_or_none()
        moe_url = "https://www.moe.gov.cn/srcsite/A08/s5672/202607/t20260731_1445670.html"
        if edition is not None:
            planned = [
                ("edition_name", "中国国际大学生创新大赛（2026）"),
                ("registration_start", datetime(2026, 8, 10)),
                ("official_registration_deadline", datetime(2026, 9, 25, 12, 0)),
                ("source_url", moe_url),
                ("official_notice_url", moe_url),
            ]
            for field, new_value in planned:
                old_value = getattr(edition, field)
                if old_value is not None and _values_equal(old_value, new_value):
                    continue
                changes.append(
                    {
                        "edition_id": edition.id,
                        "competition_id": 1,
                        "field": field,
                        "old_value": old_value.isoformat() if isinstance(old_value, datetime) else old_value,
                        "new_value": new_value.isoformat() if isinstance(new_value, datetime) else new_value,
                        "reason": "教高函〔2026〕26号官方届次字段（旧值为高校通知来源）",
                    }
                )
                if not dry_run:
                    _write_revision(
                        db,
                        edition=edition,
                        field=field,
                        old_value=old_value,
                        new_value=new_value,
                        source_url=moe_url,
                        source_name="教育部关于举办中国国际大学生创新大赛（2026）的通知",
                        stamp=stamp,
                        verification_status="verified_official",
                        note="旧值来自高校校内通知，全国字段以教育部文件为准",
                    )
                    setattr(edition, field, new_value)

    # --- 全国大学生数学建模竞赛（2026）edition row ---
    comp4 = db.execute(select(Competition).where(Competition.id == 4)).scalar_one_or_none()
    if comp4 is not None:
        edition = db.execute(
            select(CompetitionEdition).where(
                CompetitionEdition.competition_id == 4,
                CompetitionEdition.year == 2026,
            )
        ).scalar_one_or_none()
        mcm_url = "https://www.mcm.edu.cn/html_cn/node/d6fd7a0ee8f3a3d525e30af1c365fcec.html"
        if edition is not None:
            planned = [
                ("competition_start", datetime(2026, 9, 10, 18, 0)),
                ("competition_end", datetime(2026, 9, 13, 20, 0)),
                ("source_url", mcm_url),
                ("official_notice_url", mcm_url),
            ]
            for field, new_value in planned:
                old_value = getattr(edition, field)
                if old_value is not None and _values_equal(old_value, new_value):
                    continue
                changes.append(
                    {
                        "edition_id": edition.id,
                        "competition_id": 4,
                        "field": field,
                        "old_value": old_value.isoformat() if isinstance(old_value, datetime) else old_value,
                        "new_value": new_value.isoformat() if isinstance(new_value, datetime) else new_value,
                        "reason": "2026第一次通知官方竞赛时间（旧值为2025赛程/高校页）",
                    }
                )
                if not dry_run:
                    _write_revision(
                        db,
                        edition=edition,
                        field=field,
                        old_value=old_value,
                        new_value=new_value,
                        source_url=mcm_url,
                        source_name="2026高教社杯全国大学生数学建模竞赛第一次通知",
                        stamp=stamp,
                        verification_status="verified_official",
                        note="旧值9月4-7日/8月24日截止疑为2025届赛程；2026第一次通知未给出统一报名截止",
                    )
                    setattr(edition, field, new_value)
            if edition.official_registration_deadline is not None:
                old_value = edition.official_registration_deadline
                changes.append(
                    {
                        "edition_id": edition.id,
                        "competition_id": 4,
                        "field": "official_registration_deadline",
                        "old_value": old_value.isoformat(),
                        "new_value": None,
                        "reason": "2026第一次通知未提供统一报名截止；旧值=中国科大校内截止（2026-08-24）",
                    }
                )
                if not dry_run:
                    _write_revision(
                        db,
                        edition=edition,
                        field="official_registration_deadline",
                        old_value=old_value,
                        new_value=None,
                        source_url=mcm_url,
                        source_name="2026高教社杯全国大学生数学建模竞赛第一次通知",
                        stamp=stamp,
                        verification_status="verified_official",
                        note="校内截止时间不再占用全国字段；统一截止待组委会后续通知",
                    )
                    edition.official_registration_deadline = None
    return changes


def run_cleanup(db: Session, *, dry_run: bool) -> dict[str, Any]:
    linked = link_sources_to_matching_editions(db, dry_run=dry_run)
    db.flush()
    deadline_fixes = repair_school_copied_national_deadlines(db, dry_run=dry_run)
    db.flush()
    source_url_fixes = repair_edition_source_url_to_official(db, dry_run=dry_run)
    db.flush()
    misfiles = repair_known_edition_misfiles(db, dry_run=dry_run)
    db.flush()
    return {
        "dry_run": dry_run,
        "source_edition_links": linked,
        "school_copied_deadline_fixes": deadline_fixes,
        "source_url_fixes": source_url_fixes,
        "known_edition_misfile_fixes": misfiles,
        "counts": {
            "source_edition_links": len(linked),
            "school_copied_deadline_fixes": len(deadline_fixes),
            "source_url_fixes": len(source_url_fixes),
            "known_edition_misfile_fixes": len(misfiles),
        },
    }
