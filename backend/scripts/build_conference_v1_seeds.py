"""Build static Academic Conference V1 seed JSON files.

Outputs are written under data/seeds/conference_v1/ and are consumed by the
conference seed import service (idempotent).  Run from the backend folder:
    python scripts/build_conference_v1_seeds.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conference_authority_service import (  # noqa: E402
    CONFERENCE_DISCIPLINES,
    CONFERENCE_ORGANIZATION_ROLES,
    CONFERENCE_SOURCE_TYPE_AUTHORITY,
    DISCOVERY_CANDIDATE_STATUSES,
    REJECTION_REASONS,
    authority_level_for,
    can_prove_school_fact,
)
from scripts.conference_v1_seeds.domestic_series import CN_SERIES  # noqa: E402
from scripts.conference_v1_seeds.discovery_candidates import DISCOVERY_CANDIDATES  # noqa: E402
from scripts.conference_v1_seeds.discipline_mapping_v12 import v12_discipline_mappings  # noqa: E402
from scripts.conference_v1_seeds.disciplines_v12 import SERIES_DISCIPLINE_V12  # noqa: E402
from scripts.conference_v1_seeds.editions import EDITIONS  # noqa: E402
from scripts.conference_v1_seeds.editions_v11 import EDITIONS_V11  # noqa: E402
from scripts.conference_v1_seeds.editions_v111 import EDITIONS_V111  # noqa: E402
from scripts.conference_v1_seeds.international_series import INTL_SERIES  # noqa: E402
from scripts.conference_v1_seeds.opportunities_v12 import OPPORTUNITIES_V12  # noqa: E402
from scripts.conference_v1_seeds.org_catalog import ORG_CATALOG  # noqa: E402
from scripts.conference_v1_seeds.source_registry import SOURCE_REGISTRY  # noqa: E402
from scripts.conference_v1_seeds.v11_series import v11_new_series  # noqa: E402
from scripts.conference_v1_seeds.v111_series import v111_new_series  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "seeds" / "conference_v1"

# ---------------------------------------------------------------------------
# V1.1.1 recognition evidence backfill
# ---------------------------------------------------------------------------
# CCF officially released the revised (2022) recommended international
# conference/journal directory on 2023-03-08. The announcement page is the
# edition-level official reference; per-conference rows of the directory are
# published as an official attachment that this curation pass does not parse
# line-by-line, so historical CCF 2022 rows keep "legacy" evidence status
# instead of being presented as fully_verified. Rows that already carry their
# own source_url/evidence (e.g. PRCV with a pending_evidence note) are left
# untouched.
CCF_DIRECTORY_2022_OFFICIAL_URL = (
    "https://www.ccf.org.cn/Academic_Evaluation/By_category/2023-03-08/787209.shtml"
)
CCF_DIRECTORY_2022_EVIDENCE = (
    "CCF 官网 2023-03-08 正式发布《中国计算机学会推荐国际学术会议和期刊目录》"
    "（2022 版，第五版目录）公告；本行分级沿用 V1 依据 2022 版目录写入的历史"
    "分类，逐会议行文仍待官方目录附件核对。"
)
RECOGNITION_EVIDENCE_STATUSES = ("fully_verified", "legacy", "pending_evidence")


def _backfill_ccf_directory_evidence(series: list[dict]) -> None:
    for item in series:
        for rec in item.get("external_classifications") or []:
            if str(rec.get("system", "")).upper() != "CCF":
                continue
            if rec.get("source_url") or rec.get("evidence"):
                continue
            rec["source_url"] = CCF_DIRECTORY_2022_OFFICIAL_URL
            rec["evidence"] = CCF_DIRECTORY_2022_EVIDENCE
            rec["evidence_status"] = "legacy"


def _validate_recognition_evidence(all_series: list[dict]) -> None:
    total = 0
    for item in all_series:
        for rec in item.get("external_classifications") or []:
            assert rec.get("source_url"), f"{item['key']}: recognition 缺 source_url"
            assert rec.get("evidence"), f"{item['key']}: recognition 缺 evidence"
            assert rec.get("evidence_status") in RECOGNITION_EVIDENCE_STATUSES, (
                f"{item['key']}: 非法 recognition evidence_status"
            )
            total += 1
    return total


def _validate_series(series: list[dict]) -> None:
    keys: set[str] = set()
    for item in series:
        key = item["key"]
        assert key not in keys, f"duplicate series key: {key}"
        keys.add(key)
        discipline = item["discipline"]
        assert discipline in CONFERENCE_DISCIPLINES, f"{key}: bad discipline {discipline!r}"
        # One primary discipline per Series; secondary lists may never repeat it.
        secondaries = item.get("secondary_disciplines") or []
        assert discipline not in secondaries, f"{key}: secondary 重复 primary discipline"
        assert len(set(secondaries)) == len(secondaries), f"{key}: secondary 重复"
        assert all(d in CONFERENCE_DISCIPLINES for d in secondaries), (
            f"{key}: 非法 secondary discipline"
        )
        for org in item.get("organizations", []):
            assert org["role"] in CONFERENCE_ORGANIZATION_ROLES, (
                f"{key}: bad org role {org['role']!r}"
            )
        for source in item.get("sources", []):
            assert source["source_type"] in CONFERENCE_SOURCE_TYPE_AUTHORITY, (
                f"{key}: bad source_type {source['source_type']!r}"
            )
            if source.get("published_at"):
                datetime.fromisoformat(source["published_at"])
            if source.get("retrieved_at"):
                datetime.fromisoformat(source["retrieved_at"])


def _validate_editions(series_keys: set[str]) -> None:
    seen: set[tuple[str, int]] = set()
    for item in EDITIONS + EDITIONS_V11 + EDITIONS_V111:
        pair = (item["series_key"], item["year"])
        assert pair not in seen, f"duplicate edition pair: {pair}"
        seen.add(pair)
        assert pair[0] in series_keys, f"edition references unknown series: {pair}"
        if item.get("start_date") and item.get("end_date"):
            assert item["start_date"] <= item["end_date"], f"start after end: {pair}"
        for field in (
            "start_date",
            "end_date",
            "paper_deadline",
            "notification_date",
            "registration_deadline",
        ):
            if item.get(field):
                datetime.fromisoformat(item[field])
        for source in item.get("sources", []):
            assert source["source_type"] in CONFERENCE_SOURCE_TYPE_AUTHORITY, (
                f"{pair}: bad source_type {source['source_type']!r}"
            )
        seen_schools: set[str] = set()
        for relation in item.get("school_relations", []):
            assert relation["school_name"] not in seen_schools
            seen_schools.add(relation["school_name"])
            assert relation["relation_type"] in {
                "organizer",
                "co_organizer",
                "undertaker",
                "co_undertaker",
                "host",
                "academic_support",
                "local_organizer",
                "published_notice",
                "participation_notice",
                "call_for_papers_notice",
                "reimbursement_notice",
                "other",
            }
            edition_has_official_source = any(
                authority_level_for(source.get("source_type")) in {"S", "A"}
                for source in item.get("sources", [])
            )
            assert relation.get("notice_url") or edition_has_official_source, (
                f"{pair}: SchoolConference 关系必须有 notice_url 或 S/A 级 Edition 来源作证据"
            )
            assert can_prove_school_fact(
                relation.get("source_type", "university_official")
            ), f"{pair}: SchoolConference 关系来源必须是 S/A/B 官方证据"


def _validate_registry() -> None:
    keys: set[str] = set()
    for item in SOURCE_REGISTRY:
        assert item["key"] not in keys
        keys.add(item["key"])
        assert item["authority_level"] in {"S", "A", "B", "C"}
        assert item["source_type"] in CONFERENCE_SOURCE_TYPE_AUTHORITY


def _validate_v11_catalog(series: list[dict]) -> None:
    """V1.1 curation guardrails: alias collisions are tolerated only when the
    canonical alias service merges them; here we only check org coverage."""
    for item in series:
        for org in item.get("organizations", []):
            assert org["name"] in ORG_CATALOG, f"{item['key']}: org not catalogued: {org['name']!r}"


def _validate_candidates() -> None:
    for item in DISCOVERY_CANDIDATES:
        assert authority_level_for(item["source_type"]) == "C", (
            f"发现池候选必须为 C 级来源: {item['raw_name']!r}"
        )
        assert item["status"] in DISCOVERY_CANDIDATE_STATUSES
        if item["status"] == "rejected":
            assert item["rejection_reason"] in REJECTION_REASONS, (
                f"rejected 候选缺少受控 rejection_reason: {item['raw_name']!r}"
            )


def _validate_v12_disciplines(all_series: list[dict]) -> None:
    for item in all_series:
        key = item["key"]
        primary = item["discipline"]
        secondaries = item.get("secondary_disciplines") or []
        assert primary not in secondaries, f"{key}: secondary 重复 primary"
        assert len(set(secondaries)) == len(secondaries), f"{key}: secondary 重复"
        assert all(code in CONFERENCE_DISCIPLINES for code in secondaries), (
            f"{key}: 非法 secondary discipline"
        )
        evidence_rows = item.get("discipline_evidence") or []
        assert len(set((row["discipline"], row["role"]) for row in evidence_rows)) == len(
            evidence_rows
        ), f"{key}: discipline_evidence 重复"
        for row in evidence_rows:
            assert row["discipline"] in CONFERENCE_DISCIPLINES, (
                f"{key}: discipline_evidence 非法学科"
            )
            assert row["role"] in {"primary", "secondary"}
            assert row.get("source_url"), f"{key}: discipline_evidence 缺 source_url"


def _attach_v12_disciplines(all_series: list[dict]) -> None:
    for item in all_series:
        extra = SERIES_DISCIPLINE_V12.get(item["key"])
        if not extra:
            continue
        item.setdefault("secondary_disciplines", extra["secondary_disciplines"])
        item.setdefault("discipline_evidence", extra["discipline_evidence"])


def _attach_opportunities(all_editions: list[dict]) -> None:
    for item in all_editions:
        pair = (item["series_key"], item["year"])
        opportunities = OPPORTUNITIES_V12.get(pair) or []
        if not opportunities:
            continue
        seen: set[tuple[str, str]] = set()
        for opp in opportunities:
            assert opp["series_key"] == pair[0] and opp["year"] == pair[1]
            assert opp["opportunity_type"] in {
                "paper_submission", "abstract_submission", "poster", "student_paper",
                "student_forum", "undergraduate_forum", "graduate_forum",
                "doctoral_consortium", "young_scholar_forum", "workshop", "tutorial",
                "mentoring", "volunteer", "student_registration", "travel_grant",
                "student_award", "competition", "summer_school", "other",
            }, f"{pair}: 非法 opportunity_type"
            assert opp.get("official_url"), f"{pair}: opportunity 缺 official_url"
            dup_key = (opp["opportunity_type"], opp["official_url"])
            assert dup_key not in seen, f"{pair}: 重复 opportunity {dup_key}"
            seen.add(dup_key)
        item["opportunities"] = opportunities


def main() -> None:
    _validate_series(INTL_SERIES)
    _validate_series(CN_SERIES)
    v11_series = v11_new_series()
    _validate_series(v11_series)
    v111_series = v111_new_series()
    _validate_series(v111_series)
    _validate_v11_catalog(v111_series)
    _backfill_ccf_directory_evidence(INTL_SERIES)
    _backfill_ccf_directory_evidence(CN_SERIES)
    _backfill_ccf_directory_evidence(v11_series)
    _backfill_ccf_directory_evidence(v111_series)
    all_series = INTL_SERIES + CN_SERIES + v11_series + v111_series
    recognition_total = _validate_recognition_evidence(all_series)
    series_keys = {item["key"] for item in all_series}
    _validate_editions(series_keys)
    _attach_v12_disciplines(all_series)
    _validate_v12_disciplines(all_series)
    _validate_registry()
    _validate_candidates()
    all_editions = EDITIONS + EDITIONS_V11 + EDITIONS_V111
    _attach_opportunities(all_editions)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "series": all_series,
        "meta": {
            "schema_version": "1",
            "generated_at": generated_at,
            "curation_policy": (
                "S/A 来源可验证会议身份；B 级高校来源仅补充承办与校内信息；"
                "C 级第三方来源只允许进入发现池。未核实的日期/状态保持 NULL。"
            ),
            "stage": "Academic Conference V1.1.1（证据债务清理 + 学科再平衡 + Edition 学生机会补全）",
            "count": len(all_series),
            "recognition_count": recognition_total,
            "recognition_evidence_policy": (
                "全部 recognition 记录带 CCF 官方公告 source_url 与 evidence；"
                "逐会议目录行未核对前 evidence_status 为 legacy，PRCV 历史 CCF-C 存疑记为 "
                "pending_evidence；禁止无证据行被当作 fully_verified。"
            ),
        },
    }
    edition_payload = {
        "editions": all_editions,
        "meta": {
            "schema_version": "1",
            "generated_at": generated_at,
            "count": len(all_editions),
        },
    }
    registry_payload = {
        "entries": SOURCE_REGISTRY,
        "meta": {
            "schema_version": "1",
            "generated_at": generated_at,
            "count": len(SOURCE_REGISTRY),
        },
    }
    candidate_payload = {
        "candidates": DISCOVERY_CANDIDATES,
        "meta": {
            "schema_version": "1",
            "generated_at": generated_at,
            "count": len(DISCOVERY_CANDIDATES),
            "note": "V1.1 发现池仅收录真实观测到的 C 级第三方页面；pending/rejected 用于去噪，绝不直接升级为 Series/Edition。",
        },
    }
    mapping_payload = {
        "mappings": v12_discipline_mappings(),
        "meta": {
            "schema_version": "1",
            "generated_at": generated_at,
            "count": len(v12_discipline_mappings()),
            "note": "Major/专业词汇 -> Conference 受控学科映射，仅用于检索词汇关联，不做推荐或评分。",
        },
    }
    org_payload = {
        "entries": [
            {"name": name, **attrs}
            for name, attrs in sorted(ORG_CATALOG.items())
        ],
        "meta": {
            "schema_version": "1",
            "generated_at": generated_at,
            "count": len(ORG_CATALOG),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("series_seed.json", payload),
        ("editions_seed.json", edition_payload),
        ("sources_registry.json", registry_payload),
        ("discovery_candidates.json", candidate_payload),
        ("discipline_mappings.json", mapping_payload),
        ("organizations_catalog.json", org_payload),
    ):
        (OUT_DIR / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "output_dir": str(OUT_DIR),
                "series_total": len(all_series),
                "series_v1": len(INTL_SERIES) + len(CN_SERIES),
                "series_v11_added": len(v11_series),
                "series_v111_added": len(v111_series),
                "recognition_records_with_evidence": recognition_total,
                "editions_total": len(all_editions),
                "editions_v1": len(EDITIONS),
                "editions_v11_added": len(EDITIONS_V11),
                "editions_v111_added": len(EDITIONS_V111),
                "opportunities_total": sum(
                    len(item.get("opportunities", [])) for item in all_editions
                ),
                "discipline_mappings_total": len(v12_discipline_mappings()),
                "candidates_total": len(DISCOVERY_CANDIDATES),
                "registry_total": len(SOURCE_REGISTRY),
                "organizations_catalogued": len(ORG_CATALOG),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
