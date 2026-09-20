"""Import the reviewed RECOGNITION_BATCH_01 policy-document evidence.

This batch intentionally does not run or change discovery. It only imports
named competitions from reviewed official university documents, and it never
creates Competition entities from a policy-name match.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, or_, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.crawler.parsers.pdf_parser import PdfParser
from app.database.session import SessionLocal
from app.models import (
    CandidateCompetition,
    College,
    Competition,
    CompetitionFactRevision,
    CompetitionPolicyRecognition,
    CompetitionSource,
    PolicyAttachment,
    PolicyDocument,
    SchoolCompetition,
    University,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.school_competition_service import SchoolCompetitionService
from app.services.source_authority_service import authority_level_for


SEED = PROJECT_ROOT / "data" / "seeds" / "recognition_batch_01.json"
TARGETS = PROJECT_ROOT / "data" / "seeds" / "recognition_batch_01_targets.json"
REPORT = PROJECT_ROOT / "data" / "reports" / "recognition_batch_01_import.json"
UNRESOLVED_REPORT = PROJECT_ROOT / "data" / "reports" / "unresolved_recognition_leads.json"

ALLOWED_EVIDENCE_TYPES = {
    "competition_catalog",
    "competition_classification",
    "innovation_credit",
    "competition_reward",
    "recommendation_catalog",
}
VALIDITY_TO_RECOGNITION_STATUS = {
    "current_recognition": "recognized",
    "historical_recognition": "expired",
    "unknown_validity": "uncertain",
}


def recognition_status_for(validity_status: str) -> str:
    try:
        return VALIDITY_TO_RECOGNITION_STATUS[validity_status]
    except KeyError as exc:
        raise ValueError(f"unsupported validity_status: {validity_status}") from exc


def is_recognition_evidence(evidence_type: str | None) -> bool:
    return bool(evidence_type and evidence_type in ALLOWED_EVIDENCE_TYPES)


def preserve_school_specific_level(level: str | None) -> str | None:
    """Return the issuing school's label verbatim; never cross-school score it."""
    return level.strip() if level else None


def main() -> None:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc)
    before = database_snapshot()
    parsed_documents: dict[str, dict[str, Any]] = {}
    import_rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    with SessionLocal() as db:
        update_target_statuses(db, targets, stamp)
        normalizer = CompetitionNormalizationService()
        parser = PdfParser()
        for document_seed in seed["documents"]:
            document, parsed = upsert_document(db, document_seed, parser, stamp)
            parsed_documents[document_seed["key"]] = parsed
            for row in document_seed.get("rows", []):
                outcome = import_recognition_row(
                    db,
                    normalizer=normalizer,
                    document=document,
                    document_seed=document_seed,
                    row=row,
                    stamp=stamp,
                )
                import_rows.append(outcome)
                if outcome["status"] != "imported":
                    unresolved.append(outcome)
            for row in document_seed.get("unresolved_rows", []):
                unresolved.append(
                    import_unresolved_row(
                        db,
                        normalizer=normalizer,
                        document=document,
                        document_seed=document_seed,
                        row=row,
                    )
                )

        deadline_fix = repair_known_deadline_anomaly(db, stamp)
        db.flush()
        quality_refresh = CompetitionIntelligenceService().refresh_all(db, now=stamp)
        school_read_model = SchoolCompetitionService().rebuild(db)
        db.commit()

        audit = audit_imported_recognitions(
            db,
            seed=seed,
            parsed_documents=parsed_documents,
        )

    after = database_snapshot()
    report = {
        "batch": seed["batch"],
        "generated_at": stamp.isoformat(),
        "targets": Counter(row["result"] for row in targets["targets"]),
        "before": before,
        "after": after,
        "delta": {key: after[key] - before.get(key, 0) for key in after},
        "documents": [document_summary(row) for row in seed["documents"]],
        "import": {
            "attempted": len(import_rows),
            "imported": sum(row["status"] == "imported" for row in import_rows),
            "unresolved": len(unresolved),
            "new_competitions": after["competitions"] - before["competitions"],
            "normalization_methods": dict(
                Counter(row.get("normalization_method") for row in import_rows if row.get("normalization_method"))
            ),
        },
        "validity": dict(Counter(row["validity_status"] for row in import_rows if row["status"] == "imported")),
        "levels": dict(Counter(row["school_specific_level"] for row in import_rows if row["status"] == "imported")),
        "deadline_fix": deadline_fix,
        "quality_refresh": quality_refresh,
        "school_read_model": school_read_model,
        "audit": audit,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    UNRESOLVED_REPORT.write_text(
        json.dumps(
            {"batch": seed["batch"], "generated_at": stamp.isoformat(), "items": unresolved},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def update_target_statuses(db, targets: dict[str, Any], stamp: datetime) -> None:
    for item in targets["targets"]:
        university = db.execute(select(University).where(University.name == item["school"])).scalar_one()
        university.policy_crawl_started_at = stamp
        university.last_policy_crawl_at = stamp
        university.policy_crawl_status = item["result"]
        if item["result"] == "success":
            university.policy_crawl_error = None
        else:
            university.policy_crawl_error = item["possible_policy_source"]


def upsert_document(
    db,
    seed: dict[str, Any],
    parser: PdfParser,
    stamp: datetime,
) -> tuple[PolicyDocument, dict[str, Any]]:
    if not is_recognition_evidence(seed.get("evidence_type")):
        raise ValueError(f'{seed["key"]}: notification/participation is not Recognition evidence')
    local_path = PROJECT_ROOT / seed["local_path"]
    if not local_path.is_file():
        raise FileNotFoundError(local_path)
    parsed = parser.parse(local_path)
    if parsed.error or not parsed.text or parsed.needs_ocr:
        raise ValueError(f'{seed["key"]}: PDF parsing failed: {parsed.error or "OCR required"}')
    compact_text = compact(parsed.text)
    missing_terms = [term for term in seed["check_terms"] if compact(term) not in compact_text]
    if missing_terms:
        raise ValueError(f'{seed["key"]}: PDF evidence terms missing: {missing_terms}')

    university = db.execute(select(University).where(University.name == seed["school"])).scalar_one()
    college = upsert_college(db, university, seed) if seed.get("college") else None
    file_hash = sha256_file(local_path)
    document = db.execute(
        select(PolicyDocument).where(
            or_(
                PolicyDocument.document_hash == file_hash,
                PolicyDocument.attachment_url == seed["evidence_url"],
            )
        )
    ).scalar_one_or_none()
    payload = {
        "university_id": university.id,
        "college_id": college.id if college else None,
        "scope_type": seed["scope_type"],
        "title": seed["title"],
        "policy_type": seed["policy_type"],
        "year": seed["year"],
        "latest_available_year": seed["effective_year"],
        "publisher": seed["publisher"],
        "source_url": seed["source_page_url"],
        "attachment_url": seed["evidence_url"],
        "original_filename": local_path.name,
        "official_domain": seed["official_domain"],
        "authority_level": "A2",
        "published_at": parse_datetime(seed.get("published_at")),
        "effective_from": parse_datetime(seed.get("effective_from")),
        "effective_until": parse_datetime(seed.get("effective_until")),
        "content_text": parsed.text,
        "document_hash": file_hash,
        "is_current": bool(seed["is_current"]),
        "is_verified": True,
        "verification_status": "official_domain_verified",
        "parser_type": parsed.parser_type,
        "source_type": "college" if college else "university",
        "is_demo": False,
        "metadata_json": {
            "batch": "RECOGNITION_BATCH_01",
            "document_key": seed["key"],
            "document_number": seed.get("document_number"),
            "evidence_type": seed["evidence_type"],
            "effective_year": seed["effective_year"],
            "validity_status": seed["validity_status"],
            "validity_reason": seed["validity_reason"],
            "verified_at": stamp.isoformat(),
            "page_count": parsed.page_count,
            "local_path": seed["local_path"],
        },
    }
    if document is None:
        document = PolicyDocument(**payload)
        db.add(document)
        db.flush()
    else:
        for key, value in payload.items():
            setattr(document, key, value)

    attachment = db.execute(
        select(PolicyAttachment).where(PolicyAttachment.source_url == seed["evidence_url"])
    ).scalar_one_or_none()
    attachment_payload = {
        "policy_document_id": document.id,
        "university_id": university.id,
        "filename": local_path.name,
        "content_type": "application/pdf",
        "file_extension": ".pdf",
        "file_hash": file_hash,
        "file_size": local_path.stat().st_size,
        "parse_status": "parsed",
        "parsed_at": stamp,
        "text_content": parsed.text,
        "error_message": None,
        "is_demo": False,
        "metadata_json": {
            "batch": "RECOGNITION_BATCH_01",
            "document_key": seed["key"],
            "page_count": parsed.page_count,
            "parser_type": parsed.parser_type,
            "local_path": seed["local_path"],
        },
    }
    if attachment is None:
        db.add(PolicyAttachment(source_url=seed["evidence_url"], **attachment_payload))
    else:
        for key, value in attachment_payload.items():
            setattr(attachment, key, value)
    db.flush()
    return document, {"text": parsed.text, "page_count": parsed.page_count, "file_hash": file_hash}


def upsert_college(db, university: University, seed: dict[str, Any]) -> College:
    college = db.execute(
        select(College).where(College.university_id == university.id, College.name == seed["college"])
    ).scalar_one_or_none()
    if college is None:
        college = College(
            university_id=university.id,
            name=seed["college"],
            official_website=seed["source_page_url"],
            official_domain=urlparse(seed["source_page_url"]).hostname,
            source_url=seed["source_page_url"],
            is_verified=True,
            is_demo=False,
        )
        db.add(college)
        db.flush()
    return college


def import_recognition_row(
    db,
    *,
    normalizer: CompetitionNormalizationService,
    document: PolicyDocument,
    document_seed: dict[str, Any],
    row: dict[str, Any],
    stamp: datetime,
) -> dict[str, Any]:
    normalization = normalizer.normalize(db, row["raw_name"])
    safe_match = bool(
        normalization.competition
        and not normalization.needs_manual_review
        and normalization.confidence >= 0.88
    )
    candidate = upsert_candidate(
        db,
        document=document,
        row=row,
        normalization=normalization,
        needs_manual_review=not safe_match,
        reason=normalization.reason,
    )
    outcome = {
        "document_key": document_seed["key"],
        "school": document_seed["school"],
        "raw_name": row["raw_name"],
        "canonical_name": normalization.normalized_name,
        "school_specific_level": preserve_school_specific_level(row.get("school_specific_level")),
        "validity_status": document_seed["validity_status"],
        "normalization_method": normalization.method,
        "confidence": normalization.confidence,
        "candidate_id": candidate.id,
        "status": "imported" if safe_match else "unresolved",
        "reason": normalization.reason,
    }
    if not safe_match:
        return outcome

    competition = normalization.competition
    evidence_text = evidence_text_for(document_seed, row, competition.name)
    evidence_hash = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
    recognition = db.execute(
        select(CompetitionPolicyRecognition).where(
            CompetitionPolicyRecognition.policy_document_id == document.id,
            CompetitionPolicyRecognition.competition_id == competition.id,
            CompetitionPolicyRecognition.usage_type == row["usage_type"],
            CompetitionPolicyRecognition.evidence_hash == evidence_hash,
        )
    ).scalar_one_or_none()
    payload = {
        "university_id": document.university_id,
        "college_id": document.college_id,
        "year": document.year,
        "recognition_status": recognition_status_for(document_seed["validity_status"]),
        "recognition_level": preserve_school_specific_level(row.get("school_specific_level")),
        "award_requirement": None,
        "score_text": None,
        "evidence_text": evidence_text,
        "evidence_hash": evidence_hash,
        "evidence_page": row["page"],
        "evidence_section": row["row"],
        "confidence": normalization.confidence,
        "needs_manual_review": False,
        "is_demo": False,
    }
    if recognition is None:
        recognition = CompetitionPolicyRecognition(
            competition_id=competition.id,
            policy_document_id=document.id,
            usage_type=row["usage_type"],
            **payload,
        )
        db.add(recognition)
    else:
        for key, value in payload.items():
            setattr(recognition, key, value)
    upsert_source(db, competition, document, document_seed, row, evidence_text, stamp)
    db.flush()
    outcome["recognition_id"] = recognition.id
    return outcome


def import_unresolved_row(
    db,
    *,
    normalizer: CompetitionNormalizationService,
    document: PolicyDocument,
    document_seed: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    normalization = normalizer.normalize(db, row["raw_name"])
    candidate = upsert_candidate(
        db,
        document=document,
        row=row,
        normalization=normalization,
        needs_manual_review=True,
        reason=row["reason"],
    )
    return {
        "document_key": document_seed["key"],
        "school": document_seed["school"],
        "raw_name": row["raw_name"],
        "canonical_name": normalization.normalized_name,
        "school_specific_level": preserve_school_specific_level(row.get("school_specific_level")),
        "validity_status": document_seed["validity_status"],
        "normalization_method": normalization.method,
        "confidence": normalization.confidence,
        "candidate_id": candidate.id,
        "status": "unresolved",
        "reason": row["reason"],
    }


def upsert_candidate(
    db,
    *,
    document: PolicyDocument,
    row: dict[str, Any],
    normalization,
    needs_manual_review: bool,
    reason: str,
) -> CandidateCompetition:
    candidate = db.execute(
        select(CandidateCompetition).where(
            CandidateCompetition.policy_document_id == document.id,
            CandidateCompetition.table_row == row["row"],
            CandidateCompetition.raw_name == row["raw_name"],
        )
    ).scalar_one_or_none()
    payload = {
        "university_id": document.university_id,
        "college_id": document.college_id,
        "raw_category": row.get("raw_category"),
        "raw_level": preserve_school_specific_level(row.get("school_specific_level")),
        "raw_award": None,
        "raw_score": None,
        "evidence_text": f'{document.title} 第{row["page"]}页 第{row["row"]}项：{row["raw_name"]}',
        "page_number": row["page"],
        "source_url": document.attachment_url or document.source_url,
        "confidence": normalization.confidence,
        "normalization_status": normalization.method,
        "normalized_competition_id": normalization.competition.id if normalization.competition and not needs_manual_review else None,
        "needs_manual_review": needs_manual_review,
        "is_demo": False,
        "metadata_json": {"batch": "RECOGNITION_BATCH_01", "normalization_reason": reason},
    }
    if candidate is None:
        candidate = CandidateCompetition(
            policy_document_id=document.id,
            raw_name=row["raw_name"],
            table_row=row["row"],
            **payload,
        )
        db.add(candidate)
    else:
        for key, value in payload.items():
            setattr(candidate, key, value)
    db.flush()
    return candidate


def upsert_source(
    db,
    competition: Competition,
    document: PolicyDocument,
    document_seed: dict[str, Any],
    row: dict[str, Any],
    evidence_text: str,
    stamp: datetime,
) -> None:
    source_url = document_seed["evidence_url"]
    source = db.execute(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == source_url,
        )
    ).scalar_one_or_none()
    source_type = "university_policy" if document.scope_type == "university" else "college_official_notice"
    payload = {
        "source_type": source_type,
        "authority_level": authority_level_for(source_type),
        "source_name": document.publisher,
        "source_platform": "university_official",
        "published_at": document.published_at,
        "crawled_at": stamp,
        "retrieved_at": stamp,
        "is_official": True,
        "is_verified": True,
        "credibility_score": 95 if document.scope_type == "university" else 90,
        "reliability_tier": 2 if document.scope_type == "university" else 3,
        "verification_status": "school_confirmed",
        "raw_title": document.title,
        "raw_content": evidence_text,
        "content_hash": document.document_hash,
        "metadata_json": {
            "batch": "RECOGNITION_BATCH_01",
            "policy_document_id": document.id,
            "evidence_type": document_seed["evidence_type"],
            "validity_status": document_seed["validity_status"],
            "effective_year": document_seed["effective_year"],
            "school_specific_level": preserve_school_specific_level(row.get("school_specific_level")),
            "evidence_page": row["page"],
            "source_page_url": document_seed["source_page_url"],
            "verified_at": stamp.isoformat(),
        },
        "is_demo": False,
    }
    if source is None:
        db.add(CompetitionSource(competition_id=competition.id, source_url=source_url, **payload))
    else:
        for key, value in payload.items():
            setattr(source, key, value)


def repair_known_deadline_anomaly(db, stamp: datetime) -> dict[str, Any]:
    competition = db.execute(
        select(Competition).where(Competition.name == "中国首届“新域新质”创新大赛")
    ).scalar_one_or_none()
    if competition is None:
        return {"status": "not_found", "changes": []}
    edition = next((row for row in competition.editions if row.year == 2026), None)
    if edition is None:
        return {"status": "not_found", "changes": []}
    has_national_proof = any(
        source.is_verified and (source.authority_level or authority_level_for(source.source_type)) in {"S", "A"}
        for source in edition.sources
    )
    if has_national_proof:
        return {"status": "skipped_national_proof_exists", "changes": []}

    changes: list[dict[str, Any]] = []
    source_url = edition.source_url or "https://www.xyxzds.com/"
    for field in ("registration_deadline", "official_registration_deadline", "university_registration_deadline"):
        old_value = getattr(edition, field)
        if old_value is None:
            continue
        changes.append({"scope": "edition", "field": field, "old_value": old_value.isoformat(), "new_value": None})
        if not revision_exists(db, edition.id, field, old_value):
            db.add(
                CompetitionFactRevision(
                    competition_id=competition.id,
                    competition_edition_id=edition.id,
                    field_name=field,
                    old_value=old_value.isoformat(),
                    new_value=None,
                    changed_at=stamp,
                    source_url=source_url,
                    source_name="RECOGNITION_BATCH_01 deadline audit",
                    verification_status="needs_manual_review",
                )
            )
        setattr(edition, field, None)
    edition.current_status = "unknown"
    edition.verification_status = "needs_manual_review"
    edition.is_verified = False
    edition.freshness_status = "needs_review"

    relations = list(
        db.execute(
            select(UniversityCompetitionEditionRelation).where(
                UniversityCompetitionEditionRelation.competition_edition_id == edition.id,
                or_(
                    UniversityCompetitionEditionRelation.internal_registration_deadline.is_not(None),
                    UniversityCompetitionEditionRelation.official_registration_deadline.is_not(None),
                ),
            )
        ).scalars()
    )
    for relation in relations:
        previous = {
            "internal_registration_deadline": relation.internal_registration_deadline.isoformat()
            if relation.internal_registration_deadline else None,
            "official_registration_deadline": relation.official_registration_deadline.isoformat()
            if relation.official_registration_deadline else None,
        }
        metadata = dict(relation.metadata_json or {})
        metadata["deadline_audit"] = {
            "batch": "RECOGNITION_BATCH_01",
            "reason": "2025 首届赛事数据被混入 2026 届次，且高校 B 级来源不能证明全国截止；原值保留于此。",
            "previous": previous,
            "verified_at": stamp.isoformat(),
        }
        relation.metadata_json = metadata
        relation.internal_registration_deadline = None
        relation.official_registration_deadline = None
        relation.verification_status = "needs_manual_review"
        relation.is_verified = False
        changes.append({"scope": "university_relation", "relation_id": relation.id, "previous": previous})
    return {
        "status": "repaired" if changes else "already_repaired",
        "competition_id": competition.id,
        "edition_id": edition.id,
        "root_cause": "年份混淆 + 高校来源字段误映射为全国截止；不是实际校内截止晚于全国截止。",
        "changes": changes,
    }


def revision_exists(db, edition_id: int, field: str, old_value: datetime) -> bool:
    return bool(
        db.scalar(
            select(func.count()).select_from(CompetitionFactRevision).where(
                CompetitionFactRevision.competition_edition_id == edition_id,
                CompetitionFactRevision.field_name == field,
                CompetitionFactRevision.old_value == old_value.isoformat(),
                CompetitionFactRevision.verification_status == "needs_manual_review",
            )
        )
    )


def audit_imported_recognitions(
    db,
    *,
    seed: dict[str, Any],
    parsed_documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    document_keys = [row["key"] for row in seed["documents"]]
    documents = list(
        db.execute(select(PolicyDocument).where(PolicyDocument.metadata_json["document_key"].as_string().in_(document_keys))).scalars()
    )
    document_by_id = {row.id: row for row in documents}
    recognitions = list(
        db.execute(
            select(CompetitionPolicyRecognition).where(
                CompetitionPolicyRecognition.policy_document_id.in_(document_by_id),
            )
        ).scalars()
    )
    sampled = random.Random(20260914).sample(recognitions, k=min(15, len(recognitions)))
    sample: list[dict[str, Any]] = []
    seed_by_key = {row["key"]: row for row in seed["documents"]}
    for recognition in sampled:
        document = document_by_id[recognition.policy_document_id]
        key = document.metadata_json["document_key"]
        document_seed = seed_by_key[key]
        parsed = parsed_documents[key]
        expected_status = recognition_status_for(document_seed["validity_status"])
        official_host = urlparse(document.attachment_url or document.source_url).hostname or ""
        errors = []
        if not official_host.endswith(document_seed["official_domain"]):
            errors.append("non_official_domain")
        if recognition.recognition_status != expected_status:
            errors.append("validity_status_mismatch")
        if recognition.evidence_page is None or recognition.evidence_page > parsed["page_count"]:
            errors.append("invalid_evidence_page")
        source_rows = document_seed.get("rows", []) + document_seed.get("unresolved_rows", [])
        source_row = next((row for row in source_rows if str(row["row"] ) == str(recognition.evidence_section)), None)
        if source_row is None or compact(source_row["raw_name"] ) not in compact(parsed["text"]):
            errors.append("raw_competition_name_not_found_in_document")
        sample.append(
            {
                "status": "FAIL" if errors else "PASS",
                "school": recognition.university.name,
                "competition": recognition.competition.name,
                "recognition_level": recognition.recognition_level,
                "evidence_title": document.title,
                "evidence_url": document.attachment_url,
                "file_year": document.year,
                "validity_status": document_seed["validity_status"],
                "evidence_page": recognition.evidence_page,
                "errors": errors,
            }
        )
    contamination = db.scalar(
        select(func.count()).select_from(CompetitionPolicyRecognition)
        .join(PolicyDocument)
        .where(
            PolicyDocument.id.in_(document_by_id),
            PolicyDocument.metadata_json["evidence_type"].as_string().in_(["notification", "participation"]),
        )
    ) or 0
    return {
        "persisted_recognitions": len(recognitions),
        "sample_size": len(sample),
        "sample_counts": dict(Counter(row["status"] for row in sample)),
        "notification_or_participation_promoted": contamination,
        "sample": sample,
    }


def evidence_text_for(document: dict[str, Any], row: dict[str, Any], canonical_name: str) -> str:
    return (
        f'{document["title"]}；第{row["page"]}页，第{row["row"]}项；'
        f'原文竞赛名：{row["raw_name"]}；标准赛事：{canonical_name}；'
        f'学校原始分类：{row.get("school_specific_level") or "未标注"}；'
        f'适用范围：{row.get("raw_category") or "未标注"}。'
    )


def document_summary(seed: dict[str, Any]) -> dict[str, Any]:
    return {
        key: seed.get(key)
        for key in (
            "key", "school", "college", "title", "year", "effective_year",
            "validity_status", "evidence_type", "source_page_url", "evidence_url", "local_path",
        )
    } | {"recognition_rows": len(seed.get("rows", [])), "unresolved_rows": len(seed.get("unresolved_rows", []))}


def database_snapshot() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "competitions": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False))) or 0,
            "policy_documents": db.scalar(select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))) or 0,
            "policy_attachments": db.scalar(select(func.count()).select_from(PolicyAttachment).where(PolicyAttachment.is_demo.is_(False))) or 0,
            "recognitions": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "recognized_current": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.recognition_status == "recognized", CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "recognized_historical": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.recognition_status == "expired", CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "recognized_unknown": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.recognition_status == "uncertain", CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "candidate_competitions": db.scalar(select(func.count()).select_from(CandidateCompetition).where(CandidateCompetition.is_demo.is_(False))) or 0,
            "sources": db.scalar(select(func.count()).select_from(CompetitionSource).where(CompetitionSource.is_demo.is_(False))) or 0,
            "edition_relations": db.scalar(select(func.count()).select_from(UniversityCompetitionEditionRelation).where(UniversityCompetitionEditionRelation.is_demo.is_(False))) or 0,
            "school_competitions": db.scalar(select(func.count()).select_from(SchoolCompetition)) or 0,
        }


def compact(value: str) -> str:
    return "".join(value.split()).replace("“", "").replace("”", "").replace('"', "").lower()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


if __name__ == "__main__":
    main()
