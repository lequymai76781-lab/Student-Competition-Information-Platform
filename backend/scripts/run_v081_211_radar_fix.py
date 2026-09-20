"""V0.8.1 - re-run only the partial non-985 211 universities with multi-channel discovery.

Targets the 50 schools that were partial in V0.8, applies sitemap / department
feed / navigation / external search / wechat / reverse-match discovery, imports
the results, and writes a per-school quality + acceptance report.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionLead,
    CompetitionSource,
    University,
    UniversityCompetitionDiscoveryReport,
    UniversityCompetitionEditionRelation,
)
from app.repositories.stats_repository import StatsRepository
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.competition_discovery_service import CompetitionDiscoveryService
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.university_radar_discovery_service import UniversityRadarDiscoveryService


def main() -> None:
    parser = argparse.ArgumentParser(description="V0.8.1 multi-channel 211 partial-school discovery fix.")
    parser.add_argument(
        "--universities",
        default=str(PROJECT_ROOT / "data" / "seeds" / "211_non_985_universities.json"),
    )
    parser.add_argument(
        "--seed",
        default=str(PROJECT_ROOT / "data" / "seeds" / "v081_211_radar_fix_discovery.json"),
    )
    parser.add_argument(
        "--report",
        default=str(PROJECT_ROOT / "data" / "reports" / "v081_211_radar_fix_report.json"),
    )
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--import-only", action="store_true")
    parser.add_argument("--names", action="append", help="Only run these universities (repeatable).")
    parser.add_argument("--status", default="partial", help="Only run schools whose latest report status matches.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel discovery workers.")
    parser.add_argument("--school-timeout", type=int, default=300, help="Per-school subprocess timeout in seconds.")
    args = parser.parse_args()

    universities_path = Path(args.universities)
    seed_path = Path(args.seed)
    report_path = Path(args.report)
    directory = json.loads(universities_path.read_text(encoding="utf-8"))
    university_rows = directory["universities"]

    with SessionLocal() as db:
        if not args.import_only:
            selected = select_rows(db, university_rows, names=args.names, status=args.status)
            print(f"Selected {len(selected)} schools for V0.8.1 re-run")
            matcher, reverse_names, observed_at = discovery_context(db)
            payload = discover_isolated(
                selected,
                matcher,
                reverse_names,
                observed_at,
                workers=args.workers,
                school_timeout=args.school_timeout,
            )
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.discover_only:
                print(json.dumps(discovery_snapshot(payload), ensure_ascii=False, indent=2))
                return
        else:
            payload = json.loads(seed_path.read_text(encoding="utf-8"))
            batch_names = {name for batch in payload.get("batches", []) for name in batch["universities"]}
            selected = [row for row in university_rows if row["name"] in batch_names]
            print(f"Importing {len(selected)} schools from seed {seed_path.name}")

        importer = CompetitionDiscoveryImportService()
        fact_service = FactIntelligenceService()
        intelligence = CompetitionIntelligenceService()
        batch_results = []
        for batch in payload.get("batches", []):
            result = importer.import_json(db, seed_path, universities_path, batch_name=batch["name"])
            result["source_tiers"] = fact_service.refresh_source_tiers(db)
            result["verification"] = fact_service.refresh_verification(db)
            db.commit()
            batch_results.append({"batch": batch["name"], **result})

        tags = intelligence.apply_tags(db)
        statistics = intelligence.refresh_all(db)
        freshness = CompetitionFreshnessService().refresh_all(db)
        db.commit()
        coverage = CompetitionDiscoveryService().v08_coverage_summary(db)
        previous = load_previous_report(PROJECT_ROOT / "data" / "reports" / "v08_211_radar_report.json")
        report = {
            "version": "v0.8.1",
            "stage": "211赛事雷达修复与Discovery召回率提升",
            "scope": "211_non_985",
            "selected_schools": [row["name"] for row in selected],
            "previous_v08": {
                "status_counts": previous.get("status_counts"),
                "lead_count": previous.get("lead_count"),
                "partial_reasons": previous.get("partial_reasons"),
                "partial_reason_stats": previous.get("partial_reason_stats"),
                "partial_reason_classified": previous.get("partial_reason_classified"),
                "root_cause": previous.get("root_cause"),
            },
            "discovery": discovery_snapshot(payload),
            "batches": batch_results,
            "freshness": freshness,
            "tags": tags,
            "statistics": statistics,
            "platform_stats": StatsRepository().get_platform_stats(db),
            "coverage": coverage,
            "per_school_quality": per_school_quality(db, selected),
            "remaining_partial_classified": classify_current_reasons(per_school_quality(db, selected)),
            "database_counts": database_counts(db),
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def select_rows(db, rows: list[dict], *, names: list[str] | None, status: str) -> list[dict]:
    if names:
        name_set = set(names)
        return [row for row in rows if row["name"] in name_set]
    universities = {item.name: item for item in db.execute(select(University)).scalars()}
    selected: list[dict] = []
    for row in rows:
        university = universities.get(row["name"])
        if university is None:
            continue
        report = (
            db.execute(
                select(UniversityCompetitionDiscoveryReport)
                .where(UniversityCompetitionDiscoveryReport.university_id == university.id)
                .order_by(UniversityCompetitionDiscoveryReport.last_crawled_at.desc())
            )
            .scalars()
            .first()
        )
        latest = report.status if report else university.competition_discovery_status
        if latest == status:
            selected.append(row)
    return selected


def discovery_context(db):
    service = UniversityRadarDiscoveryService()
    try:
        competitions = list(
            db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.is_competition.is_(True),
                )
            ).scalars()
        )
        matcher = service._build_matcher(db, competitions)
        reverse_names = service._reverse_search_names(db)
    finally:
        service.close()
    return matcher, reverse_names, datetime.now(timezone.utc)


def discover_isolated(
    rows: list[dict],
    matcher: dict,
    reverse_names: list[str],
    observed_at: datetime,
    *,
    workers: int,
    school_timeout: int,
) -> dict:
    runner = Path(__file__).resolve().parent / "run_v081_school_runner.py"
    tmpdir = Path(tempfile.mkdtemp(prefix="v081_discovery_"))
    results: dict[int, dict] = {}

    def run_school(index: int, university: dict) -> dict:
        in_path = tmpdir / f"in_{index:03d}.json"
        out_path = tmpdir / f"out_{index:03d}.json"
        in_path.write_text(
            json.dumps(
                {
                    "university": university,
                    "matcher": matcher,
                    "reverse_names": reverse_names,
                    "observed_at": observed_at.isoformat(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        try:
            completed = subprocess.run(
                [sys.executable, str(runner), str(in_path), str(out_path)],
                cwd=str(BACKEND_DIR),
                timeout=school_timeout,
                capture_output=True,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or b"").decode("utf-8", "ignore")[-500:]
                return failed_school(university, f"子进程异常({completed.returncode}): {detail}")
            if out_path.exists():
                return json.loads(out_path.read_text(encoding="utf-8"))
            return failed_school(university, "子进程未产出结果文件")
        except subprocess.TimeoutExpired:
            return failed_school(university, f"单校超时（>{school_timeout}s），已终止")
        except Exception as exc:  # noqa: BLE001
            return failed_school(university, f"调度异常：{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(run_school, index, row): index for index, row in enumerate(rows)}
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()

    ordered = [results[index] for index in range(len(rows))]
    payload: dict = {
        "version": "v0.8.1",
        "retrieved_at": observed_at.isoformat(),
        "scope": "211_non_985",
        "batches": [],
        "discovery_reports": [],
        "leads": [],
        "official_records": [],
        "edition_relations": [],
    }
    for index in range(0, len(rows), 8):
        batch_name = f"v081-211-fix-batch-{index // 8 + 1:02d}"
        batch = rows[index : index + 8]
        payload["batches"].append(
            {"name": batch_name, "universities": [row["name"] for row in batch], "size": len(batch)}
        )
        for discovered in ordered[index : index + 8]:
            discovered["report"]["batch_name"] = batch_name
            for lead in discovered.get("leads", []):
                lead["batch_name"] = batch_name
            for relation in discovered.get("relations", []):
                relation["batch_name"] = batch_name
            payload["discovery_reports"].append(discovered["report"])
            payload["leads"].extend(discovered.get("leads", []))
            payload["edition_relations"].extend(discovered.get("relations", []))
    return payload


def failed_school(university: dict, reason: str) -> dict:
    report = {
        "university": university["name"],
        "batch_name": "",
        "status": "failed",
        "methods_attempted": [],
        "methods_successful": [],
        "pages_examined": 0,
        "candidate_articles": 0,
        "pages_searched": 0,
        "competition_leads": 0,
        "matched_competitions": 0,
        "new_competitions": 0,
        "new_editions": 0,
        "official_sources": 0,
        "university_notice_count": 0,
        "college_notice_count": 0,
        "current_registration_count": 0,
        "edition_2026_count": 0,
        "wechat_leads": 0,
        "internal_deadlines": 0,
        "last_crawled_at": datetime.now(timezone.utc).isoformat(),
        "reason": f"Discovery异常：{reason}",
        "errors": [{"method": "pipeline", "error": reason}],
        "examined_pages": [],
        "channel_stats": {},
        "search_queries": [],
        "source_domains": [],
        "seed_version": "v0.8.1",
    }
    return {"report": report, "leads": [], "relations": []}


def discovery_snapshot(payload: dict) -> dict:
    reports = payload.get("discovery_reports", [])
    method_counts = Counter(method for report in reports for method in report.get("methods_successful", []))
    return {
        "version": payload.get("version"),
        "batch_count": len(payload.get("batches", [])),
        "school_count": len(reports),
        "status_counts": dict(Counter(item["status"] for item in reports)),
        "methods_successful": dict(method_counts),
        "lead_count": len(payload.get("leads", [])),
        "pages_examined": sum(item.get("pages_examined", 0) for item in reports),
        "candidate_articles": sum(item.get("candidate_articles", 0) for item in reports),
        "wechat_leads": sum(item.get("wechat_leads", 0) for item in reports),
        "matched_leads": sum(bool(item.get("detected_competition_name")) for item in payload.get("leads", [])),
        "edition_relations": len(payload.get("edition_relations", [])),
        "internal_deadlines": sum(item.get("internal_deadlines", 0) for item in reports),
        "schools": reports,
    }


def load_previous_report(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    reports = payload.get("discovery", {}).get("schools", [])
    partials = [item for item in reports if item.get("status") == "partial"]
    reason_counts = Counter(item.get("reason") for item in partials)
    return {
        "status_counts": payload.get("discovery", {}).get("status_counts"),
        "lead_count": payload.get("discovery", {}).get("lead_count"),
        "partial_reasons": [{"university": item["university"], "reason": item.get("reason")} for item in partials],
        "partial_reason_stats": dict(reason_counts),
        "partial_reason_classified": classify_partial_reasons(partials),
        "root_cause": (
            "V0.8 唯一官网发现通道依赖搜狗(sogou.com)的 site: 检索，运行时段搜狗持续返回 HTTP 403，"
            "导致 49/50 所 partial 学校没有拿到任何官方 URL；剩余 1 所（北京工业大学）拿到结果但页面抓取失败。"
            "另外 22 所被标记 completed 的学校实际 0 Lead，因为旧逻辑把“检索返回0且无报错”直接当作 completed。"
            "因此 73 所学校只有 1 条 Lead，匹配已有 Competition = 0 是发现层直接断流的结果，而非匹配层失效。"
        ),
    }


def classify_partial_reasons(partials: list[dict]) -> dict[str, int]:
    categories = {
        "SEARCH_ENDPOINT_403": 0,
        "SITE_403": 0,
        "SEARCH_UNAVAILABLE": 0,
        "DYNAMIC_SEARCH": 0,
        "NO_RESULTS": 0,
        "TIMEOUT": 0,
        "SSL_ERROR": 0,
        "NAVIGATION_FAILED": 0,
        "CONTENT_FILTERED": 0,
        "PARSER_FAILED": 0,
        "OTHER": 0,
    }
    for item in partials:
        reason = item.get("reason") or ""
        if "HTTP 403" in reason or "HTTP 429" in reason:
            categories["SEARCH_ENDPOINT_403"] += 1
        elif "抓取失败" in reason or "跳出官方域名" in reason:
            categories["NAVIGATION_FAILED"] += 1
        elif "未发现" in reason:
            categories["NO_RESULTS"] += 1
        else:
            categories["OTHER"] += 1
    return categories


def classify_current_reasons(quality_rows: list[dict]) -> dict[str, int]:
    categories = {
        "SEARCH_ENDPOINT_403": 0,
        "SITE_403": 0,
        "SEARCH_UNAVAILABLE": 0,
        "DYNAMIC_SEARCH": 0,
        "NO_RESULTS": 0,
        "TIMEOUT": 0,
        "SSL_ERROR": 0,
        "NAVIGATION_FAILED": 0,
        "CONTENT_FILTERED": 0,
        "PARSER_FAILED": 0,
        "OTHER": 0,
    }
    for row in quality_rows:
        if row.get("status") not in {"partial", "failed", "blocked"}:
            continue
        reason = row.get("reason") or ""
        errors = " ".join(item.get("error", "") for item in (row.get("errors") or []))
        if "HTTP 403" in errors or "HTTP 403" in reason or "安全验证" in reason or "限流" in reason:
            categories["SEARCH_ENDPOINT_403"] += 1
        elif "HTTP 412" in errors:
            categories["SITE_403"] += 1
        elif "超时" in reason:
            categories["TIMEOUT"] += 1
        elif "未发现" in reason or "0条候选" in reason:
            categories["NO_RESULTS"] += 1
        else:
            categories["OTHER"] += 1
    return categories


def per_school_quality(db, selected: list[dict]) -> list[dict]:
    rows: list[dict] = []
    universities = {item.name: item for item in db.execute(select(University)).scalars()}
    leads_by_university: dict[str, list] = {}
    for lead in db.execute(select(CompetitionLead)).scalars():
        university_name = (lead.metadata_json or {}).get("university")
        if university_name:
            leads_by_university.setdefault(university_name, []).append(lead)
    for row in selected:
        university = universities.get(row["name"])
        if university is None:
            continue
        report = (
            db.execute(
                select(UniversityCompetitionDiscoveryReport)
                .where(UniversityCompetitionDiscoveryReport.university_id == university.id)
                .order_by(UniversityCompetitionDiscoveryReport.last_crawled_at.desc())
            )
            .scalars()
            .first()
        )
        relations = list(
            db.execute(
                select(UniversityCompetitionEditionRelation)
                .where(UniversityCompetitionEditionRelation.university_id == university.id)
            ).scalars()
        )
        leads = leads_by_university.get(university.name, [])
        rows.append(
            {
                "university": university.name,
                "status": report.status if report else None,
                "methods_attempted": report.methods_attempted if report else [],
                "methods_successful": report.methods_successful if report else [],
                "pages_examined": report.pages_examined if report else 0,
                "candidate_articles": report.candidate_articles if report else 0,
                "competition_leads": report.competition_leads if report else len(leads),
                "matched_competitions": report.matched_competitions if report else 0,
                "new_competitions": report.new_competitions if report else 0,
                "new_editions": report.new_editions if report else 0,
                "internal_deadlines": report.internal_deadlines if report else sum(
                    1 for relation in relations if relation.internal_registration_deadline
                ),
                "relations": len(relations),
                "errors": (report.metadata_json or {}).get("errors", []) if report else [],
                "reason": report.reason if report else None,
            }
        )
    return rows


def database_counts(db) -> dict:
    models = {
        "universities": University,
        "competitions": Competition,
        "competition_editions": CompetitionEdition,
        "competition_leads": CompetitionLead,
        "competition_sources": CompetitionSource,
        "university_competition_edition_relations": UniversityCompetitionEditionRelation,
        "competition_fact_revisions": CompetitionFactRevision,
    }
    return {name: db.scalar(select(func.count()).select_from(model)) or 0 for name, model in models.items()}


if __name__ == "__main__":
    main()
