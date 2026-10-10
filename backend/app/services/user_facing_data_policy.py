"""V0.9 - centralized rule for which data may enter ordinary user views.

Deterministic modules (current registration / school notice / personalized
deadline) may only use verified relations and open editions. result_notice /
award_news / needs_review / noise leads never act as registration evidence.
"""

from __future__ import annotations

from sqlalchemy import and_


class UserFacingDataPolicy:
    VERIFIED_FACT_STATUSES = {"verified_manual", "verified_official", "verified_multi_source", "authority_confirmed",
        "association_confirmed", "official_site_confirmed", "school_confirmed"}
    BLOCKED_VERIFICATION_STATUSES = {"pending", "pending_verification", "reviewing", "needs_review",
        "conflicting", "uncertain", "insufficient_evidence", "suspected", "candidate", "rejected", "superseded"}

    @classmethod
    def verified_record(cls, record) -> bool:
        # Legacy rows can carry is_verified=True with the default 'unverified'
        # text. Explicit pending/review/conflict flags always override that bit.
        return bool(record is not None and record.is_verified
                    and not getattr(record, "is_demo", False)
                    and record.verification_status not in cls.BLOCKED_VERIFICATION_STATUSES)

    @classmethod
    def verified_clause(cls, model):
        clauses = [model.is_verified.is_(True), model.verification_status.notin_(cls.BLOCKED_VERIFICATION_STATUSES)]
        if hasattr(model, "is_demo"):
            clauses.append(model.is_demo.is_(False))
        return and_(*clauses)

    @classmethod
    def competition_allowed(cls, competition) -> bool:
        return bool(not competition.is_demo and competition.is_competition and (
            competition.verification_status in cls.VERIFIED_FACT_STATUSES
            or (competition.verification_status == "unverified" and (
                competition.is_official_verified or any(cls.verified_record(source)
                                                       for source in competition.sources)))))

    @classmethod
    def recognition_allowed(cls, recognition) -> bool:
        policy = recognition.policy_document
        if policy is not None and any((policy.metadata_json or {}).get(key) for key in ("policy_automation", "superseded_by", "policy_version_conflict")):
            from app.services.policy_resolution_service import PolicyResolutionService
            if not PolicyResolutionService._public_document_scope(policy):
                return False
        return bool(not recognition.is_demo and recognition.recognition_status == "recognized"
                    and recognition.needs_manual_review is False and policy is not None
                    and cls.verified_record(policy))

    # Relation notice types allowed as school/college "has a notice" evidence.
    RELATION_NOTICE_TYPES = {
        "registration_notice",
        "internal_selection",
        "submission_notice",
        "competition_announcement",
    }
    # Only these imply an actual current registration/selection action.
    ACTION_NOTICE_TYPES = {
        "registration_notice",
        "internal_selection",
        "submission_notice",
    }
    VERIFIED_RELATION_STATUSES = {"verified_official"}
    EDITION_OPEN_STATUSES = {
        "registration_open",
        "registration_upcoming",
        "submission_open",
        "upcoming",
    }

    @classmethod
    def relation_allowed(cls, relation) -> bool:
        if relation.is_demo or relation.is_verified is not True:
            return False
        if relation.verification_status not in cls.VERIFIED_RELATION_STATUSES:
            return False
        return relation.notice_type in cls.RELATION_NOTICE_TYPES

    @classmethod
    def relation_action(cls, relation) -> bool:
        return cls.relation_allowed(relation) and relation.notice_type in cls.ACTION_NOTICE_TYPES
