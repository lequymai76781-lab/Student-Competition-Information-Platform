from collections.abc import Iterable
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.base import CrawlError, CrawlPage, CrawlerRunResult, DiscoveredLink, utc_now
from app.crawler.discovery.attachment_discovery import AttachmentDiscoveryService
from app.crawler.discovery.college_discovery import CollegeDiscoveryService
from app.crawler.discovery.university_discovery import UniversitySeed
from app.crawler.extractors.competition_extractor import CompetitionExtractor
from app.crawler.extractors.policy_classifier import PolicyClassification, PolicyClassifier
from app.crawler.extractors.policy_relation_extractor import PolicyRelationExtractor
from app.crawler.fetchers.document_fetcher import DocumentFetchResult, DocumentFetcher
from app.crawler.fetchers.html_fetcher import FetchResult, HtmlFetcher
from app.crawler.normalization.college_normalizer import CollegeNormalizer
from app.crawler.normalization.competition_normalizer import CompetitionNormalizer
from app.crawler.parsers.docx_parser import DocxParser
from app.crawler.parsers.excel_parser import ExcelParser
from app.crawler.parsers.html_parser import HtmlContentParser
from app.crawler.parsers.legacy_office_parser import LegacyExcelParser, LegacyWordParser
from app.crawler.parsers.pdf_parser import ParsedDocument, PdfParser
from app.models import (
    CandidateCompetition,
    College,
    Competition,
    CompetitionPolicyRecognition,
    CrawlerJob,
    PolicyAttachment,
    PolicyDocument,
    ReviewQueue,
    University,
)


class UniversityPolicyPipeline:
    supported_document_extensions = {"pdf", "doc", "docx", "xls", "xlsx"}

    def __init__(
        self,
        *,
        storage_root: Path,
        respect_robots: bool = True,
        html_fetcher: HtmlFetcher | None = None,
        document_fetcher: DocumentFetcher | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.html_fetcher = html_fetcher or HtmlFetcher(respect_robots=respect_robots)
        self.document_fetcher = document_fetcher or DocumentFetcher(storage_root, respect_robots=respect_robots)
        self.html_parser = HtmlContentParser()
        self.attachment_discovery = AttachmentDiscoveryService()
        self.college_discovery = CollegeDiscoveryService()
        self.college_normalizer = CollegeNormalizer()
        self.policy_classifier = PolicyClassifier()
        self.competition_extractor = CompetitionExtractor()
        self.competition_normalizer = CompetitionNormalizer()
        self.relation_extractor = PolicyRelationExtractor()

    def run_batch(
        self,
        db: Session,
        seeds: Iterable[UniversitySeed],
        *,
        max_pages_per_university: int = 5,
        max_attachments_per_page: int = 2,
        dry_run: bool = False,
    ) -> list[CrawlerRunResult]:
        results: list[CrawlerRunResult] = []
        for seed in seeds:
            results.append(
                self.run_university(
                    db,
                    seed,
                    max_pages=max_pages_per_university,
                    max_attachments_per_page=max_attachments_per_page,
                    dry_run=dry_run,
                )
            )
        return results

    def run_university(
        self,
        db: Session,
        seed: UniversitySeed,
        *,
        max_pages: int = 5,
        max_attachments_per_page: int = 2,
        dry_run: bool = False,
    ) -> CrawlerRunResult:
        result = CrawlerRunResult(target_name=seed.name, target_url=seed.official_website)
        university = self._upsert_university(db, seed)
        job = self._start_job(db, university, seed, dry_run=dry_run)

        try:
            homepage = self.html_fetcher.fetch(seed.official_website)
            if isinstance(homepage, CrawlError):
                result.errors.append(homepage)
                self._queue_review(
                    db,
                    item_type="crawler_failure",
                    university_id=university.id,
                    reason="homepage_fetch_failed",
                    raw_value=homepage.message,
                    source_url=homepage.url,
                    confidence=None,
                    dry_run=dry_run,
                )
                result.review_items += 1
                return self._finish_job(db, job, result, dry_run=dry_run)

            page = self._parse_fetch_result(homepage)
            result.pages_fetched += 1
            result.pages_discovered += len(page.links)

            college_candidates = self.college_discovery.discover(page.links, seed.official_domain)
            for college_candidate in college_candidates:
                result.colleges_found += 1
                if not dry_run:
                    self.college_normalizer.get_or_create_from_official_source(
                        db,
                        university_id=university.id,
                        name=college_candidate.name,
                        official_website=college_candidate.official_website,
                        official_domain=college_candidate.official_domain,
                        source_url=college_candidate.source_url,
                        source_hash=college_candidate.source_hash,
                        confidence=college_candidate.confidence,
                    )

            policy_links = self.policy_discovery_links(page.links, seed.official_domain)[:max_pages]
            for link in policy_links:
                self._process_policy_link(
                    db,
                    university=university,
                    seed=seed,
                    link=link,
                    job=job,
                    result=result,
                    max_attachments=max_attachments_per_page,
                    dry_run=dry_run,
                )
            return self._finish_job(db, job, result, dry_run=dry_run)
        except Exception as exc:
            result.errors.append(CrawlError(url=seed.official_website, message=str(exc), retryable=False))
            self._queue_review(
                db,
                item_type="crawler_failure",
                university_id=university.id,
                reason="pipeline_exception",
                raw_value=str(exc),
                source_url=seed.official_website,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return self._finish_job(db, job, result, dry_run=dry_run)

    def run_university_from_discovered(
        self,
        db: Session,
        seed: UniversitySeed,
        discovered: list,
        *,
        max_attachments_per_page: int = 2,
        dry_run: bool = False,
        job_type: str = "general_undergraduate_policy_discovery",
    ) -> CrawlerRunResult:
        from app.crawler.discovery.general_undergraduate_policy_discovery import DiscoveredPolicy
        from app.crawler.discovery.url_normalizer import OfficialUrlNormalizer

        result = CrawlerRunResult(target_name=seed.name, target_url=seed.official_website)
        university = self._upsert_university(db, seed)
        job = self._start_job(db, university, seed, dry_run=dry_run, job_type=job_type)
        normalizer = OfficialUrlNormalizer()
        seen: set[str] = set()
        try:
            for policy in discovered:
                if not isinstance(policy, DiscoveredPolicy):
                    continue
                url = normalizer.normalize(policy.url, base_url=policy.source_url)
                if not url or not normalizer.is_official(url, seed.official_domain) or url in seen:
                    continue
                seen.add(url)
                link = DiscoveredLink(
                    url=url,
                    text=policy.title or url,
                    source_url=policy.source_url or seed.official_website,
                    reason=policy.discovery_stage or "multistage_discovery",
                )
                self._process_policy_link(
                    db,
                    university=university,
                    seed=seed,
                    link=link,
                    job=job,
                    result=result,
                    max_attachments=max_attachments_per_page,
                    discover_attachments=False,
                    dry_run=dry_run,
                )
            result.pages_discovered += len(seen)
            return self._finish_job(db, job, result, dry_run=dry_run)
        except Exception as exc:
            result.errors.append(CrawlError(url=seed.official_website, message=str(exc), retryable=False))
            self._queue_review(
                db,
                item_type="crawler_failure",
                university_id=university.id,
                reason="pipeline_exception",
                raw_value=str(exc),
                source_url=seed.official_website,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return self._finish_job(db, job, result, dry_run=dry_run)

    def policy_discovery_links(self, links: list[DiscoveredLink], official_domain: str) -> list[DiscoveredLink]:
        from app.crawler.discovery.policy_discovery import PolicyDiscoveryService

        return PolicyDiscoveryService().discover(links, official_domain)

    def _process_policy_link(
        self,
        db: Session,
        *,
        university: University,
        seed: UniversitySeed,
        link: DiscoveredLink,
        job: CrawlerJob,
        result: CrawlerRunResult,
        max_attachments: int,
        discover_attachments: bool = True,
        dry_run: bool,
    ) -> None:
        extension = self.attachment_discovery.detect_extension(link.url, link.text).lstrip(".")
        if extension or self.attachment_discovery.discover([link]):
            self._process_attachment_link(
                db,
                university=university,
                seed=seed,
                link=link,
                job=job,
                result=result,
                dry_run=dry_run,
            )
            return

        fetched = self.html_fetcher.fetch(link.url)
        if isinstance(fetched, CrawlError):
            result.errors.append(fetched)
            self._queue_review(
                db,
                item_type="crawler_failure",
                university_id=university.id,
                reason="policy_page_fetch_failed",
                raw_value=fetched.message,
                source_url=fetched.url,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return

        page = self._parse_fetch_result(fetched)
        result.pages_fetched += 1
        document = self._persist_policy_document(
            db,
            university=university,
            title=page.title or link.text or link.url,
            source_url=page.url,
            attachment_url=None,
            original_filename=None,
            official_domain=seed.official_domain,
            content_text=page.text,
            content_markdown=page.markdown,
            document_hash=page.content_hash,
            parser_type="html",
            source_type="university",
            crawler_job_id=job.id,
            review_result=result,
            dry_run=dry_run,
        )
        if document:
            result.policies_found += 1
            self._extract_and_persist_recognitions(db, university=university, document=document, result=result, dry_run=dry_run)

        attachments = self.attachment_discovery.discover(page.links) if discover_attachments else []
        for attachment in attachments[:max_attachments]:
            attachment_link = DiscoveredLink(
                url=attachment.url,
                text=attachment.link_text or attachment.filename or "",
                source_url=page.url,
                priority=link.priority,
                reason="attachment_from_policy_page",
            )
            self._process_attachment_link(
                db,
                university=university,
                seed=seed,
                link=attachment_link,
                job=job,
                result=result,
                dry_run=dry_run,
            )

    def _process_attachment_link(
        self,
        db: Session,
        *,
        university: University,
        seed: UniversitySeed,
        link: DiscoveredLink,
        job: CrawlerJob,
        result: CrawlerRunResult,
        dry_run: bool,
    ) -> None:
        result.documents_found += 1
        fetched = self.document_fetcher.fetch(link.url, referer=link.source_url)
        if isinstance(fetched, CrawlError):
            result.errors.append(fetched)
            self._queue_review(
                db,
                item_type="crawler_failure",
                university_id=university.id,
                reason="attachment_fetch_failed",
                raw_value=fetched.message,
                source_url=fetched.url,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return

        if fetched.extension not in self.supported_document_extensions:
            self._queue_review(
                db,
                item_type="unsupported_attachment",
                university_id=university.id,
                reason="unsupported_document_type",
                raw_value=fetched.extension or "unknown",
                source_url=link.url,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return

        parsed = self._parse_attachment(fetched)
        attachment = self._persist_attachment(
            db,
            university_id=university.id,
            fetched=fetched,
            parsed=parsed,
            crawler_job_id=job.id,
            dry_run=dry_run,
        )
        if parsed.error:
            self._queue_review(
                db,
                item_type="parse_failure",
                item_id=attachment.id if attachment else None,
                university_id=university.id,
                reason="attachment_parse_failed",
                raw_value=parsed.error,
                source_url=link.url,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return
        if parsed.needs_ocr:
            self._queue_review(
                db,
                item_type="scanned_pdf",
                item_id=attachment.id if attachment else None,
                university_id=university.id,
                reason="text_layer_missing_ocr_required",
                source_url=link.url,
                confidence=None,
                dry_run=dry_run,
            )
            result.review_items += 1
            return

        result.documents_parsed += 1
        title = link.text or fetched.filename
        document = self._persist_policy_document(
            db,
            university=university,
            title=title,
            source_url=link.source_url or link.url,
            attachment_url=link.url,
            original_filename=fetched.filename,
            official_domain=seed.official_domain,
            content_text=parsed.text,
            content_markdown=parsed.text,
            document_hash=fetched.file_hash,
            parser_type=parsed.parser_type,
            source_type="university",
            crawler_job_id=job.id,
            review_result=result,
            dry_run=dry_run,
        )
        if document:
            result.policies_found += 1
            if attachment and not dry_run:
                attachment.policy_document_id = document.id
            self._extract_and_persist_recognitions(db, university=university, document=document, result=result, dry_run=dry_run)

    def _parse_fetch_result(self, fetched: FetchResult) -> CrawlPage:
        parsed = self.html_parser.parse(fetched.text, fetched.final_url)
        return CrawlPage(
            url=fetched.final_url,
            title=parsed.title,
            text=parsed.text,
            markdown=parsed.markdown,
            html=fetched.text,
            links=parsed.links,
            status_code=fetched.status_code,
            content_hash=fetched.content_hash,
        )

    def _parse_attachment(self, fetched: DocumentFetchResult) -> ParsedDocument:
        if fetched.extension == "pdf":
            return PdfParser().parse(fetched.path)
        if fetched.extension == "docx":
            return DocxParser().parse(fetched.path)
        if fetched.extension == "xlsx":
            return ExcelParser().parse(fetched.path)
        if fetched.extension == "xls":
            return LegacyExcelParser().parse(fetched.path)
        if fetched.extension == "doc":
            return LegacyWordParser().parse(fetched.path)
        return ParsedDocument(text="", parser_type=fetched.extension, error=f"Unsupported document extension: {fetched.extension}")

    def _persist_policy_document(
        self,
        db: Session,
        *,
        university: University,
        title: str,
        source_url: str,
        attachment_url: str | None,
        original_filename: str | None,
        official_domain: str,
        content_text: str,
        content_markdown: str | None,
        document_hash: str | None,
        parser_type: str,
        source_type: str,
        crawler_job_id: int | None,
        review_result: CrawlerRunResult | None = None,
        dry_run: bool,
    ) -> PolicyDocument | None:
        classification = self.policy_classifier.classify(title, content_text)
        has_policy_marker = self.policy_classifier.has_policy_document_marker(title, content_text)
        if classification.policy_type == "other" or not has_policy_marker:
            self._queue_review(
                db,
                item_type="policy_candidate",
                university_id=university.id,
                reason="low_policy_confidence",
                raw_value=title[:500],
                evidence_text=content_text[:1000] or None,
                source_url=attachment_url or source_url,
                confidence=classification.confidence,
                dry_run=dry_run,
            )
            if review_result is not None:
                review_result.review_items += 1
            return None

        existing = self._find_existing_policy_document(db, source_url=source_url, attachment_url=attachment_url, document_hash=document_hash)
        if existing:
            self._refresh_existing_policy_document(existing, title, content_text, content_markdown, classification, parser_type)
            return existing
        if dry_run:
            return None

        document = PolicyDocument(
            university_id=university.id,
            scope_type=classification.scope_type,
            title=title[:500],
            policy_type=classification.policy_type,
            year=classification.year,
            latest_available_year=classification.latest_available_year,
            publisher=university.name,
            source_url=source_url,
            attachment_url=attachment_url,
            original_filename=original_filename,
            official_domain=official_domain,
            authority_level="A1" if classification.scope_type == "university" else "A2",
            content_text=content_text,
            content_markdown=content_markdown,
            document_hash=document_hash,
            is_current=classification.year is not None and classification.year >= 2024,
            is_verified=True,
            verification_status="official_domain_verified",
            crawler_job_id=crawler_job_id,
            parser_type=parser_type,
            source_type=source_type,
            is_demo=False,
            metadata_json={"classifier_confidence": classification.confidence},
        )
        db.add(document)
        db.flush()
        return document

    def _find_existing_policy_document(
        self,
        db: Session,
        *,
        source_url: str,
        attachment_url: str | None,
        document_hash: str | None,
    ) -> PolicyDocument | None:
        if document_hash:
            existing = db.execute(select(PolicyDocument).where(PolicyDocument.document_hash == document_hash)).scalars().first()
            if existing:
                return existing
        return db.execute(
            select(PolicyDocument).where(
                PolicyDocument.source_url == source_url,
                PolicyDocument.attachment_url == attachment_url,
            )
        ).scalars().first()

    def _refresh_existing_policy_document(
        self,
        document: PolicyDocument,
        title: str,
        content_text: str,
        content_markdown: str | None,
        classification: PolicyClassification,
        parser_type: str,
    ) -> None:
        if document.is_demo:
            return
        document.title = title[:500] or document.title
        document.content_text = content_text or document.content_text
        document.content_markdown = content_markdown or document.content_markdown
        document.policy_type = classification.policy_type
        document.year = classification.year or document.year
        document.latest_available_year = classification.latest_available_year or document.latest_available_year
        document.is_current = document.is_current or (classification.year is not None and classification.year >= 2024)
        document.parser_type = parser_type or document.parser_type

    def _persist_attachment(
        self,
        db: Session,
        *,
        university_id: int,
        fetched: DocumentFetchResult,
        parsed: ParsedDocument,
        crawler_job_id: int | None,
        dry_run: bool,
    ) -> PolicyAttachment | None:
        existing = db.execute(select(PolicyAttachment).where(PolicyAttachment.file_hash == fetched.file_hash)).scalars().first()
        if existing:
            return existing
        existing = db.execute(select(PolicyAttachment).where(PolicyAttachment.source_url == fetched.url)).scalars().first()
        if existing:
            return existing
        if dry_run:
            return None
        attachment = PolicyAttachment(
            crawler_job_id=crawler_job_id,
            university_id=university_id,
            source_url=fetched.url,
            filename=fetched.filename,
            content_type=fetched.content_type,
            file_extension=fetched.extension,
            file_hash=fetched.file_hash,
            file_size=fetched.file_size,
            parse_status="failed" if parsed.error else ("needs_ocr" if parsed.needs_ocr else "parsed"),
            parsed_at=utc_now() if not parsed.error else None,
            text_content=parsed.text or None,
            error_message=parsed.error,
            is_demo=False,
            metadata_json={"needs_ocr": parsed.needs_ocr, "page_count": parsed.page_count},
        )
        db.add(attachment)
        db.flush()
        return attachment

    def _extract_and_persist_recognitions(
        self,
        db: Session,
        *,
        university: University,
        document: PolicyDocument,
        result: CrawlerRunResult,
        dry_run: bool,
    ) -> None:
        text = document.content_text or ""
        if not text:
            return
        known_names = [name for name in db.execute(select(Competition.name)).scalars().all()]
        candidates = self.competition_extractor.extract(text, known_names)
        if not candidates:
            return

        relation_candidates = self.relation_extractor.extract(candidates, text, document.policy_type, title=document.title)
        for relation in relation_candidates:
            trusted_policy = (
                document.is_verified
                and relation.confidence >= 0.9
                and not relation.needs_manual_review
                and relation.recognition_status in {"recognized", "explicitly_not_recognized"}
            )
            normalized = self.competition_normalizer.normalize_or_create(
                db,
                relation.raw_competition_name,
                trusted_policy=trusted_policy,
                source_title=document.title,
                category="学科竞赛",
                source_url=document.attachment_url or document.source_url,
            )
            candidate = self._persist_candidate_competition(
                db,
                university=university,
                document=document,
                raw_name=relation.raw_competition_name,
                evidence_text=relation.evidence_text,
                source_url=document.attachment_url or document.source_url,
                confidence=relation.confidence,
                needs_manual_review=relation.needs_manual_review or normalized.needs_manual_review,
                normalized_competition_id=normalized.competition.id if normalized.competition else None,
                normalization_status=normalized.method,
                dry_run=dry_run,
            )
            if normalized.competition is None or normalized.needs_manual_review:
                self._queue_review(
                    db,
                    item_type="competition_alias",
                    university_id=university.id,
                    item_id=candidate.id if candidate else None,
                    policy_document_id=document.id,
                    reason=normalized.reason,
                    raw_value=relation.raw_competition_name,
                    evidence_text=relation.evidence_text,
                    source_url=document.attachment_url or document.source_url,
                    confidence=normalized.confidence,
                    dry_run=dry_run,
                )
                result.review_items += 1
                continue

            result.competitions_found += 1
            evidence_hash = sha256(
                f"{document.id}|{normalized.competition.id}|{relation.usage_type}|{relation.evidence_text}".encode("utf-8")
            ).hexdigest()
            existing = db.execute(
                select(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.policy_document_id == document.id,
                    CompetitionPolicyRecognition.competition_id == normalized.competition.id,
                    CompetitionPolicyRecognition.usage_type == relation.usage_type,
                    CompetitionPolicyRecognition.evidence_hash == evidence_hash,
                )
            ).scalars().first()
            if existing or dry_run:
                continue
            db.add(
                CompetitionPolicyRecognition(
                    competition_id=normalized.competition.id,
                    policy_document_id=document.id,
                    university_id=university.id,
                    college_id=document.college_id,
                    major_id=document.major_id,
                    year=document.year,
                    recognition_status=relation.recognition_status,
                    usage_type=relation.usage_type,
                    score_text=relation.score_text,
                    evidence_text=relation.evidence_text,
                    evidence_hash=evidence_hash,
                    evidence_page=relation.evidence_page,
                    evidence_section=relation.evidence_section,
                    confidence=relation.confidence,
                    needs_manual_review=relation.needs_manual_review,
                    is_demo=False,
                )
            )

    def _persist_candidate_competition(
        self,
        db: Session,
        *,
        university: University,
        document: PolicyDocument,
        raw_name: str,
        evidence_text: str,
        source_url: str,
        confidence: float,
        needs_manual_review: bool,
        normalized_competition_id: int | None,
        normalization_status: str,
        dry_run: bool,
    ) -> CandidateCompetition | None:
        if dry_run:
            return None
        table_row = sha256(evidence_text.encode("utf-8")).hexdigest()[:16]
        candidate = db.execute(
            select(CandidateCompetition).where(
                CandidateCompetition.policy_document_id == document.id,
                CandidateCompetition.table_row == table_row,
                CandidateCompetition.raw_name == raw_name,
            )
        ).scalar_one_or_none()
        payload = {
            "university_id": university.id,
            "college_id": document.college_id,
            "raw_category": "自动抽取",
            "evidence_text": evidence_text,
            "source_url": source_url,
            "confidence": confidence,
            "normalization_status": normalization_status,
            "normalized_competition_id": normalized_competition_id,
            "needs_manual_review": needs_manual_review,
            "is_demo": False,
        }
        if candidate is None:
            candidate = CandidateCompetition(
                policy_document_id=document.id,
                raw_name=raw_name,
                table_row=table_row,
                **payload,
            )
            db.add(candidate)
            db.flush()
            return candidate
        for key, value in payload.items():
            setattr(candidate, key, value)
        return candidate

    def _upsert_university(self, db: Session, seed: UniversitySeed) -> University:
        university = db.execute(select(University).where(University.name == seed.name)).scalar_one_or_none()
        payload = {
            "short_name": seed.short_name,
            "english_name": seed.english_name,
            "aliases": seed.aliases,
            "province": seed.province,
            "city": seed.city,
            "university_type": "综合类",
            "is_985": seed.is_985,
            "is_211": seed.is_211,
            "is_double_first_class": bool(getattr(seed, "is_double_first_class", seed.is_985)),
            "official_website": seed.official_website,
            "official_domain": seed.official_domain,
            "is_demo": False,
        }
        if university is None:
            university = University(name=seed.name, **payload)
            db.add(university)
            db.flush()
            return university
        for key, value in payload.items():
            setattr(university, key, value)
        db.flush()
        return university

    def _start_job(self, db: Session, university: University, seed: UniversitySeed, *, dry_run: bool, job_type: str = "985_policy_discovery") -> CrawlerJob:
        university.policy_crawl_status = "discovering"
        university.policy_crawl_started_at = utc_now()
        university.policy_crawl_error = None
        job = CrawlerJob(
            job_type=job_type,
            target_type="university",
            target_id=university.id,
            target_name=university.name,
            status="running",
            started_at=utc_now(),
            metadata_json={"official_domain": seed.official_domain, "dry_run": dry_run},
        )
        db.add(job)
        db.flush()
        return job

    def _finish_job(self, db: Session, job: CrawlerJob, result: CrawlerRunResult, *, dry_run: bool) -> CrawlerRunResult:
        result.finished_at = utc_now()
        status = result.status
        if status == "completed" and result.policies_found == 0:
            status = "partial"
        job.status = status
        job.finished_at = result.finished_at
        job.pages_discovered = result.pages_discovered
        job.pages_fetched = result.pages_fetched
        job.documents_found = result.documents_found
        job.documents_parsed = result.documents_parsed
        job.competitions_found = result.competitions_found
        job.errors_count = len(result.errors)
        job.error_summary = "\n".join(f"{error.url}: {error.message}" for error in result.errors[:10]) or None
        university = db.get(University, job.target_id) if job.target_id else None
        if university:
            university.policy_crawl_status = status
            university.last_policy_crawl_at = result.finished_at
            university.policy_crawl_error = job.error_summary or (
                "本轮未发现可验证政策。" if result.policies_found == 0 else None
            )
        if not dry_run:
            db.commit()
        else:
            db.rollback()
        return result

    def _queue_review(
        self,
        db: Session,
        *,
        item_type: str,
        reason: str,
        raw_value: str | None = None,
        suggested_value: str | None = None,
        evidence_text: str | None = None,
        source_url: str | None = None,
        confidence: float | None = None,
        item_id: int | None = None,
        university_id: int | None = None,
        college_id: int | None = None,
        major_id: int | None = None,
        policy_document_id: int | None = None,
        competition_id: int | None = None,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            return
        duplicate = db.execute(
            select(ReviewQueue).where(
                ReviewQueue.item_type == item_type,
                ReviewQueue.reason == reason,
                ReviewQueue.source_url == source_url,
                ReviewQueue.raw_value == raw_value,
                ReviewQueue.status == "pending",
            )
        ).scalars().first()
        if duplicate:
            return
        db.add(
            ReviewQueue(
                item_type=item_type,
                item_id=item_id,
                university_id=university_id,
                college_id=college_id,
                major_id=major_id,
                policy_document_id=policy_document_id,
                competition_id=competition_id,
                status="pending",
                reason=reason,
                raw_value=raw_value,
                suggested_value=suggested_value,
                evidence_text=evidence_text,
                source_url=source_url,
                confidence=confidence,
                is_demo=False,
            )
        )


def result_to_dict(result: CrawlerRunResult) -> dict:
    return {
        "target_name": result.target_name,
        "target_url": result.target_url,
        "status": result.status,
        "pages_discovered": result.pages_discovered,
        "pages_fetched": result.pages_fetched,
        "documents_found": result.documents_found,
        "documents_parsed": result.documents_parsed,
        "competitions_found": result.competitions_found,
        "colleges_found": result.colleges_found,
        "policies_found": result.policies_found,
        "review_items": result.review_items,
        "errors": [
            {
                "url": error.url,
                "message": error.message,
                "status_code": error.status_code,
                "retryable": error.retryable,
            }
            for error in result.errors
        ],
        "started_at": _isoformat(result.started_at),
        "finished_at": _isoformat(result.finished_at),
    }


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
