import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crawler.parsers.pdf_parser import PdfParser
from app.models import (
    CandidateCompetition,
    College,
    Competition,
    CompetitionPolicyRecognition,
    CompetitionSource,
    CompetitionStatistics,
    CrawlerJob,
    PolicyAttachment,
    PolicyDocument,
    University,
)
from app.services.competition_normalization_service import CompetitionNormalizationService

ROOT_DIR = Path(__file__).resolve().parents[3]
WHU_POLICY_PAGE = "https://journal.whu.edu.cn/20250611use7"
WHU_POLICY_PDF = "https://journal.whu.edu.cn/uploadfiles/2025061120jgu.pdf"
WHU_POLICY_PATH = (
    ROOT_DIR
    / "data"
    / "raw"
    / "policy_documents"
    / "wuhan-university"
    / "武汉大学新闻与传播学院本科学生素质综合测评实施细则-2025.pdf"
)
WHSU_POLICY_SOURCE = "local-source://wuhan-sports-university/journalism/2026/catalog.pdf"
WHSU_POLICY_PATH = (
    ROOT_DIR
    / "data"
    / "raw"
    / "policy_documents"
    / "wuhan-sports-university"
    / "武汉体育学院新闻传播学院大学生学科竞赛目录.pdf"
)
WHSU_ROWS_PATH = ROOT_DIR / "data" / "seeds" / "wuhan_sports_university_journalism_competitions.json"

WHU_COMPETITIONS = [
    "中国国际大学生创新大赛",
    "“挑战杯”全国大学生课外学术科技作品竞赛",
    "“挑战杯”中国大学生创业计划竞赛",
    "全国大学生数学建模竞赛",
    "全国大学生电子设计竞赛",
]
WHU_EVIDENCE = (
    "参见本科生院出具的赛事目录，其他不予加分。其中，I类赛事（即中国国际大学生创新大赛、"
    "“挑战杯”全国大学生课外学术科技作品竞赛、“挑战杯”中国大学生创业计划竞赛、"
    "全国大学生数学建模竞赛和全国大学生电子设计竞赛）按照上限加分，II类赛事按照下限加分。"
)


class VerifiedPolicyIngestService:
    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()
        self.pdf_parser = PdfParser()

    def ingest(self, db: Session) -> dict[str, int]:
        self._require_source_files()
        whu_document = self._ingest_wuhan_university(db)
        whsu_document = self._ingest_wuhan_sports_university(db)
        self._record_first_batch_statuses(db, whu_document)
        self._refresh_statistics(db)
        db.flush()
        return {
            "policy_documents": self._count(db, PolicyDocument),
            "candidate_competitions": self._count(db, CandidateCompetition),
            "competitions": self._count(db, Competition),
            "recognitions": self._count(db, CompetitionPolicyRecognition),
            "wuhan_university_policy_document_id": whu_document.id,
            "wuhan_sports_policy_document_id": whsu_document.id,
        }

    def _ingest_wuhan_university(self, db: Session) -> PolicyDocument:
        university = self._upsert_university(
            db,
            name="武汉大学",
            short_name="武大",
            province="湖北",
            city="武汉",
            official_website="https://www.whu.edu.cn/",
            official_domain="whu.edu.cn",
            is_985=True,
            is_211=True,
        )
        college = self._upsert_college(
            db,
            university=university,
            name="新闻与传播学院",
            official_website="https://journal.whu.edu.cn/",
            official_domain="journal.whu.edu.cn",
            source_url="https://journal.whu.edu.cn/xygk/xyjj.htm",
            is_verified=True,
        )
        parsed = self.pdf_parser.parse(WHU_POLICY_PATH)
        if parsed.error or not parsed.text or parsed.needs_ocr:
            raise ValueError(f"武汉大学政策 PDF 解析失败: {parsed.error or 'empty text layer'}")
        compact_policy_text = re.sub(r"\s+", "", parsed.text)
        for name in WHU_COMPETITIONS:
            if re.sub(r"\s+", "", name) not in compact_policy_text:
                raise ValueError(f"武汉大学政策证据中缺少竞赛名称: {name}")

        file_hash = self._sha256_file(WHU_POLICY_PATH)
        document = self._upsert_document(
            db,
            university=university,
            college=college,
            title="武汉大学新闻与传播学院本科学生素质综合测评实施细则（2025年修订版）",
            policy_type="comprehensive_evaluation",
            year=2025,
            publisher="武汉大学新闻与传播学院",
            source_url=WHU_POLICY_PAGE,
            attachment_url=WHU_POLICY_PDF,
            original_filename=WHU_POLICY_PATH.name,
            official_domain="journal.whu.edu.cn",
            published_at=datetime(2025, 6, 11, tzinfo=timezone.utc),
            effective_from=datetime(2025, 9, 1, tzinfo=timezone.utc),
            content_text=parsed.text,
            document_hash=file_hash,
            parser_type=parsed.parser_type,
            source_type="college_official_website",
            verification_status="official_domain_verified",
            metadata={"page_count": parsed.page_count, "evidence_page": 14},
        )
        self._upsert_attachment(
            db,
            document=document,
            university=university,
            source_url=WHU_POLICY_PDF,
            path=WHU_POLICY_PATH,
            file_hash=file_hash,
            parse_status="parsed",
            text_content=parsed.text,
            metadata={"page_count": parsed.page_count, "parser_type": parsed.parser_type},
        )

        for index, name in enumerate(WHU_COMPETITIONS, start=1):
            self._persist_candidate_and_recognition(
                db,
                document=document,
                university=university,
                college=college,
                raw_name=name,
                raw_category="学科竞赛",
                raw_level="I类",
                raw_award=None,
                raw_score="按照上限加分",
                evidence_text=WHU_EVIDENCE,
                table_row=f"I类-{index}",
                page_number=14,
                source_url=WHU_POLICY_PDF,
                usage_type="comprehensive_evaluation",
                recognition_status="recognized",
                confidence=1.0,
                needs_manual_review=False,
                trusted_policy=True,
            )

        university.policy_crawl_status = "completed"
        university.policy_crawl_started_at = datetime.now(timezone.utc)
        university.last_policy_crawl_at = datetime.now(timezone.utc)
        university.policy_crawl_error = None
        return document

    def _ingest_wuhan_sports_university(self, db: Session) -> PolicyDocument:
        university = self._upsert_university(
            db,
            name="武汉体育学院",
            short_name="武体",
            province="湖北",
            city="武汉",
            official_website="https://www.whsu.edu.cn/",
            official_domain="whsu.edu.cn",
            is_985=False,
            is_211=False,
        )
        college = self._upsert_college(
            db,
            university=university,
            name="新闻传播学院",
            official_website="https://xwxy.whsu.edu.cn/",
            official_domain="xwxy.whsu.edu.cn",
            source_url="https://xwxy.whsu.edu.cn/",
            is_verified=True,
        )
        rows = json.loads(WHSU_ROWS_PATH.read_text(encoding="utf-8"))
        if [row["row"] for row in rows] != list(range(1, 98)):
            raise ValueError("武汉体育学院人工核验目录必须连续包含 1-97 行")

        file_hash = self._sha256_file(WHSU_POLICY_PATH)
        manual_text = "\n".join(f'{row["row"]}. {row["name"]} [{row["level"]}]' for row in rows)
        document = self._upsert_document(
            db,
            university=university,
            college=college,
            title="武汉体育学院新闻传播学院大学生学科竞赛目录",
            policy_type="competition_catalog",
            year=2026,
            publisher="武汉体育学院新闻传播学院",
            source_url=WHSU_POLICY_SOURCE,
            attachment_url=WHSU_POLICY_SOURCE,
            original_filename=WHSU_POLICY_PATH.name,
            official_domain="xwxy.whsu.edu.cn",
            published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            effective_from=datetime(2026, 8, 30, tzinfo=timezone.utc),
            content_text=manual_text,
            document_hash=file_hash,
            parser_type="manual_visual_transcription",
            source_type="user_provided_official_scan",
            verification_status="user_confirmed_official_scan",
            metadata={
                "page_count": 5,
                "document_number": "武体新传院发〔2026〕3号",
                "public_source_url_status": "pending",
                "source_file_sha256": file_hash,
                "transcription_method": "manual_visual_review_no_ocr",
            },
        )
        self._upsert_attachment(
            db,
            document=document,
            university=university,
            source_url=WHSU_POLICY_SOURCE,
            path=WHSU_POLICY_PATH,
            file_hash=file_hash,
            parse_status="manual_transcription",
            text_content=manual_text,
            metadata={
                "page_count": 5,
                "needs_ocr": True,
                "ocr_used": False,
                "transcription_method": "manual_visual_review",
            },
        )

        for row in rows:
            evidence = f'目录第{row["row"]}行：{row["name"]}，级别{row["level"]}。'
            self._persist_candidate_and_recognition(
                db,
                document=document,
                university=university,
                college=college,
                raw_name=row["name"],
                raw_category="学院学科竞赛目录",
                raw_level=row["level"],
                raw_award=None,
                raw_score=None,
                evidence_text=evidence,
                table_row=str(row["row"]),
                page_number=row["page"],
                source_url=WHSU_POLICY_SOURCE,
                usage_type="competition_catalog",
                recognition_status="recognized",
                confidence=1.0,
                needs_manual_review=False,
                trusted_policy=True,
            )

        university.policy_crawl_status = "completed"
        university.policy_crawl_started_at = datetime.now(timezone.utc)
        university.last_policy_crawl_at = datetime.now(timezone.utc)
        university.policy_crawl_error = "官网公开链接待补；当前依据用户提供的学院盖章扫描件。"
        return document

    def _persist_candidate_and_recognition(
        self,
        db: Session,
        *,
        document: PolicyDocument,
        university: University,
        college: College | None,
        raw_name: str,
        raw_category: str | None,
        raw_level: str | None,
        raw_award: str | None,
        raw_score: str | None,
        evidence_text: str,
        table_row: str,
        page_number: int,
        source_url: str,
        usage_type: str,
        recognition_status: str,
        confidence: float,
        needs_manual_review: bool,
        trusted_policy: bool,
    ) -> None:
        normalization = self.normalizer.normalize_or_create(
            db,
            raw_name,
            trusted_policy=trusted_policy,
            source_title=document.title,
            category="学科竞赛",
        )
        if normalization.competition is None:
            raise ValueError(f"可信政策候选无法归一化: {raw_name} ({normalization.reason})")
        competition = normalization.competition
        candidate = db.execute(
            select(CandidateCompetition).where(
                CandidateCompetition.policy_document_id == document.id,
                CandidateCompetition.table_row == table_row,
                CandidateCompetition.raw_name == raw_name,
            )
        ).scalar_one_or_none()
        payload = {
            "university_id": university.id,
            "college_id": college.id if college else None,
            "raw_category": raw_category,
            "raw_level": raw_level,
            "raw_award": raw_award,
            "raw_score": raw_score,
            "evidence_text": evidence_text,
            "page_number": page_number,
            "source_url": source_url,
            "confidence": confidence,
            "normalization_status": normalization.method,
            "normalized_competition_id": competition.id,
            "needs_manual_review": needs_manual_review,
            "is_demo": False,
            "metadata_json": {"normalization_reason": normalization.reason},
        }
        if candidate is None:
            candidate = CandidateCompetition(
                policy_document_id=document.id,
                raw_name=raw_name,
                table_row=table_row,
                **payload,
            )
            db.add(candidate)
        else:
            for key, value in payload.items():
                setattr(candidate, key, value)

        evidence_hash = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
        recognition = db.execute(
            select(CompetitionPolicyRecognition).where(
                CompetitionPolicyRecognition.policy_document_id == document.id,
                CompetitionPolicyRecognition.competition_id == competition.id,
                CompetitionPolicyRecognition.usage_type == usage_type,
                CompetitionPolicyRecognition.evidence_hash == evidence_hash,
            )
        ).scalar_one_or_none()
        recognition_payload = {
            "university_id": university.id,
            "college_id": college.id if college else None,
            "year": document.year,
            "recognition_status": recognition_status,
            "recognition_level": raw_level,
            "award_requirement": raw_award,
            "score_text": raw_score,
            "evidence_text": evidence_text,
            "evidence_hash": evidence_hash,
            "evidence_page": page_number,
            "evidence_section": table_row,
            "confidence": confidence,
            "needs_manual_review": needs_manual_review,
            "is_demo": False,
        }
        if recognition is None:
            recognition = CompetitionPolicyRecognition(
                competition_id=competition.id,
                policy_document_id=document.id,
                usage_type=usage_type,
                **recognition_payload,
            )
            db.add(recognition)
        else:
            for key, value in recognition_payload.items():
                setattr(recognition, key, value)

        source = db.execute(
            select(CompetitionSource).where(
                CompetitionSource.competition_id == competition.id,
                CompetitionSource.source_url == source_url,
            )
        ).scalar_one_or_none()
        if source is None:
            db.add(
                CompetitionSource(
                    competition_id=competition.id,
                    source_type="university_policy",
                    source_name=document.publisher,
                    source_url=source_url,
                    source_platform="university_official",
                    published_at=document.published_at,
                    crawled_at=datetime.now(timezone.utc),
                    is_official=True,
                    is_verified=document.is_verified,
                    credibility_score=95 if document.source_url.startswith("https://") else 90,
                    raw_title=document.title,
                    raw_content=evidence_text,
                    content_hash=document.document_hash,
                    metadata_json={"policy_document_id": document.id, "evidence_page": page_number},
                    is_demo=False,
                )
            )

    def _upsert_document(
        self,
        db: Session,
        *,
        university: University,
        college: College,
        title: str,
        policy_type: str,
        year: int,
        publisher: str,
        source_url: str,
        attachment_url: str,
        original_filename: str,
        official_domain: str,
        published_at: datetime,
        effective_from: datetime,
        content_text: str,
        document_hash: str,
        parser_type: str,
        source_type: str,
        verification_status: str,
        metadata: dict,
    ) -> PolicyDocument:
        document = db.execute(
            select(PolicyDocument).where(PolicyDocument.document_hash == document_hash)
        ).scalar_one_or_none()
        payload = {
            "university_id": university.id,
            "college_id": college.id,
            "scope_type": "college",
            "title": title,
            "policy_type": policy_type,
            "year": year,
            "latest_available_year": year,
            "publisher": publisher,
            "source_url": source_url,
            "attachment_url": attachment_url,
            "original_filename": original_filename,
            "official_domain": official_domain,
            "authority_level": "A2",
            "published_at": published_at,
            "effective_from": effective_from,
            "content_text": content_text,
            "document_hash": document_hash,
            "is_current": True,
            "is_verified": True,
            "verification_status": verification_status,
            "parser_type": parser_type,
            "source_type": source_type,
            "is_demo": False,
            "metadata_json": metadata,
        }
        if document is None:
            document = PolicyDocument(**payload)
            db.add(document)
            db.flush()
        else:
            for key, value in payload.items():
                setattr(document, key, value)
            db.flush()
        return document

    def _upsert_attachment(
        self,
        db: Session,
        *,
        document: PolicyDocument,
        university: University,
        source_url: str,
        path: Path,
        file_hash: str,
        parse_status: str,
        text_content: str,
        metadata: dict,
    ) -> PolicyAttachment:
        attachment = db.execute(
            select(PolicyAttachment).where(PolicyAttachment.file_hash == file_hash)
        ).scalar_one_or_none()
        payload = {
            "policy_document_id": document.id,
            "university_id": university.id,
            "source_url": source_url,
            "filename": path.name,
            "content_type": "application/pdf",
            "file_extension": ".pdf",
            "file_hash": file_hash,
            "file_size": path.stat().st_size,
            "parse_status": parse_status,
            "parsed_at": datetime.now(timezone.utc),
            "text_content": text_content,
            "is_demo": False,
            "metadata_json": {"local_path": str(path), **metadata},
        }
        if attachment is None:
            attachment = PolicyAttachment(**payload)
            db.add(attachment)
        else:
            for key, value in payload.items():
                setattr(attachment, key, value)
        return attachment

    def _upsert_university(
        self,
        db: Session,
        *,
        name: str,
        short_name: str,
        province: str,
        city: str,
        official_website: str,
        official_domain: str,
        is_985: bool,
        is_211: bool,
    ) -> University:
        university = db.execute(select(University).where(University.name == name)).scalar_one_or_none()
        payload = {
            "short_name": short_name,
            "province": province,
            "city": city,
            "official_website": official_website,
            "official_domain": official_domain,
            "is_985": is_985,
            "is_211": is_211,
            "is_double_first_class": is_985,
            "is_demo": False,
        }
        if university is None:
            university = University(name=name, **payload)
            db.add(university)
            db.flush()
        else:
            for key, value in payload.items():
                setattr(university, key, value)
        return university

    def _upsert_college(
        self,
        db: Session,
        *,
        university: University,
        name: str,
        official_website: str,
        official_domain: str,
        source_url: str,
        is_verified: bool,
    ) -> College:
        college = db.execute(
            select(College).where(College.university_id == university.id, College.name == name)
        ).scalar_one_or_none()
        payload = {
            "official_website": official_website,
            "official_domain": official_domain,
            "source_url": source_url,
            "is_verified": is_verified,
            "is_demo": False,
        }
        if college is None:
            college = College(university_id=university.id, name=name, **payload)
            db.add(college)
            db.flush()
        else:
            for key, value in payload.items():
                setattr(college, key, value)
        return college

    def _record_first_batch_statuses(self, db: Session, whu_document: PolicyDocument) -> None:
        now = datetime.now(timezone.utc)
        statuses = {
            "清华大学": "未找到可在本轮完成解析并核验的现行竞赛认定政策。",
            "北京大学": "已定位学院官方政策候选，附件结构仍待逐条解析，本轮不计入政策覆盖。",
            "浙江大学": "已定位官网历史竞赛目录，因年份较早，本轮不作为现行政策入库。",
            "华中科技大学": "未找到可在本轮完成解析并核验的现行竞赛认定政策。",
        }
        for name, reason in statuses.items():
            university = db.execute(select(University).where(University.name == name)).scalar_one_or_none()
            if university is None:
                continue
            university.policy_crawl_status = "partial"
            university.policy_crawl_started_at = now
            university.last_policy_crawl_at = now
            university.policy_crawl_error = reason
            self._upsert_job(
                db,
                university=university,
                status="partial",
                documents_found=0,
                documents_parsed=0,
                competitions_found=0,
                error_summary=reason,
                metadata={"batch": "v0.2-first-five", "counts_toward_coverage": False},
            )

        whu = whu_document.university
        self._upsert_job(
            db,
            university=whu,
            status="completed",
            documents_found=1,
            documents_parsed=1,
            competitions_found=5,
            error_summary=None,
            metadata={
                "batch": "v0.2-first-five",
                "policy_document_id": whu_document.id,
                "source_url": WHU_POLICY_PAGE,
                "attachment_url": WHU_POLICY_PDF,
                "counts_toward_coverage": True,
            },
        )

    def _upsert_job(
        self,
        db: Session,
        *,
        university: University,
        status: str,
        documents_found: int,
        documents_parsed: int,
        competitions_found: int,
        error_summary: str | None,
        metadata: dict,
    ) -> None:
        job = db.execute(
            select(CrawlerJob).where(
                CrawlerJob.job_type == "v0.2_first_batch",
                CrawlerJob.target_type == "university",
                CrawlerJob.target_id == university.id,
            )
        ).scalar_one_or_none()
        payload = {
            "target_name": university.name,
            "status": status,
            "started_at": university.policy_crawl_started_at,
            "finished_at": university.last_policy_crawl_at,
            "pages_discovered": 1 if documents_found else 0,
            "pages_fetched": 1 if documents_found else 0,
            "documents_found": documents_found,
            "documents_parsed": documents_parsed,
            "competitions_found": competitions_found,
            "errors_count": 1 if error_summary else 0,
            "error_summary": error_summary,
            "metadata_json": metadata,
        }
        if job is None:
            db.add(
                CrawlerJob(
                    job_type="v0.2_first_batch",
                    target_type="university",
                    target_id=university.id,
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(job, key, value)

    def _refresh_statistics(self, db: Session) -> None:
        from app.services.competition_intelligence_service import CompetitionIntelligenceService

        db.flush()
        CompetitionIntelligenceService().refresh_all(db)

    def _require_source_files(self) -> None:
        missing = [path for path in (WHU_POLICY_PATH, WHSU_POLICY_PATH, WHSU_ROWS_PATH) if not path.exists()]
        if missing:
            raise FileNotFoundError("缺少政策导入文件: " + ", ".join(str(path) for path in missing))

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _count(self, db: Session, model: type) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(model.is_demo.is_(False))) or 0)
