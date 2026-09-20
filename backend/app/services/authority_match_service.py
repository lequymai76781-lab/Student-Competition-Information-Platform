"""Authority-source name normalization and competition matching.

V1 authority main library: registry entries carry authoritative document
names; we never merge purely on string similarity. A match combines:

- normalized base name (year / 第X届 / quotes / full-width / spaces removed)
- known historical aliases and the existing alias table
- organizer / official-domain hints when available
- edition-year / edition-number hints

Results are scored and anything below the auto threshold is flagged for
manual review instead of being silently bound.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionAlias, CompetitionEdition


CN_NUMERALS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
}

HISTORICAL_NAME_MAP = {
    "中国互联网+大学生创新创业大赛": "中国国际大学生创新大赛",
    "互联网+大学生创新创业大赛": "中国国际大学生创新大赛",
    "“互联网+”大学生创新创业大赛": "中国国际大学生创新大赛",
    "中国“互联网+”大学生创新创业大赛": "中国国际大学生创新大赛",
    "ACM-ICPC国际大学生程序设计竞赛": "ACM-ICPC国际大学生程序设计竞赛",
    "ICPC国际大学生程序设计竞赛": "ACM-ICPC国际大学生程序设计竞赛",
}

_YEAR_RE = re.compile(r"(20\d\d)")
_EDITION_CN_RE = re.compile(r"第([一二三四五六七八九十]+)届")
_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")
_PUNCT_RE = re.compile(r"[\s\u3000\"“”'‘’《》、，,。.·\\/|｜\-—–+＋&＆:：;；!！?？@#￥$%^*]+")


def normalize_competition_name(name: str | None) -> str:
    """Lower, strip quotes/spaces/full-width punctuation (keeps Chinese)."""
    if not name:
        return ""
    value = name.strip()
    value = _PUNCT_RE.sub("", value)
    value = value.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    return value.lower()


def strip_year_and_edition(name: str | None) -> str:
    """Return a comparison key without years / 第X届 / parenthetical notes."""
    if not name:
        return ""
    value = name.strip()
    value = _PAREN_RE.sub("", value)
    value = _EDITION_CN_RE.sub("", value)
    value = _YEAR_RE.sub("", value)
    value = value.replace("年", "")
    return normalize_competition_name(value)


def extract_year(text: str | None) -> int | None:
    if not text:
        return None
    match = _YEAR_RE.search(text)
    if not match:
        return None
    year = int(match.group(1))
    if 1990 <= year <= 2100:
        return year
    return None


def extract_edition_number(text: str | None) -> int | None:
    if not text:
        return None
    match = _EDITION_CN_RE.search(text)
    if not match:
        return None
    return CN_NUMERALS.get(match.group(1))


def host_of(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return (parsed.hostname or "").lower()


@dataclass(slots=True)
class CompetitionMatch:
    competition: Competition | None = None
    edition: CompetitionEdition | None = None
    confidence: float = 0.0
    method: str = "none"
    reasons: list[str] = field(default_factory=list)
    needs_manual_review: bool = True


class AuthorityMatchService:
    auto_threshold = 0.90
    review_threshold = 0.72

    def match(
        self,
        db: Session,
        raw_name: str,
        *,
        year: int | None = None,
        aliases: list[str] | None = None,
        organizer_hint: str | None = None,
        domain_hint: str | None = None,
    ) -> CompetitionMatch:
        name = normalize_competition_name(raw_name)
        if not name:
            return CompetitionMatch(reasons=["empty normalized name"])
        exact = self._match_exact(db, raw_name, aliases)
        if exact:
            return self._attach_edition(exact, year, domain_hint)
        candidates = self._score_candidates(
            db, raw_name, organizer_hint=organizer_hint, domain_hint=domain_hint
        )
        if not candidates:
            return CompetitionMatch(reasons=["no candidate above review threshold"])
        best = candidates[0]
        if best[0] >= self.auto_threshold:
            return self._attach_edition(best[1], year, domain_hint)
        if best[0] >= self.review_threshold:
            return CompetitionMatch(
                competition=best[1],
                edition=self._find_edition(best[1], year),
                confidence=best[0],
                method="fuzzy_review",
                reasons=[best[2]],
                needs_manual_review=True,
            )
        return CompetitionMatch(reasons=[f"low confidence {best[0]:.2f}: {best[2]}"])

    def _match_exact(
        self,
        db: Session,
        raw_name: str,
        aliases: list[str] | None,
    ) -> Competition | None:
        raw_key = normalize_competition_name(raw_name)
        competition = db.execute(
            select(Competition).where(Competition.name == raw_name.strip())
        ).scalar_one_or_none()
        if competition:
            return competition
        alias_rows = list(
            db.execute(
                select(CompetitionAlias).where(CompetitionAlias.normalized_alias == raw_key)
            ).scalars()
        )
        if len(alias_rows) == 1:
            return alias_rows[0].competition
        if aliases:
            for alias in aliases:
                normalized = normalize_competition_name(alias)
                if normalized == raw_key:
                    continue
                alias_hit = list(
                    db.execute(
                        select(CompetitionAlias).where(
                            CompetitionAlias.normalized_alias == normalized
                        )
                    ).scalars()
                )
                if len(alias_hit) == 1:
                    return alias_hit[0].competition
                competition = db.execute(
                    select(Competition).where(Competition.name == alias.strip())
                ).scalar_one_or_none()
                if competition:
                    return competition
        canonical = HISTORICAL_NAME_MAP.get(raw_name.strip())
        if canonical:
            return db.execute(
                select(Competition).where(Competition.name == canonical)
            ).scalar_one_or_none()
        return None

    def _score_candidates(
        self,
        db: Session,
        raw_name: str,
        *,
        organizer_hint: str | None,
        domain_hint: str | None,
    ) -> list[tuple[float, Competition, str]]:
        base = strip_year_and_edition(raw_name)
        if not base:
            return []
        scored: list[tuple[float, Competition, str]] = []
        for competition in db.execute(select(Competition)).scalars():
            if not competition.is_competition:
                continue
            comp_base = strip_year_and_edition(competition.name)
            if not comp_base:
                continue
            ratio = SequenceMatcher(a=base, b=comp_base).ratio()
            if ratio < self.review_threshold:
                continue
            reason = f"base-name similarity {ratio:.2f}"
            if organizer_hint and self._organizer_matches(competition, organizer_hint):
                ratio = min(1.0, ratio + 0.08)
                reason += " + organizer hint"
            if domain_hint and self._domain_matches(competition, domain_hint):
                ratio = min(1.0, ratio + 0.06)
                reason += " + domain hint"
            if ratio >= 0.98:
                ratio = 1.0
            scored.append((ratio, competition, reason))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _organizer_matches(self, competition: Competition, hint: str) -> bool:
        haystacks = [
            competition.organizer or "",
            *(competition.co_organizers or []),
            *(competition.guiding_organizations or []),
            *(competition.undertakers or []),
        ]
        hint_key = normalize_competition_name(hint)
        return any(hint_key and hint_key in normalize_competition_name(item) for item in haystacks)

    def _domain_matches(self, competition: Competition, hint: str) -> bool:
        if not hint:
            return False
        if competition.official_website:
            competition_host = host_of(competition.official_website)
            if competition_host and competition_host.endswith(hint.strip().lower()):
                return True
        for source in competition.sources:
            if source.source_url and host_of(source.source_url).endswith(hint.strip().lower()):
                return True
        return False

    def _find_edition(
        self,
        competition: Competition,
        year: int | None,
    ) -> CompetitionEdition | None:
        if not year:
            return None
        return db_edition_for_year(competition.id, year, [e for e in competition.editions])

    def _attach_edition(
        self,
        competition: Competition,
        year: int | None,
        domain_hint: str | None,
    ) -> CompetitionMatch:
        edition = self._find_edition(competition, year) if competition else None
        return CompetitionMatch(
            competition=competition,
            edition=edition,
            confidence=1.0,
            method="exact",
            reasons=["exact name / alias match"],
            needs_manual_review=False,
        )


def db_edition_for_year(
    competition_id: int,
    year: int,
    editions: list[CompetitionEdition] | None = None,
) -> CompetitionEdition | None:
    if editions is None:
        return None
    matches = [edition for edition in editions if edition.year == year]
    return matches[0] if len(matches) == 1 else (matches[-1] if matches else None)
