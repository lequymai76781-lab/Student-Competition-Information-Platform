"""Import the bounded DATA_READINESS_SPRINT_01 evidence set.

This script is deliberately separate from discovery.  It imports reviewed
official policy evidence, resolves the six carry-over recognition candidates,
and repairs two cross-year deadline copies.  Every operation is idempotent.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.crawler.parsers.pdf_parser import PdfParser
from app.database.session import SessionLocal
from app.models import (
    CandidateCompetition,
    Competition,
    CompetitionAlias,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionPolicyRecognition,
    CompetitionSource,
    PolicyAttachment,
    PolicyDocument,
    SchoolCompetition,
    University,
)
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.school_competition_service import SchoolCompetitionService
from app.services.source_authority_service import authority_level_for


SEED = PROJECT_ROOT / "data" / "seeds" / "data_readiness_sprint_01.json"
REPORT = PROJECT_ROOT / "data" / "reports" / "data_readiness_sprint_01_import.json"
BATCH = "DATA_READINESS_SPRINT_01"

IDENTITY_SPECS = [
    {
        "name": "全国大学生红色旅游创意策划大赛",
        "short_name": "红旅大赛",
        "aliases": ["全国大学生红色旅游创意策划大赛（简称“红旅大赛”）"],
        "organizer": "文化和旅游部资源开发司等",
        "category": "创新创业",
        "competition_level": "国家级",
        "description": "面向大学生开展的红色旅游创意策划赛事。",
        "source_type": "government_official_notice",
        "source_name": "中华人民共和国文化和旅游部",
        "source_url": "https://www.mct.gov.cn/whzx/bnsj/zykfs/202403/t20240328_951957.html",
        "source_title": "文化和旅游部联合有关单位举办第十四届全国大学生红色旅游创意策划大赛",
        "verified": True,
    },
    {
        "name": "“中航工业杯”国际无人飞行器创新大奖赛",
        "short_name": "国际无人飞行器创新大奖赛",
        "aliases": ["国际无人飞行器创新大奖赛"],
        "organizer": "中国航空工业集团公司、中国航空学会",
        "category": "航空航天",
        "competition_level": "国际级",
        "description": "由高校官方历史资料确认举办的无人飞行器创新与竞技赛事。",
        "source_type": "university_official_notice",
        "source_name": "上海交通大学航空航天学院",
        "source_url": "https://www.aero.sjtu.edu.cn/post/925",
        "source_title": "我校航模队在首届国际无人飞行器创新大奖赛中勇创佳绩",
        "verified": False,
    },
    {
        "name": "全国“电脑鼠走迷宫”竞赛",
        "short_name": "电脑鼠走迷宫竞赛",
        "aliases": ["全国电脑鼠走迷宫竞赛", "全国IEEE标准电脑鼠走迷宫竞赛"],
        "organizer": "中国计算机学会",
        "category": "电子信息",
        "competition_level": "国家级",
        "description": "采用 IEEE 标准电脑鼠规则的全国性走迷宫竞赛。",
        "source_type": "university_official_notice",
        "source_name": "北京交通大学新闻网",
        "source_url": "https://news.bjtu.edu.cn/info/1003/17280.htm",
        "source_title": "2012全国“电脑鼠走迷宫”总决赛于北京交通大学成功举行",
        "verified": False,
    },
    {
        "name": "“东芝杯”中国师范大学理科师范生教学技能创新大赛",
        "short_name": "东芝杯教学技能创新大赛",
        "aliases": ["东芝杯·中国师范大学师范专业理科大学生教学技能创新实践大赛"],
        "organizer": "中华人民共和国教育部、东芝（中国）有限公司",
        "category": "教育教学",
        "competition_level": "国家级",
        "description": "面向师范大学理科师范生的教学技能创新赛事。",
        "source_type": "organizer_official_notice",
        "source_name": "东芝（中国）有限公司",
        "source_url": "https://www.toshiba.com.cn/news/welfare_news/news_2011/news347498.html",
        "source_title": "东芝和中国教育部签署教学技能创新大赛框架协议书",
        "verified": True,
    },
    {
        "name": "全国大学生交通运输科技大赛",
        "short_name": "交通运输科技大赛",
        "aliases": [],
        "organizer": "教育部高等学校交通运输类专业教学指导委员会",
        "category": "交通运输",
        "competition_level": "国家级",
        "description": "面向高校学生的全国性交通运输科技竞赛。",
        "official_website": "https://nactrans.bjtu.edu.cn/",
        "source_type": "official_competition_website",
        "source_name": "全国大学生交通运输科技大赛组委会",
        "source_url": "https://nactrans.bjtu.edu.cn/",
        "source_title": "全国大学生交通运输科技大赛官方网站",
        "verified": True,
    },
]

UNRESOLVED_TARGETS = {
    "全国大学生红色旅游创意策划大赛（简称“红旅大赛”）": "全国大学生红色旅游创意策划大赛",
    "“中航工业杯”国际无人飞行器创新大奖赛": "“中航工业杯”国际无人飞行器创新大奖赛",
    "ACM国际大学生程序设计竞赛": "ACM-ICPC国际大学生程序设计竞赛",
    "全国“电脑鼠走迷宫”竞赛": "全国“电脑鼠走迷宫”竞赛",
    "东芝杯·中国师范大学师范专业理科大学生教学技能创新实践大赛": "“东芝杯”中国师范大学理科师范生教学技能创新大赛",
    "全国大学生交通运输科技大赛": "全国大学生交通运输科技大赛",
}


def main() -> None:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc)
    before = snapshot()

    with SessionLocal() as db:
        normalizer = CompetitionNormalizationService()
        created_competitions = ensure_identity_competitions(db, normalizer, stamp)
        document_results = []
        imported_rows = []
        for document_seed in seed["documents"]:
            document, parsed = upsert_document(db, document_seed, stamp)
            document_results.append(parsed)
            for row in document_seed["rows"]:
                imported_rows.append(
                    upsert_current_recognition(db, normalizer, document, document_seed, row, stamp)
                )

        cleanup = cleanup_first_run_artifacts(db)
        resolved = resolve_carry_over_candidates(db, normalizer, stamp)
        deadline_repairs = repair_cross_year_deadlines(db, stamp)
        db.flush()
        quality_refresh = CompetitionIntelligenceService().refresh_all(db, now=stamp)
        school_read_model = SchoolCompetitionService().rebuild(db)
        db.commit()

        audit = audit_state(db, seed)

    after = snapshot()
    report = {
        "batch": BATCH,
        "generated_at": stamp.isoformat(),
        "before": before,
        "after": after,
        "delta": {key: after[key] - before.get(key, 0) for key in after},
        "created_competitions": created_competitions,
        "documents": document_results,
        "current_recognition_import": {
            "attempted": len(imported_rows),
            "imported": sum(item["status"] == "imported" for item in imported_rows),
            "unresolved": [item for item in imported_rows if item["status"] != "imported"],
        },
        "first_run_artifact_cleanup": cleanup,
        "carry_over_candidates": resolved,
        "deadline_repairs": deadline_repairs,
        "quality_refresh": quality_refresh,
        "school_read_model": school_read_model,
        "audit": audit,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def ensure_identity_competitions(db, normalizer: CompetitionNormalizationService, stamp: datetime) -> list[str]:
    created = []
    for spec in IDENTITY_SPECS:
        competition = db.execute(select(Competition).where(Competition.name == spec["name"])).scalar_one_or_none()
        if competition is None:
            source_level = authority_level_for(spec["source_type"])
            competition = Competition(
                name=spec["name"],
                short_name=spec.get("short_name"),
                description=spec["description"],
                organizer=spec["organizer"],
                official_website=spec.get("official_website"),
                description_source_url=spec["source_url"],
                category=spec["category"],
                competition_level=spec["competition_level"],
                country_or_region="中国",
                competition_type="competition",
                is_competition=True,
                entity_type="competition",
                status="active",
                is_official_verified=bool(spec["verified"]),
                verification_status="verified_official" if spec["verified"] else "school_confirmed",
                last_verified_at=stamp,
                last_seen_at=stamp,
                is_demo=False,
            )
            db.add(competition)
            db.flush()
            created.append(competition.name)
        for alias in spec["aliases"]:
            normalizer.ensure_alias(
                db,
                competition,
                alias,
                source=BATCH,
                confidence=1.0,
                is_verified=True,
            )
        upsert_competition_source(db, competition, spec, stamp)

    acm = db.execute(
        select(Competition).where(Competition.name == "ACM-ICPC国际大学生程序设计竞赛")
    ).scalar_one()
    normalizer.ensure_alias(
        db,
        acm,
        "ACM国际大学生程序设计竞赛",
        source=BATCH,
        confidence=1.0,
        is_verified=True,
    )
    return created


def upsert_competition_source(db, competition: Competition, spec: dict[str, Any], stamp: datetime) -> None:
    source = db.execute(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == spec["source_url"],
        )
    ).scalar_one_or_none()
    level = authority_level_for(spec["source_type"])
    payload = {
        "source_type": spec["source_type"],
        "authority_level": level,
        "source_name": spec["source_name"],
        "source_platform": "official_web",
        "retrieved_at": stamp,
        "is_official": True,
        "is_verified": True,
        "credibility_score": 100 if level == "S" else 90,
        "reliability_tier": 1 if level == "S" else 3,
        "verification_status": "verified_official" if spec["verified"] else "school_confirmed",
        "raw_title": spec["source_title"],
        "raw_content": spec["description"],
        "content_hash": digest_text(spec["source_title"] + spec["description"]),
        "metadata_json": {"batch": BATCH, "identity_evidence": True},
        "is_demo": False,
    }
    if source is None:
        db.add(CompetitionSource(competition_id=competition.id, source_url=spec["source_url"], **payload))
    else:
        for key, value in payload.items():
            setattr(source, key, value)


def upsert_document(db, seed: dict[str, Any], stamp: datetime) -> tuple[PolicyDocument, dict[str, Any]]:
    university = db.execute(select(University).where(University.name == seed["school"])).scalar_one()
    local_path = PROJECT_ROOT / seed["local_path"] if seed.get("local_path") else None
    if local_path is not None and not local_path.is_file():
        raise FileNotFoundError(local_path)

    content_text = seed.get("content_text") or ""
    page_count = None
    file_hash = None
    if local_path is not None:
        file_hash = sha256_file(local_path)
        if local_path.suffix.lower() == ".pdf":
            parsed = PdfParser().parse(local_path)
            if parsed.error or not parsed.text or parsed.needs_ocr:
                raise ValueError(f'{seed["key"]}: PDF parse failed: {parsed.error or "OCR required"}')
            content_text = parsed.text
            page_count = parsed.page_count
        else:
            content_text = "\n".join(
                f'{row["row"]}\t{row["raw_name"]}\t{row.get("school_specific_level") or ""}'
                for row in seed["rows"]
            )
    else:
        file_hash = digest_text(seed["source_page_url"] + content_text)

    if not content_text:
        raise ValueError(f'{seed["key"]}: empty evidence text')
    document = next(
        (
            item
            for item in db.execute(select(PolicyDocument).where(PolicyDocument.university_id == university.id)).scalars()
            if (item.metadata_json or {}).get("document_key") == seed["key"]
        ),
        None,
    )
    if document is None:
        identity_predicates = [PolicyDocument.document_hash == file_hash]
        if seed.get("evidence_url"):
            identity_predicates.append(PolicyDocument.attachment_url == seed["evidence_url"])
        document = db.execute(
            select(PolicyDocument).where(or_(*identity_predicates))
        ).scalar_one_or_none()

    payload = {
        "university_id": university.id,
        "scope_type": "university",
        "title": seed["title"],
        "policy_type": seed["policy_type"],
        "year": seed["year"],
        "latest_available_year": seed["effective_year"],
        "publisher": university.name,
        "source_url": seed["source_page_url"],
        "attachment_url": seed.get("evidence_url"),
        "original_filename": local_path.name if local_path else None,
        "official_domain": seed["official_domain"],
        "authority_level": "A2",
        "published_at": parse_datetime(seed["published_at"]),
        "effective_from": parse_datetime(seed["published_at"]),
        "effective_until": None,
        "content_text": content_text,
        "document_hash": file_hash,
        "is_current": True,
        "is_verified": True,
        "verification_status": "official_domain_verified",
        "parser_type": seed["parser_type"],
        "source_type": "university",
        "is_demo": False,
        "metadata_json": {
            "batch": BATCH,
            "document_key": seed["key"],
            "evidence_type": seed["evidence_type"],
            "effective_year": seed["effective_year"],
            "validity_status": "current_recognition",
            "verified_at": stamp.isoformat(),
            "page_count": page_count,
            "local_path": seed.get("local_path"),
        },
    }
    if document is None:
        document = PolicyDocument(**payload)
        db.add(document)
        db.flush()
    else:
        for key, value in payload.items():
            setattr(document, key, value)

    for older in db.execute(
        select(PolicyDocument).where(
            PolicyDocument.university_id == university.id,
            PolicyDocument.id != document.id,
            PolicyDocument.is_current.is_(True),
        )
    ).scalars():
        older.is_current = False

    if local_path is not None and seed.get("evidence_url"):
        upsert_attachment(db, document, seed, local_path, file_hash, content_text, page_count, stamp)
    return document, {
        "key": seed["key"],
        "school": seed["school"],
        "rows": len(seed["rows"]),
        "parser_type": seed["parser_type"],
        "page_count": page_count,
        "file_hash": file_hash,
    }


def upsert_attachment(
    db,
    document: PolicyDocument,
    seed: dict[str, Any],
    local_path: Path,
    file_hash: str,
    content_text: str,
    page_count: int | None,
    stamp: datetime,
) -> None:
    attachment = db.execute(
        select(PolicyAttachment).where(PolicyAttachment.source_url == seed["evidence_url"])
    ).scalar_one_or_none()
    suffix = local_path.suffix.lower()
    payload = {
        "policy_document_id": document.id,
        "university_id": document.university_id,
        "filename": local_path.name,
        "content_type": "application/pdf" if suffix == ".pdf" else "application/vnd.ms-excel",
        "file_extension": suffix,
        "file_hash": file_hash,
        "file_size": local_path.stat().st_size,
        "parse_status": "parsed",
        "parsed_at": stamp,
        "text_content": content_text,
        "error_message": None,
        "is_demo": False,
        "metadata_json": {
            "batch": BATCH,
            "document_key": seed["key"],
            "page_count": page_count,
            "parser_type": seed["parser_type"],
            "local_path": seed["local_path"],
        },
    }
    if attachment is None:
        db.add(PolicyAttachment(source_url=seed["evidence_url"], **payload))
    else:
        for key, value in payload.items():
            setattr(attachment, key, value)


def upsert_current_recognition(
    db,
    normalizer: CompetitionNormalizationService,
    document: PolicyDocument,
    document_seed: dict[str, Any],
    row: dict[str, Any],
    stamp: datetime,
) -> dict[str, Any]:
    normalized = normalizer.normalize(db, row["raw_name"])
    safe = bool(normalized.competition and not normalized.needs_manual_review and normalized.confidence >= 0.88)
    candidate = upsert_candidate(db, document, row, normalized, safe)
    if not safe:
        return {
            "status": "unresolved",
            "school": document_seed["school"],
            "raw_name": row["raw_name"],
            "method": normalized.method,
            "confidence": normalized.confidence,
        }

    competition = normalized.competition
    evidence_text = (
        f'{document.title}；第{row.get("page") or "表格"}页/位置{row["row"]}；'
        f'原文竞赛名：{row["raw_name"]}；标准赛事：{competition.name}；'
        f'学校原始分类：{row.get("school_specific_level") or "正文未标明"}。'
    )
    evidence_hash = digest_text(evidence_text)
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
        "year": document.latest_available_year or document.year,
        "recognition_status": "recognized",
        "recognition_level": clean(row.get("school_specific_level")),
        "evidence_text": evidence_text,
        "evidence_hash": evidence_hash,
        "evidence_page": row.get("page"),
        "evidence_section": row["row"],
        "confidence": normalized.confidence,
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
    upsert_policy_source(db, competition, document, document_seed, evidence_text, stamp)
    db.flush()
    return {
        "status": "imported",
        "school": document_seed["school"],
        "raw_name": row["raw_name"],
        "competition_id": competition.id,
        "candidate_id": candidate.id,
        "method": normalized.method,
        "confidence": normalized.confidence,
    }


def upsert_candidate(db, document: PolicyDocument, row: dict[str, Any], normalized, safe: bool) -> CandidateCompetition:
    candidate = db.execute(
        select(CandidateCompetition).where(
            CandidateCompetition.policy_document_id == document.id,
            CandidateCompetition.table_row == row["row"],
            CandidateCompetition.raw_name == row["raw_name"],
        )
    ).scalar_one_or_none()
    payload = {
        "university_id": document.university_id,
        "raw_category": row.get("raw_category"),
        "raw_level": clean(row.get("school_specific_level")),
        "evidence_text": f'{document.title}；位置{row["row"]}：{row["raw_name"]}',
        "page_number": row.get("page"),
        "source_url": document.attachment_url or document.source_url,
        "confidence": normalized.confidence,
        "normalization_status": normalized.method,
        "normalized_competition_id": normalized.competition.id if safe else None,
        "needs_manual_review": not safe,
        "is_demo": False,
        "metadata_json": {"batch": BATCH, "normalization_reason": normalized.reason},
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


def upsert_policy_source(
    db,
    competition: Competition,
    document: PolicyDocument,
    seed: dict[str, Any],
    evidence_text: str,
    stamp: datetime,
) -> None:
    source_url = document.attachment_url or document.source_url
    source = db.execute(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == source_url,
        )
    ).scalar_one_or_none()
    payload = {
        "source_type": "university_policy",
        "authority_level": authority_level_for("university_policy"),
        "source_name": document.publisher,
        "source_platform": "university_official",
        "published_at": document.published_at,
        "crawled_at": stamp,
        "retrieved_at": stamp,
        "is_official": True,
        "is_verified": True,
        "credibility_score": 95,
        "reliability_tier": 2,
        "verification_status": "school_confirmed",
        "raw_title": document.title,
        "raw_content": evidence_text,
        "content_hash": document.document_hash,
        "metadata_json": {
            "batch": BATCH,
            "policy_document_id": document.id,
            "evidence_type": seed["evidence_type"],
            "validity_status": "current_recognition",
            "effective_year": seed["effective_year"],
            "source_page_url": seed["source_page_url"],
        },
        "is_demo": False,
    }
    if source is None:
        db.add(CompetitionSource(competition_id=competition.id, source_url=source_url, **payload))
    else:
        for key, value in payload.items():
            setattr(source, key, value)


def resolve_carry_over_candidates(
    db,
    normalizer: CompetitionNormalizationService,
    stamp: datetime,
) -> list[dict[str, Any]]:
    results = []
    for raw_name, canonical_name in UNRESOLVED_TARGETS.items():
        competition = db.execute(select(Competition).where(Competition.name == canonical_name)).scalar_one()
        candidates = [
            candidate
            for candidate in db.execute(
                select(CandidateCompetition).where(CandidateCompetition.raw_name == raw_name)
            ).scalars()
            if (candidate.metadata_json or {}).get("batch") == "RECOGNITION_BATCH_01"
        ]
        if not candidates:
            raise ValueError(f"carry-over candidate not found: {raw_name}")
        normalizer.ensure_alias(
            db,
            competition,
            raw_name,
            source=BATCH,
            confidence=1.0,
            is_verified=True,
        )
        for candidate in candidates:
            candidate.normalized_competition_id = competition.id
            candidate.normalization_status = "manual_verified_identity"
            candidate.confidence = 1.0
            candidate.needs_manual_review = False
            metadata = dict(candidate.metadata_json or {})
            metadata["resolution"] = {
                "batch": BATCH,
                "canonical_name": canonical_name,
                "resolved_at": stamp.isoformat(),
            }
            candidate.metadata_json = metadata
            usage_type = "recommendation" if candidate.policy_document.policy_type == "recommendation" else "competition_classification"
            status = "recognized" if candidate.policy_document.is_current else "expired"
            evidence_text = (
                f'{candidate.policy_document.title}；位置{candidate.table_row}；'
                f'原文竞赛名：{candidate.raw_name}；经独立赛事身份核验映射为：{competition.name}。'
            )
            evidence_hash = digest_text(evidence_text)
            recognition = db.execute(
                select(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.policy_document_id == candidate.policy_document_id,
                    CompetitionPolicyRecognition.competition_id == competition.id,
                    CompetitionPolicyRecognition.usage_type == usage_type,
                    CompetitionPolicyRecognition.evidence_hash == evidence_hash,
                )
            ).scalar_one_or_none()
            payload = {
                "university_id": candidate.university_id,
                "college_id": candidate.college_id,
                "year": candidate.policy_document.year,
                "recognition_status": status,
                "recognition_level": candidate.raw_level,
                "evidence_text": evidence_text,
                "evidence_hash": evidence_hash,
                "evidence_page": candidate.page_number,
                "evidence_section": candidate.table_row,
                "confidence": 1.0,
                "needs_manual_review": False,
                "is_demo": False,
            }
            if recognition is None:
                recognition = CompetitionPolicyRecognition(
                    competition_id=competition.id,
                    policy_document_id=candidate.policy_document_id,
                    usage_type=usage_type,
                    **payload,
                )
                db.add(recognition)
            else:
                for key, value in payload.items():
                    setattr(recognition, key, value)
            results.append(
                {
                    "candidate_id": candidate.id,
                    "raw_name": raw_name,
                    "competition_id": competition.id,
                    "canonical_name": canonical_name,
                    "status": "resolved",
                }
            )
    return results


def cleanup_first_run_artifacts(db) -> dict[str, int]:
    """Remove only rows created by the initial NULL-attachment/import-scope bug."""
    batch_documents = [
        document
        for document in db.execute(select(PolicyDocument)).scalars()
        if (document.metadata_json or {}).get("batch") == BATCH
    ]
    document_by_id = {document.id: document for document in batch_documents}
    deleted_recognitions = 0
    for recognition in list(
        db.execute(
            select(CompetitionPolicyRecognition).where(
                CompetitionPolicyRecognition.policy_document_id.in_(document_by_id)
            )
        ).scalars()
    ):
        document = document_by_id[recognition.policy_document_id]
        duplicate_resolution = "经独立赛事身份核验映射为" in recognition.evidence_text
        wrong_school = recognition.university_id != document.university_id
        if duplicate_resolution or wrong_school:
            db.delete(recognition)
            deleted_recognitions += 1

    deleted_candidates = 0
    for candidate in list(
        db.execute(
            select(CandidateCompetition).where(
                CandidateCompetition.policy_document_id.in_(document_by_id)
            )
        ).scalars()
    ):
        document = document_by_id[candidate.policy_document_id]
        if candidate.university_id != document.university_id:
            db.delete(candidate)
            deleted_candidates += 1
    db.flush()
    return {
        "deleted_recognitions": deleted_recognitions,
        "deleted_candidates": deleted_candidates,
    }

def repair_cross_year_deadlines(db, stamp: datetime) -> list[dict[str, Any]]:
    competition = db.execute(
        select(Competition).where(Competition.name == "中国国际大学生创新大赛")
    ).scalar_one()
    repairs = []
    for edition in db.execute(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == competition.id,
            CompetitionEdition.year.in_([2024, 2025]),
        )
    ).scalars():
        old_value = edition.official_registration_deadline
        if old_value is None:
            repairs.append({"edition_id": edition.id, "year": edition.year, "status": "already_repaired"})
            continue
        source_url = edition.official_notice_url or edition.source_url or "https://www.moe.gov.cn/"
        revision = next(
            (
                item
                for item in db.execute(
                    select(CompetitionFactRevision).where(
                        CompetitionFactRevision.competition_edition_id == edition.id,
                        CompetitionFactRevision.field_name == "official_registration_deadline",
                    )
                ).scalars()
                if item.old_value == old_value.isoformat() and item.new_value is None
            ),
            None,
        )
        if revision is None:
            db.add(
                CompetitionFactRevision(
                    competition_id=competition.id,
                    competition_edition_id=edition.id,
                    field_name="official_registration_deadline",
                    old_value=old_value.isoformat(),
                    new_value=None,
                    changed_at=stamp,
                    source_url=source_url,
                    source_name=f"{BATCH} cross-year deadline audit",
                    verification_status="verified_official",
                )
            )
        edition.official_registration_deadline = None
        repairs.append(
            {
                "edition_id": edition.id,
                "year": edition.year,
                "status": "repaired",
                "old_value": old_value.isoformat(),
            }
        )
    return repairs


def audit_state(db, seed: dict[str, Any]) -> dict[str, Any]:
    keys = {item["key"] for item in seed["documents"]}
    documents = [
        item
        for item in db.execute(select(PolicyDocument)).scalars()
        if (item.metadata_json or {}).get("document_key") in keys
    ]
    document_ids = [item.id for item in documents]
    recognitions = list(
        db.execute(
            select(CompetitionPolicyRecognition).where(
                CompetitionPolicyRecognition.policy_document_id.in_(document_ids)
            )
        ).scalars()
    )
    current_school_count = db.scalar(
        select(func.count(func.distinct(CompetitionPolicyRecognition.university_id))).where(
            CompetitionPolicyRecognition.recognition_status == "recognized",
            CompetitionPolicyRecognition.needs_manual_review.is_(False),
            CompetitionPolicyRecognition.is_demo.is_(False),
        )
    ) or 0
    remaining_targets = db.scalar(
        select(func.count()).select_from(CandidateCompetition).where(
            CandidateCompetition.raw_name.in_(UNRESOLVED_TARGETS),
            CandidateCompetition.needs_manual_review.is_(True),
        )
    ) or 0
    contamination = db.scalar(
        select(func.count()).select_from(CompetitionPolicyRecognition).join(PolicyDocument).where(
            PolicyDocument.id.in_(document_ids),
            PolicyDocument.metadata_json["evidence_type"].as_string().in_(["notification", "participation"]),
        )
    ) or 0
    stale_deadlines = db.scalar(
        select(func.count()).select_from(CompetitionEdition).where(
            CompetitionEdition.competition_id == select(Competition.id).where(
                Competition.name == "中国国际大学生创新大赛"
            ).scalar_subquery(),
            CompetitionEdition.year.in_([2024, 2025]),
            CompetitionEdition.official_registration_deadline.is_not(None),
        )
    ) or 0
    return {
        "documents": len(documents),
        "current_recognitions_in_batch": len(recognitions),
        "current_recognition_school_count": current_school_count,
        "remaining_carry_over_targets": remaining_targets,
        "notification_or_participation_promoted": contamination,
        "stale_cross_year_deadlines": stale_deadlines,
    }


def snapshot() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "competitions": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False))) or 0,
            "sources": db.scalar(select(func.count()).select_from(CompetitionSource).where(CompetitionSource.is_demo.is_(False))) or 0,
            "policy_documents": db.scalar(select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))) or 0,
            "policy_attachments": db.scalar(select(func.count()).select_from(PolicyAttachment).where(PolicyAttachment.is_demo.is_(False))) or 0,
            "recognitions": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "recognized_current": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.recognition_status == "recognized", CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "recognized_historical": db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.recognition_status == "expired", CompetitionPolicyRecognition.is_demo.is_(False))) or 0,
            "candidate_competitions": db.scalar(select(func.count()).select_from(CandidateCompetition).where(CandidateCompetition.is_demo.is_(False))) or 0,
            "school_competitions": db.scalar(select(func.count()).select_from(SchoolCompetition)) or 0,
            "fact_revisions": db.scalar(select(func.count()).select_from(CompetitionFactRevision)) or 0,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def clean(value: str | None) -> str | None:
    return value.strip() if value else None


if __name__ == "__main__":
    main()
