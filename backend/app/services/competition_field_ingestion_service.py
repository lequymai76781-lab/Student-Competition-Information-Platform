"""Candidate-only adapter shared by external competition data producers.

No method approves sources, mutates official entities, or commits. Unsupported
input is retained in the candidate description for explicit human preparation.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select

from app.models import CompetitionEdition, ReviewQueue
from app.schemas.field_review import FieldSourceIn
from app.services.field_review_service import FIELDS, FieldReviewService, validate_candidate_value


def _json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def ingestion_source(record: dict, *, default_type="crawler") -> dict:
    """Classify a claimed source without treating the claim as verification."""
    raw = record.get("source_type") or default_type
    mapping = {
        "organizer_official_notice": "organizer_notice", "official_notice": "organizer_notice",
        "government_official_notice": "government_document", "government_document": "government_document",
        "competition_official_website": "official_website", "official_competition_website": "official_website",
        "official_competition_site": "official_website", "organizer_official": "organizer_notice",
        "university_official_notice": "university_notice", "university_official": "university_notice",
        "college_official_notice": "university_notice", "university_policy": "university_policy",
        "github_seed": "third_party", "source_repository_discovery": "third_party",
        "third_party_platform": "third_party", "association_official": "industry_organization",
    }
    allowed = {row["value"] for row in FieldReviewService.config()["source_types"]}
    kind = mapping.get(raw, raw if raw in allowed else default_type)
    url = record.get("source_url") or record.get("canonical_source_url") or record.get("internal_notice_url")
    parsed = urlsplit(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        url = None
    title = record.get("source_title") or record.get("source_name") or record.get("title")
    return {
        "source_type": kind,
        "source_title": str(title)[:255] if title else None,
        "source_url": url,
        "publisher": str(record["publisher"])[:255] if record.get("publisher") else None,
        "published_at": record.get("published_at"),
    }


class CompetitionFieldIngestionService:
    def stage(self, db, *, entity_type, title, fields, source=None, competition_id=None,
              edition_id=None, year=None, university_id=None, producer="crawler", raw=None):
        # A source also belongs to unstructured evidence. Validate and retain it
        # even when every extracted field needs manual preparation.
        source = FieldSourceIn.model_validate(source).model_dump(mode="json") if source else None
        raw_fields = _json(fields)
        proposals = []
        validation_notes = {}
        for key, value in raw_fields.items():
            if key not in FIELDS[entity_type]:
                validation_notes[key] = "Not an editable fact field; retained as raw evidence."
                continue
            try:
                value = validate_candidate_value(entity_type, key, value)
            except HTTPException as error:
                if error.status_code != 422:
                    raise
                validation_notes[key] = str(error.detail)
                continue
            proposals.append({"field_name": key, "candidate_value": value, "source": source})
        payload = {
            "entity_type": entity_type, "competition_id": competition_id,
            "edition_id": edition_id, "year": year, "university_id": university_id,
            "title": str(title)[:255], "origin": "crawler",
            "fields": proposals,
        }
        evidence = {"producer": producer, "input": _json(raw if raw is not None else fields),
                    "fields_requiring_manual_preparation": validation_notes}
        # Empty proposals otherwise omit the source completely from identity.
        # Existing raw manifests already include it; preserve their fingerprints.
        if not proposals and raw is None:
            evidence["source"] = source
        canonical = json.dumps({"payload": payload, "evidence": evidence}, ensure_ascii=False, sort_keys=True, default=str)
        marker = "ingestion_sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        # Includes terminal decisions: rerunning an unchanged source must never
        # reopen rejected/approved work or replace its immutable evidence.
        existing = db.scalar(select(ReviewQueue).where(
            ReviewQueue.item_type == "field_candidate", ReviewQueue.raw_value.contains(marker),
        ).order_by(ReviewQueue.id))
        if existing is not None:
            return existing
        payload["description"] = marker + "\n" + json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
        # Never truncate evidence silently; the shared input limit raises a
        # clear validation error and the surrounding ingestion must roll back.
        row = FieldReviewService.create_candidate(db, payload, origin="crawler")
        row.source_url = source.get("source_url") if source else None
        db.flush()
        if producer != "mid_scale_school_mapping":
            from app.services.document_policy_service import DocumentPolicyService
            DocumentPolicyService.classify_candidate(db, row.id)
        return row

    def stage_record(self, db, record, *, producer, competition=None):
        """Stage a competition record and, only with a known parent, its edition."""
        from app.services.competition_normalization_service import CompetitionNormalizationService

        name = record.get("competition_name") or record.get("name")
        if competition is None and name:
            match = CompetitionNormalizationService().normalize(db, name)
            if not match.needs_manual_review:
                competition = match.competition
        source = ingestion_source(record)
        fields = {key: value for key, value in record.items() if key in FIELDS["competition"] and value is not None}
        if name:
            fields.setdefault("name", name)
        rows = [self.stage(db, entity_type="competition", competition_id=competition.id if competition else None,
            title=f"{producer}: {name or '待确认赛事'}", fields=fields, source=source, producer=producer, raw=record)]
        edition_data = record.get("edition") or {}
        # A not-yet-approved Competition cannot own a formal edition candidate.
        # The complete edition payload remains in the parent's raw evidence.
        if competition is not None and edition_data.get("year"):
            year = int(edition_data["year"])
            edition = db.scalar(select(CompetitionEdition).where(
                CompetitionEdition.competition_id == competition.id, CompetitionEdition.year == year))
            edition_fields = {key: value for key, value in edition_data.items()
                              if key in FIELDS["edition"] and value is not None}
            rows.append(self.stage(db, entity_type="edition", competition_id=competition.id,
                edition_id=edition.id if edition else None, year=year,
                title=f"{producer}: {name} / {year}", fields=edition_fields,
                source=source, producer=producer, raw=record))
        return rows
