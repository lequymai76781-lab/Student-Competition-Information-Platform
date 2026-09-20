"""Verify ordinary-undergraduate production coverage against the frozen Gold Set.

Read-only. By default, verification is limited to ``general_a`` because Batch B
is intentionally frozen. A database copy can be supplied for isolated trials.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.crawler.discovery.url_normalizer import OfficialUrlNormalizer

GOLD = ROOT / "data/seeds/general_undergraduate_gold_set.json"
MASTER = ROOT / "data/seeds/general_undergraduate_master.json"
DB = ROOT / "data/v02.sqlite"
REPORT = ROOT / "data/reports/general_undergraduate_production_gold_verify.json"
JOB_TYPE = "general_undergraduate_policy_discovery"


def canonical(url: str) -> str:
    return OfficialUrlNormalizer().normalize(url)


def load_gold_schools(*, scope: str = "general_a") -> list[dict]:
    schools = [dict(row) for row in json.loads(GOLD.read_text(encoding="utf-8"))["schools"]]
    if scope == "all":
        return schools
    batches = {
        row["name"]: row.get("collection_batch", "")
        for row in json.loads(MASTER.read_text(encoding="utf-8"))["institutions"]
    }
    for school in schools:
        school["collection_batch"] = batches.get(school["school"], "")
    return [school for school in schools if school["collection_batch"] == scope]


def verify(db_path: Path, *, scope: str = "general_a") -> dict:
    schools = load_gold_schools(scope=scope)
    school_names = [row["school"] for row in schools]
    normalizer = OfficialUrlNormalizer()
    db = sqlite3.connect(db_path)
    try:
        name_placeholders = ",".join("?" for _ in school_names) or "NULL"
        job_rows = db.execute(
            f"""SELECT id, target_id, target_name, status
                FROM crawler_jobs
                WHERE job_type=? AND target_name IN ({name_placeholders})""",
            [JOB_TYPE, *school_names],
        ).fetchall()
        job_ids = [row[0] for row in job_rows]
        job_placeholders = ",".join("?" for _ in job_ids) or "NULL"
        docs = db.execute(
            f"""SELECT id, official_domain, attachment_url, source_url, crawler_job_id
                FROM policy_documents
                WHERE crawler_job_id IN ({job_placeholders})""",
            job_ids,
        ).fetchall()

        doc_urls: set[str] = set()
        off_domain = []
        for doc_id, official_domain, attachment_url, source_url, _ in docs:
            for value in (attachment_url, source_url):
                if value:
                    doc_urls.add(canonical(value))
            evidence_url = attachment_url or source_url
            if evidence_url and not normalizer.is_official(evidence_url, official_domain):
                off_domain.append({
                    "id": doc_id,
                    "official_domain": official_domain,
                    "source_url": source_url,
                    "attachment_url": attachment_url,
                })

        false_negatives = []
        found = 0
        expected_total = 0
        expected_attachment = 0
        found_attachment = 0
        for school in schools:
            for item in school["expected_evidence"]:
                expected_total += 1
                target = canonical(item["expected_source_url"])
                is_attachment = item["document_type"] != "html"
                expected_attachment += int(is_attachment)
                if target in doc_urls:
                    found += 1
                    found_attachment += int(is_attachment)
                else:
                    false_negatives.append({
                        "school": school["school"],
                        "target": item["expected_title"],
                        "expected_url": item["expected_source_url"],
                    })

        return {
            "task": "GENERAL_UNDERGRADUATE_PRODUCTION_GOLD_VERIFY",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "method": "read-only DB reconciliation against the frozen gold set",
            "database": str(db_path.resolve()),
            "scope": scope,
            "gold_school_count": len(schools),
            "expected_documents": expected_total,
            "found_documents": found,
            "document_recall": round(found / expected_total, 4) if expected_total else 0,
            "attachment_recall": round(found_attachment / expected_attachment, 4) if expected_attachment else 0,
            "false_negatives": false_negatives,
            "jobs": {
                "count": len(job_rows),
                "by_school": [{"school": row[2], "status": row[3]} for row in job_rows],
            },
            "off_domain_documents": off_domain,
        }
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify ordinary-undergraduate production Gold coverage.")
    parser.add_argument("--database", type=Path, default=DB)
    parser.add_argument("--scope", choices=["general_a", "all"], default="general_a")
    parser.add_argument("--report", type=Path, default=REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = verify(args.database, scope=args.scope)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "scope": payload["scope"],
        "gold_school_count": payload["gold_school_count"],
        "document_recall": payload["document_recall"],
        "attachment_recall": payload["attachment_recall"],
        "expected_documents": payload["expected_documents"],
        "found_documents": payload["found_documents"],
        "false_negatives": len(payload["false_negatives"]),
        "off_domain_documents": len(payload["off_domain_documents"]),
        "jobs": payload["jobs"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()