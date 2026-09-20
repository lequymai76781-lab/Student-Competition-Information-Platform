import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.crawler.discovery.university_discovery import UniversitySeedLoader
from app.crawler.pipelines.university_policy_pipeline import result_to_dict
from app.crawler.scheduler import PolicyCrawlerScheduler
from app.database.session import SessionLocal
from app.models import CompetitionPolicyRecognition, PolicyDocument, ReviewQueue
from app.repositories.policy_repository import PolicyRepository
from scripts.seed_985_universities import load_seed, upsert_universities

ROOT_DIR = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT_DIR / "data" / "seeds" / "985_universities.json"
RAW_STORAGE_ROOT = ROOT_DIR / "data" / "raw" / "985_policy_documents"
JSON_REPORT_PATH = ROOT_DIR / "data" / "reports" / "985_crawl_report.json"
MARKDOWN_REPORT_PATH = ROOT_DIR / "docs" / "data" / "985-crawl-report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 985 university policy data engineering pipeline.")
    parser.add_argument("--batch", choices=["first", "all"], default="first", help="Run first 5 universities or all 39 985 universities.")
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum candidate policy pages per university.")
    parser.add_argument("--max-attachments", type=int, default=2, help="Maximum attachments parsed from each policy page.")
    parser.add_argument("--dry-run", action="store_true", help="Run fetch/parse logic without committing database changes.")
    parser.add_argument("--ignore-robots", action="store_true", help="Disable robots.txt checks for local verification only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_seed()
    db = SessionLocal()
    try:
        created, updated = upsert_universities(db, rows)
        db.commit()

        scheduler = PolicyCrawlerScheduler(
            seed_path=SEED_PATH,
            storage_root=RAW_STORAGE_ROOT,
            respect_robots=not args.ignore_robots,
        )
        seed_loader = UniversitySeedLoader(SEED_PATH)
        seeds = seed_loader.first_batch() if args.batch == "first" else seed_loader.load_985()
        results = scheduler.pipeline.run_batch(
            db,
            seeds,
            max_pages_per_university=args.max_pages,
            max_attachments_per_page=args.max_attachments,
            dry_run=args.dry_run,
        )

        repository = PolicyRepository()
        coverage = repository.coverage_summary(db)
        report = build_report(
            args=args,
            seed_created=created,
            seed_updated=updated,
            coverage=coverage,
            results=[result_to_dict(result) for result in results],
            db_counts=current_counts(db),
        )
        write_reports(report)
        print(f"JSON report: {JSON_REPORT_PATH}")
        print(f"Markdown report: {MARKDOWN_REPORT_PATH}")
    finally:
        db.close()


def current_counts(db) -> dict[str, int]:
    statuses = [
        "recognized",
        "explicitly_not_recognized",
        "not_mentioned",
        "insufficient_evidence",
        "conflicting",
        "expired",
    ]
    recognition_counts = {
        status: int(
            db.scalar(
                select(func.count()).select_from(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.recognition_status == status,
                    CompetitionPolicyRecognition.is_demo.is_(False),
                )
            )
            or 0
        )
        for status in statuses
    }
    return {
        "policy_documents": int(db.scalar(select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))) or 0),
        "pending_review_items": int(db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending", ReviewQueue.is_demo.is_(False))) or 0),
        **{f"recognition_{key}": value for key, value in recognition_counts.items()},
    }


def build_report(
    *,
    args: argparse.Namespace,
    seed_created: int,
    seed_updated: int,
    coverage: dict[str, Any],
    results: list[dict[str, Any]],
    db_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_phase": "V0.2 - 985 university competition policy data engineering",
        "seed": {
            "expected_985_count": 39,
            "created": seed_created,
            "updated": seed_updated,
            "path": str(SEED_PATH),
        },
        "run": {
            "batch": args.batch,
            "max_pages_per_university": args.max_pages,
            "max_attachments_per_page": args.max_attachments,
            "dry_run": args.dry_run,
            "respect_robots": not args.ignore_robots,
        },
        "coverage": coverage,
        "db_counts": db_counts,
        "results": results,
        "rules": {
            "policy_priority": "MAJOR > COLLEGE > UNIVERSITY",
            "status_values": [
                "recognized",
                "explicitly_not_recognized",
                "not_mentioned",
                "insufficient_evidence",
                "conflicting",
                "expired",
            ],
            "not_mentioned_rule": "A policy document that does not mention a competition must not be treated as not recognized.",
            "ocr_rule": "No OCR is performed. Textless PDF files are routed to manual review as scanned_pdf.",
        },
        "github_license_risk": {
            "copied_external_code": False,
            "note": "Current V0.2 crawler is implemented in this repository. No GitHub crawler project code was copied. If future work ports code from Scrapy, crawl4ai, Firecrawl, or similar projects, license and NOTICE obligations must be reviewed before merging.",
        },
    }


def write_reports(report: dict[str, Any]) -> None:
    JSON_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MARKDOWN_REPORT_PATH.write_text(markdown_report(report), encoding="utf-8")


def markdown_report(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    db_counts = report["db_counts"]
    lines = [
        "# 985高校竞赛政策爬取报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 执行批次：{report['run']['batch']}",
        f"- 985种子：{coverage['universities_985_seeded']}/{coverage['universities_985_total']}",
        f"- 真实政策文档：{coverage['real_policy_documents']}",
        f"- 已核验政策文档：{coverage['verified_policy_documents']}",
        f"- 学院级政策文档：{coverage['college_policy_documents']}",
        f"- 待复核项：{coverage['review_queue_pending']}",
        "",
        "## 识别状态统计",
        "",
    ]
    for key in [
        "recognized",
        "explicitly_not_recognized",
        "not_mentioned",
        "insufficient_evidence",
        "conflicting",
        "expired",
    ]:
        lines.append(f"- {key}: {db_counts.get(f'recognition_{key}', 0)}")

    lines.extend(
        [
            "",
            "## 单校抓取结果",
            "",
            "| 学校 | 状态 | 发现链接 | 抓取页面 | 附件 | 解析附件 | 政策文档 | 竞赛命中 | 复核项 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["results"]:
        lines.append(
            "| {target_name} | {status} | {pages_discovered} | {pages_fetched} | {documents_found} | {documents_parsed} | {policies_found} | {competitions_found} | {review_items} |".format(
                **item
            )
        )

    failures = [error | {"target_name": item["target_name"]} for item in report["results"] for error in item["errors"]]
    lines.extend(["", "## 失败与待复核原则", ""])
    if failures:
        lines.extend(["| 学校 | URL | 错误 | 可重试 |", "| --- | --- | --- | --- |"])
        for error in failures[:50]:
            lines.append(f"| {error['target_name']} | {error['url']} | {error['message']} | {error['retryable']} |")
    else:
        lines.append("- 当前批次没有抓取失败。")

    lines.extend(
        [
            "",
            "## 解析策略",
            "",
            "- HTML：优先 BeautifulSoup，依赖缺失时退回标准库 HTMLParser。",
            "- PDF：优先 PyMuPDF，缺失时退回 pdfplumber；无文本层时只标记 scanned_pdf，不做 OCR。",
            "- DOCX：python-docx。",
            "- XLSX：openpyxl，读取工作表文本，不执行公式。",
            "",
            "## 结论边界",
            "",
            "- 政策优先级固定为 MAJOR > COLLEGE > UNIVERSITY。",
            "- 政策存在但未提及比赛时，只能输出 not_mentioned，不能推断为不认可。",
            "- 抓取失败、解析失败、短名歧义、低置信匹配均进入 ReviewQueue。",
            "- 当前实现未复制 GitHub 第三方爬虫项目代码；未来引入外部实现前必须核验许可证和 NOTICE 义务。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
