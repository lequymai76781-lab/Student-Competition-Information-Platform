"""Ordinary-undergraduate production policy pipeline entry point.

Unlike the 985/211 runner, discovery is delegated to the bounded multi-stage
``GeneralUndergraduatePolicyDiscoveryService``. Downloading, parsing, classifying,
normalizing and persisting are all reused from ``UniversityPolicyPipeline``.

This runner does NOT mutate the existing 985/211 ``run_university`` path.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.crawler.discovery.general_undergraduate_policy_discovery import (
    GeneralUndergraduatePolicyDiscoveryService,
)
from app.crawler.discovery.university_discovery import UniversitySeed
from app.crawler.pipelines.university_policy_pipeline import (
    UniversityPolicyPipeline,
    result_to_dict,
)
from app.database.session import SessionLocal

GOLD = ROOT / "data/seeds/general_undergraduate_gold_set.json"
SNAPSHOT = ROOT / "data/seeds/general_undergraduate_gold_set_search_snapshot.json"
MASTER = ROOT / "data/seeds/general_undergraduate_master.json"
REPORT = ROOT / "data/reports/general_undergraduate_production_gold.json"
CHECKPOINT = ROOT / "data/checkpoints/general_undergraduate_production_gold.json"
RAW_STORAGE = ROOT / "data/raw/general_undergraduate_production"


def build_seed(school: dict) -> UniversitySeed:
    return UniversitySeed(
        name=school["school"],
        english_name=None,
        short_name=None,
        province=school.get("province", ""),
        city=school.get("city", school.get("province", "")),
        official_website=school["official_website"],
        official_domain=school["official_domain"],
        aliases=[],
        is_985=False,
        is_211=False,
        is_double_first_class=False,
    )


def run_school(
    db,
    *,
    school: dict,
    search_results: list[dict],
    discovery: GeneralUndergraduatePolicyDiscoveryService | None = None,
    pipeline: UniversityPolicyPipeline | None = None,
    max_pages: int = 24,
    max_attachments: int = 2,
    dry_run: bool = False,
) -> dict:
    discovery = discovery or GeneralUndergraduatePolicyDiscoveryService()
    pipeline = pipeline or UniversityPolicyPipeline(storage_root=RAW_STORAGE, respect_robots=True)
    found = discovery.discover(
        school=school["school"],
        official_website=school["official_website"],
        official_domain=school["official_domain"],
        search_results=search_results,
        max_pages=max_pages,
    )
    crawl = pipeline.run_university_from_discovered(
        db,
        build_seed(school),
        found.documents,
        max_attachments_per_page=max_attachments,
        dry_run=dry_run,
    )
    return {
        "school": school["school"],
        "discovery_status": found.status,
        "documents_discovered": len(found.documents),
        "channels_attempted": found.channels_attempted,
        "crawl": result_to_dict(crawl),
    }


def _collection_batches() -> dict[str, str]:
    master = json.loads(MASTER.read_text(encoding="utf-8"))["institutions"]
    return {row["name"]: row.get("collection_batch", "") for row in master}


def load_gold_schools(names: list[str] | None) -> list[dict]:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["results"]
    batches = _collection_batches()
    schools = [dict(row) for row in gold["schools"]]
    if names:
        allowed = set(names)
        schools = [row for row in schools if row["school"] in allowed]
    for row in schools:
        row["search_results"] = snapshot.get(row["school"], [])
        row["collection_batch"] = batches.get(row["school"], "")
    return schools


def load_master_schools(limit: int | None, names: list[str] | None) -> list[dict]:
    master = json.loads(MASTER.read_text(encoding="utf-8"))["institutions"]
    rows = []
    for row in master:
        if row.get("collection_batch") != "general_a" or not row.get("official_url"):
            continue
        from urllib.parse import urlparse

        domain = urlparse(row["official_url"]).netloc.lower().removeprefix("www.")
        if not domain:
            continue
        rows.append({
            "school": row["name"],
            "province": row.get("province", ""),
            "city": row.get("province", ""),
            "official_website": row["official_url"],
            "official_domain": domain,
            "collection_batch": "general_a",
            "search_results": [],
        })
    if names:
        allowed = set(names)
        rows = [row for row in rows if row["school"] in allowed]
    if limit:
        rows = rows[:limit]
    return rows


def select_run_schools(rows: list[dict], *, dry_run: bool) -> tuple[list[dict], list[dict]]:
    if dry_run:
        return rows, []
    selected = [row for row in rows if row.get("collection_batch") == "general_a"]
    skipped = [row for row in rows if row.get("collection_batch") != "general_a"]
    return selected, skipped


def report_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.source == "gold" and not args.names and not args.dry_run:
        return REPORT, CHECKPOINT
    suffix = args.source
    if args.names:
        suffix += "_partial"
    if args.dry_run:
        suffix += "_dry_run"
    return (
        ROOT / f"data/reports/general_undergraduate_production_{suffix}.json",
        ROOT / f"data/checkpoints/general_undergraduate_production_{suffix}.json",
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ordinary-undergraduate multi-stage policy pipeline.")
    parser.add_argument("--source", choices=["gold", "master"], default="gold")
    parser.add_argument("--names", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-pages", type=int, default=24)
    parser.add_argument("--max-attachments", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.source == "gold":
        schools = load_gold_schools(args.names)
    else:
        schools = load_master_schools(args.limit, args.names)
    schools, skipped = select_run_schools(schools, dry_run=args.dry_run)

    rows = []
    with SessionLocal() as db:
        for school in schools:
            row = run_school(
                db,
                school=school,
                search_results=school.get("search_results", []),
                max_pages=args.max_pages,
                max_attachments=args.max_attachments,
                dry_run=args.dry_run,
            )
            rows.append(row)
            print(json.dumps({
                "school": row["school"],
                "discovery_status": row["discovery_status"],
                "documents_discovered": row["documents_discovered"],
                "policies_found": row["crawl"]["policies_found"],
                "errors": len(row["crawl"]["errors"]),
            }, ensure_ascii=False), flush=True)

    status_counts = Counter(row["discovery_status"] for row in rows)
    payload = {
        "task": "GENERAL_UNDERGRADUATE_PRODUCTION_GOLD",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "dry_run": args.dry_run,
        "school_count": len(rows),
        "skipped_non_general_a": [row["school"] for row in skipped],
        "status_counts": dict(status_counts),
        "totals": {
            "documents_discovered": sum(row["documents_discovered"] for row in rows),
            "policies_found": sum(row["crawl"]["policies_found"] for row in rows),
            "documents_found": sum(row["crawl"]["documents_found"] for row in rows),
            "documents_parsed": sum(row["crawl"]["documents_parsed"] for row in rows),
            "competitions_found": sum(row["crawl"]["competitions_found"] for row in rows),
        },
        "schools": rows,
    }
    report_path, checkpoint_path = report_paths(args)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checkpoint_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status_counts": dict(status_counts), "totals": payload["totals"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
