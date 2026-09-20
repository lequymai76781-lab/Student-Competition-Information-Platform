"""Run the resumable shallow-first ordinary-undergraduate Batch A pilot."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select

from app.crawler.discovery.university_discovery import UniversitySeedLoader
from app.crawler.scheduler import PolicyCrawlerScheduler
from app.database.session import SessionLocal
from app.models import Competition, CompetitionPolicyRecognition, CompetitionSource, PolicyDocument, University
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.university_radar_discovery_service import UniversityRadarDiscoveryService

MASTER = ROOT / "data/seeds/general_undergraduate_master.json"
DIRECTORY = ROOT / "data/seeds/general_undergraduate_batch_a_directory.json"
CHECKPOINT = ROOT / "data/checkpoints/general_undergraduate_batch_a.json"
DISCOVERY = ROOT / "data/seeds/general_undergraduate_batch_a_discovery.json"
RUN_REPORT = ROOT / "data/reports/general_undergraduate_batch_a_run.json"
RAW_POLICY = ROOT / "data/raw/general_undergraduate_batch_a"
TASK = "GENERAL_UNDERGRADUATE_BATCH_A"
FINAL_STATUSES = {"VERIFIED_DATA", "VERIFIED_NO_PUBLIC_DATA", "ACCESS_LIMITED", "DEEP_PASS_REQUIRED", "AMBIGUOUS"}
CRAWL_BUDGET = {
    "max_department_entries": 6, "max_department_feeds": 4,
    "max_list_pages_per_department": 1, "max_department_articles": 12,
    "max_candidate_urls": 30, "max_page_fetches": 22,
    "max_known_entry_probes": 5, "max_internal_search_pages": 1,
}


def load_batch() -> list[dict]:
    master = json.loads(MASTER.read_text(encoding="utf-8"))["institutions"]
    rows = []
    for row in master:
        if row["collection_batch"] != "general_a":
            continue
        domain = urlparse(row["official_url"]).netloc.lower().removeprefix("www.")
        rows.append({
            "name": row["name"], "english_name": None, "short_name": None,
            "aliases": [], "province": row["province"], "city": row["province"],
            "university_type": "普通本科高校", "official_website": row["official_url"],
            "official_domain": domain, "is_985": False, "is_211": False,
            "is_double_first_class": False,
        })
    return rows


def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {"task": TASK, "collection_batch": "general_a", "schools": []}


def save_checkpoint(payload: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    temp = CHECKPOINT.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(CHECKPOINT)


def db_counts(db, university_id: int) -> dict[str, int]:
    recognitions = int(db.scalar(select(func.count()).select_from(CompetitionPolicyRecognition).where(
        CompetitionPolicyRecognition.university_id == university_id,
        CompetitionPolicyRecognition.is_demo.is_(False),
    )) or 0)
    relations = db.execute(__import__("sqlalchemy").text(
        "SELECT notice_type FROM university_competition_edition_relations WHERE university_id=:id AND is_demo=0"
    ), {"id": university_id}).all()
    participation = sum(row[0] in {"participation_news", "award_news"} for row in relations)
    return {"recognition": recognitions, "notification": len(relations) - participation, "participation": participation}


def register(db, rows: list[dict]) -> None:
    for row in rows:
        university = db.scalar(select(University).where(University.name == row["name"]))
        if university is None:
            university = University(name=row["name"], is_demo=False)
            db.add(university)
        for key in ("province", "city", "university_type", "official_website", "official_domain"):
            setattr(university, key, row[key])
        university.is_985 = university.is_211 = university.is_double_first_class = False
    db.commit()


def policy_pass(db, row: dict, timeout: int) -> dict:
    seed_path = Path(tempfile.mkdtemp(prefix="general_policy_")) / "seed.json"
    output_path = seed_path.with_name("output.json")
    seed_path.write_text(json.dumps([row], ensure_ascii=False), encoding="utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, str(BACKEND / "scripts/run_general_undergraduate_policy_school.py"),
             str(seed_path), str(output_path), str(RAW_POLICY)],
            cwd=BACKEND, capture_output=True, timeout=timeout,
        )
        if completed.returncode or not output_path.exists():
            detail = (completed.stderr or b"").decode("utf-8", "ignore")[-800:] or "no output"
            return {"status": "failed", "pages_discovered": 0, "pages_fetched": 0,
                    "documents_found": 0, "documents_parsed": 0, "policies_found": 0,
                    "competitions_found": 0, "errors": [detail]}
        return json.loads(output_path.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        return {"status": "failed", "pages_discovered": 0, "pages_fetched": 0,
                "documents_found": 0, "documents_parsed": 0, "policies_found": 0,
                "competitions_found": 0, "errors": [f"policy timeout after {timeout}s"]}

def radar_context(db):
    service = UniversityRadarDiscoveryService()
    try:
        competitions = list(db.execute(select(Competition).where(
            Competition.is_demo.is_(False), Competition.is_competition.is_(True)
        )).scalars())
        return service._build_matcher(db, competitions), service._reverse_search_names(db)
    finally:
        service.close()


def radar_pass(row: dict, matcher: dict, reverse_names: list[str], timeout: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="general_radar_"))
    source, output = tmp / "in.json", tmp / "out.json"
    source.write_text(json.dumps({
        "university": row, "matcher": matcher, "reverse_names": reverse_names,
        "observed_at": datetime.now(timezone.utc).isoformat(), "crawl_budget": CRAWL_BUDGET,
    }, ensure_ascii=False), encoding="utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, str(BACKEND / "scripts/run_general_undergraduate_school.py"), str(source), str(output)],
            cwd=BACKEND, capture_output=True, timeout=timeout,
        )
        if completed.returncode or not output.exists():
            return {"error": (completed.stderr or b"").decode("utf-8", "ignore")[-800:] or "no output"}
        return json.loads(output.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        return {"error": f"school timeout after {timeout}s"}


def import_radar(db, row: dict, radar: dict) -> dict:
    if "error" in radar:
        return {"relations_created": 0, "relations_updated": 0, "sources_created": 0, "sources_updated": 0}
    batch_name = f"general-a-{row['name']}"
    radar["report"]["batch_name"] = batch_name
    for key in ("leads", "relations"):
        for item in radar.get(key, []):
            item["batch_name"] = batch_name
            item["discovery_batch"] = "general_a"
    payload = {
        "version": "general-undergraduate-a-v1", "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "scope": "general_undergraduate", "batches": [{"name": batch_name, "universities": [row["name"]]}],
        "discovery_reports": [radar["report"]], "leads": radar.get("leads", []),
        "official_records": [], "edition_relations": radar.get("relations", []),
    }
    temp = Path(tempfile.mkdtemp(prefix="general_import_")) / "payload.json"
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = CompetitionDiscoveryImportService().import_json(db, temp, DIRECTORY, batch_name=batch_name)
    db.commit()
    return result


def choose_status(policy: dict, radar: dict, counts: dict) -> tuple[str, bool]:
    candidate_count = int((radar.get("report") or {}).get("candidate_articles", 0))
    if counts["recognition"] or policy.get("policies_found", 0) or candidate_count >= 10:
        return "DEEP_PASS_REQUIRED", True
    if any(counts.values()):
        return "VERIFIED_DATA", False
    errors = policy.get("errors", []) + ([radar["error"]] if radar.get("error") else [])
    if errors or policy.get("status") in {"failed", "partial"}:
        return "ACCESS_LIMITED", False
    if candidate_count:
        return "AMBIGUOUS", False
    return "VERIFIED_NO_PUBLIC_DATA", False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--school-timeout", type=int, default=75)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume-check-only", action="store_true")
    args = parser.parse_args()
    rows = load_batch()
    DIRECTORY.write_text(json.dumps({
        "scope": "general_undergraduate", "expected_count": len(rows), "universities": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checkpoint = load_checkpoint()
    completed = {row["school"] for row in checkpoint["schools"] if row.get("final_status") in FINAL_STATUSES}
    pending = [row for row in rows if row["name"] not in completed]
    if args.resume_check_only:
        print(json.dumps({"total": len(rows), "completed": len(completed), "next": pending[0]["name"] if pending else None}, ensure_ascii=False))
        return
    if args.limit:
        pending = pending[:args.limit]
    with SessionLocal() as db:
        register(db, rows)
        matcher, reverse_names = radar_context(db)
        for index, row in enumerate(pending, start=1):
            started = time.monotonic()
            university = db.scalar(select(University).where(University.name == row["name"]))
            before = db_counts(db, university.id)
            policy = policy_pass(db, row, args.school_timeout)
            db.commit()
            radar = radar_pass(row, matcher, reverse_names, args.school_timeout)
            imported = import_radar(db, row, radar)
            after = db_counts(db, university.id)
            status, deep = choose_status(policy, radar, after)
            report = radar.get("report", {})
            archive = {
                "school_id": university.id, "school": row["name"], "batch": "general_a",
                "checked_sources": list(dict.fromkeys([row["official_website"], *report.get("examined_pages", [])])),
                "candidate_count": report.get("candidate_articles", 0),
                "relations": after, "relations_delta": {k: after[k] - before[k] for k in after},
                "sources": imported.get("sources_created", 0) + imported.get("sources_updated", 0),
                "policy_pass": policy, "radar_status": report.get("status") or radar.get("error"),
                "pages_examined": report.get("pages_examined", 0) + policy.get("pages_fetched", 0),
                "request_count": report.get("pages_searched", 0) + policy.get("pages_fetched", 0),
                "final_status": status, "needs_deep_pass": deep,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
            }
            checkpoint["schools"].append(archive)
            checkpoint["last_completed_school"] = row["name"]
            save_checkpoint(checkpoint)
            print(json.dumps({"progress": f"{len(completed)+index}/{len(rows)}", "school": row["name"], "status": status}, ensure_ascii=False), flush=True)
    RUN_REPORT.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


