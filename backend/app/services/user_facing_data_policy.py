"""V0.9 - centralized rule for which data may enter ordinary user views.

Deterministic modules (current registration / school notice / personalized
deadline) may only use verified relations and open editions. result_notice /
award_news / needs_review / noise leads never act as registration evidence.
"""

from __future__ import annotations


class UserFacingDataPolicy:
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
