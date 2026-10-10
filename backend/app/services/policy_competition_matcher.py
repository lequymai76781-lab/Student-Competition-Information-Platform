"""Read-only, conservative matching of policy names to formal competitions."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionAlias


_EDITION = re.compile(r"^(?:(?:20\d{2}|19\d{2})年?\s*)?(?:第[一二三四五六七八九十百千万零〇\d]+届\s*)?")
_TRACK = re.compile(r"(?:赛道|专项赛|分赛|组别|赛区|总决赛)")
_AMBIGUOUS_SERIES = {"挑战杯", "互联网+", "创新大赛", "大创"}


def normalize_policy_name(raw_name: str) -> str:
    value = unicodedata.normalize("NFKC", raw_name or "").strip()
    value = _EDITION.sub("", value)
    value = re.sub(r"[\s\u3000·•“”‘’'\"《》<>（）()\[\]【】、，,。.;；:：!！?？—–-]", "", value)
    return value.casefold()


def _result(name: str, status: str, confidence: float, reason: str, *, matched_id: int | None = None, candidate_ids: list[int] | None = None) -> dict:
    result = {
        "normalized_name": name,
        "match_status": status,
        "match_confidence": confidence,
        "matched_competition_id": matched_id,
        "match_reason": reason,
    }
    if candidate_ids is not None:
        result["candidate_ids"] = candidate_ids
    return result


def match_policy_competition(db: Session, raw_name: str, *, hints: dict | None = None) -> dict:
    """Only unique, directly verified labels may become automatic matches."""
    normalized = normalize_policy_name(raw_name)
    if not normalized:
        return _result(normalized, "NEEDS_MANUAL_MATCH", 0.0, "empty_name", candidate_ids=[])

    competitions = list(db.execute(select(Competition).where(
        Competition.is_demo.is_(False),
        Competition.is_competition.is_(True),
        Competition.entity_type == "competition",
        Competition.status == "active",
    )).scalars().all())
    by_id = {item.id: item for item in competitions}
    aliases = list(db.execute(select(CompetitionAlias).where(CompetitionAlias.is_demo.is_(False))).scalars().all())
    exact: dict[int, set[str]] = {}
    weak: dict[int, set[str]] = {}

    for item in competitions:
        for field, label in (("name", item.name), ("short_name", item.short_name), ("english_name", item.english_name)):
            if label and normalize_policy_name(label) == normalized:
                exact.setdefault(item.id, set()).add(field)
        for label in item.former_names or []:
            if isinstance(label, str) and normalize_policy_name(label) == normalized:
                weak.setdefault(item.id, set()).add("unverified_former_name")
    for alias in aliases:
        if alias.competition_id not in by_id or normalize_policy_name(alias.alias) != normalized:
            continue
        target = exact if alias.is_verified else weak
        target.setdefault(alias.competition_id, set()).add("verified_alias" if alias.is_verified else "unverified_alias")

    candidate_ids = sorted(set(exact) | set(weak))
    if len(candidate_ids) > 1:
        return _result(normalized, "NEEDS_MANUAL_MATCH", 0.0, "ambiguous_exact_or_alias", candidate_ids=candidate_ids)
    if exact and normalized not in {normalize_policy_name(item) for item in _AMBIGUOUS_SERIES}:
        item_id = next(iter(exact))
        item = by_id[item_id]
        # A parent title with a requested child track is never silently mapped to the parent.
        if _TRACK.search(raw_name) and not _TRACK.search(item.name):
            return _result(normalized, "NEEDS_MANUAL_MATCH", 0.0, "child_track_requires_exact_match", candidate_ids=[item_id])
        method = sorted(exact[item_id])[0]
        return _result(item.name, "AUTO_MATCHED", 1.0, method, matched_id=item_id)
    if candidate_ids:
        reason = "ambiguous_series" if normalized in {normalize_policy_name(item) for item in _AMBIGUOUS_SERIES} else ",".join(sorted(weak.get(candidate_ids[0], exact.get(candidate_ids[0], set()))))
        return _result(normalized, "NEEDS_QUICK_CONFIRM", 0.7, reason, candidate_ids=candidate_ids)

    scored: list[tuple[float, int]] = []
    for item in competitions:
        canonical = normalize_policy_name(item.name)
        score = SequenceMatcher(None, normalized, canonical).ratio()
        if normalized.replace("中国", "全国", 1) == canonical or normalized.replace("全国", "中国", 1) == canonical:
            score = max(score, 0.85)
        if score >= 0.7:
            scored.append((score, item.id))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    if scored:
        top = scored[0][0]
        close = [item_id for score, item_id in scored if score >= max(0.7, top - 0.08)]
        status = "NEEDS_MANUAL_MATCH" if len(close) > 1 or _TRACK.search(raw_name) else "NEEDS_QUICK_CONFIRM"
        reason = "ambiguous_similar_names" if len(close) > 1 else "child_track_or_fuzzy_name" if _TRACK.search(raw_name) else "similar_name_unverified"
        return _result(normalized, status, round(top, 3), reason, candidate_ids=close)
    return _result(normalized, "NEEDS_MANUAL_MATCH", 0.0, "no_formal_match", candidate_ids=[])
