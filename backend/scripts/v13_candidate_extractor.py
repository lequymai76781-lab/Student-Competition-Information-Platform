"""Extract explicit, sentence-level field-evidence candidates from local crawls.

Scans the saved university-discovery snapshots (v04/v06/v07/v08/v081/debug) for
core competitions and prints only sentences that explicitly state verifiable
facts: 主办/承办/指导, 参赛对象/资格/条件, 报名截止, 竞赛时间, 举办地/届次.
Read-only; no DB writes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402


SEED_FILES = [
    "data/seeds/v04_university_discovery.json",
    "data/seeds/v06_985_competition_discovery.json",
    "data/seeds/v07_partial_rechecks.json",
    "data/seeds/v08_211_radar_discovery.json",
    "data/seeds/v081_211_radar_fix_discovery.json",
    "data/seeds/v081_211_radar_fix_discovery_audited.json",
    "data/seeds/v081_debug_bjtu_ustb_discovery.json",
    "data/seeds/v081_debug5_discovery.json",
    "data/seeds/v081_debug5_final_discovery.json",
]

TEXT_KEYS = (
    "raw_content",
    "raw_title",
    "notice_title",
    "detected_competition_name",
    "competition_name",
    "content",
    "description",
)

KEYWORD = re.compile(r"主办|承办|协办|指导单位|参赛对象|参赛资格|报名条件|报名截止|竞赛时间|举办|总决赛")
SENTENCE_SPLIT = re.compile(r"(?<=[。！？；;])")


def iter_records(obj):
    if isinstance(obj, dict):
        if any(key in obj for key in TEXT_KEYS):
            yield obj
        for value in obj.values():
            yield from iter_records(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_records(value)


def text_of(record: dict) -> str:
    parts = []
    for key in TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    return "\n".join(parts)


def main() -> None:
    target_ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
    with SessionLocal() as db:
        queue = json.loads(
            (PROJECT_ROOT / "data/reports/v12_missing_field_queue.json").read_text(encoding="utf-8")
        )
        names = {
            row["competition_id"]: row["name"]
            for row in queue["rows"]
            if not target_ids or row["competition_id"] in target_ids
        }
        db_names = dict(
            db.execute(
                text("SELECT id, name FROM competitions WHERE id IN (SELECT id FROM competitions)")
            ).fetchall()
        )
    aliases = {**names}
    for comp_id, name in names.items():
        aliases[comp_id] = name.replace("“", "").replace("”", "").replace("（", "(").replace("）", ")")

    collected: dict[int, list[dict]] = {comp_id: [] for comp_id in names}
    for seed in SEED_FILES:
        path = PROJECT_ROOT / seed
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print("skip", seed, exc)
            continue
        for record in iter_records(payload):
            blob = text_of(record)
            if len(blob) < 30:
                continue
            for comp_id, target in aliases.items():
                target_plain = re.sub(r"[\s“”\"'（）()]+", "", target)
                blob_plain = re.sub(r"[\s“”\"'（）()]+", "", blob)
                if target_plain not in blob_plain:
                    continue
                sentences = [
                    s.strip()
                    for s in SENTENCE_SPLIT.split(blob)
                    if len(s.strip()) > 8 and KEYWORD.search(s)
                ]
                if not sentences:
                    continue
                collected[comp_id].append(
                    {
                        "seed": seed,
                        "record_title": (
                            record.get("raw_title")
                            or record.get("notice_title")
                            or record.get("competition_name")
                            or record.get("detected_competition_name")
                            or ""
                        )[:180],
                        "source_url": record.get("source_url") or record.get("internal_notice_url") or record.get("official_url") or "",
                        "source_name": record.get("source_name") or record.get("university") or "",
                        "source_type": record.get("source_type") or "",
                        "reliability": record.get("reliability_tier") or record.get("authority") or "",
                        "sentences": sentences[:12],
                    }
                )

    for comp_id in sorted(collected):
        if not target_ids and comp_id not in (9, 10, 11, 19, 20, 22, 23, 25, 27, 28, 29, 30, 31, 33, 37, 38, 39, 40, 41, 42, 43, 44, 45, 48, 49, 50, 51, 52, 53, 54, 55, 57, 58, 60, 61, 62, 64, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87):
            continue
        rows = collected[comp_id]
        if not rows:
            continue
        print(f"\n########## {comp_id} {names[comp_id]}  ({len(rows)} records) ##########")
        seen_urls = set()
        for row in rows[:18]:
            key = row["source_url"] or row["record_title"]
            if key in seen_urls:
                continue
            seen_urls.add(key)
            print(f"  [{row['source_type'] or '-'} tier={row['reliability']}] {row['source_name']}")
            print(f"  title: {row['record_title']}")
            print(f"  url: {row['source_url']}")
            for sentence in row["sentences"][:6]:
                print("   ·", sentence[:260])


if __name__ == "__main__":
    main()
