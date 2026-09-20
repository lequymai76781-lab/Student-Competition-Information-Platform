"""Generate a read-only recovery audit of the current SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def scalar(db: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(db.execute(sql, params).fetchone()[0] or 0)


def columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def present(db: sqlite3.Connection, table: str, expression: str) -> int:
    return scalar(db, f"SELECT COUNT(*) FROM {table} WHERE {expression}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="../data/v02.sqlite")
    parser.add_argument("--output")
    args = parser.parse_args()
    database = Path(args.database).resolve()
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }

    def count(table: str) -> int:
        return scalar(db, f"SELECT COUNT(*) FROM {table}") if table in tables else 0

    report: dict[str, object] = {
        "database": str(database),
        "database_bytes": database.stat().st_size,
        "tables": {table: count(table) for table in sorted(tables)},
    }

    if "competitions" in tables:
        report["competitions"] = {
            "total": count("competitions"),
            "non_demo": present(db, "competitions", "COALESCE(is_demo, 0) = 0"),
            "demo": present(db, "competitions", "COALESCE(is_demo, 0) = 1"),
            "official_website": present(db, "competitions", "TRIM(COALESCE(official_website, '')) <> ''"),
            "organizer": present(db, "competitions", "TRIM(COALESCE(organizer, '')) <> ''"),
            "description": present(db, "competitions", "TRIM(COALESCE(description, '')) <> ''"),
            "founded_or_first_year": present(db, "competitions", "founded_year IS NOT NULL OR first_held_year IS NOT NULL"),
            "history_text": present(db, "competitions", "TRIM(COALESCE(development_history, '')) <> ''"),
            "history_timeline": present(db, "competitions", "history_timeline IS NOT NULL AND history_timeline NOT IN ('[]', 'null', '')"),
            "official_verified": present(db, "competitions", "COALESCE(is_official_verified, 0) = 1"),
            "detail_ready": present(db, "competitions", "COALESCE(detail_ready, 0) = 1"),
            "exact_duplicate_names": scalar(db, "SELECT COUNT(*) FROM (SELECT name FROM competitions GROUP BY name HAVING COUNT(*) > 1)"),
        }
    if "competition_editions" in tables:
        report["competition_editions"] = {
            "total": count("competition_editions"),
            "with_any_deadline": present(db, "competition_editions", "registration_deadline IS NOT NULL OR submission_deadline IS NOT NULL"),
            "with_official_url": present(db, "competition_editions", "TRIM(COALESCE(official_url, '')) <> '' OR TRIM(COALESCE(official_notice_url, '')) <> ''"),
            "verified": present(db, "competition_editions", "COALESCE(is_verified, 0) = 1"),
        }
    if "competition_sources" in tables:
        report["competition_sources"] = {
            "total": count("competition_sources"),
            "official": present(db, "competition_sources", "COALESCE(is_official, 0) = 1"),
            "verified": present(db, "competition_sources", "COALESCE(is_verified, 0) = 1"),
            "valid_http_url": present(db, "competition_sources", "source_url LIKE 'http://%' OR source_url LIKE 'https://%'"),
        }
    if "universities" in tables:
        report["universities"] = {
            "total": count("universities"),
            "non_demo": present(db, "universities", "COALESCE(is_demo, 0) = 0"),
            "is_985": present(db, "universities", "COALESCE(is_985, 0) = 1"),
            "is_211": present(db, "universities", "COALESCE(is_211, 0) = 1"),
            "with_official_website": present(db, "universities", "TRIM(COALESCE(official_website, '')) <> ''"),
            "exact_duplicate_names": scalar(db, "SELECT COUNT(*) FROM (SELECT name FROM universities GROUP BY name HAVING COUNT(*) > 1)"),
        }
    relation_tables = [
        "university_competition_policies",
        "competition_policy_recognitions",
        "university_competition_edition_relations",
    ]
    report["university_competition_relations"] = {
        table: count(table) for table in relation_tables if table in tables
    }
    if "conference_series" in tables:
        series_cols = columns(db, "conference_series")
        report["conference_series"] = {
            "total": count("conference_series"),
            "with_official_website": present(db, "conference_series", "TRIM(COALESCE(official_website, '')) <> ''") if "official_website" in series_cols else 0,
            "with_acronym": present(db, "conference_series", "TRIM(COALESCE(acronym, '')) <> ''") if "acronym" in series_cols else 0,
            "with_history": present(db, "conference_series", "TRIM(COALESCE(history_summary, '')) <> ''") if "history_summary" in series_cols else 0,
            "exact_duplicate_names": scalar(db, "SELECT COUNT(*) FROM (SELECT name FROM conference_series GROUP BY name HAVING COUNT(*) > 1)"),
        }
    if "conference_editions" in tables:
        edition_cols = columns(db, "conference_editions")
        report["conference_editions"] = {
            "total": count("conference_editions"),
            "with_dates": present(db, "conference_editions", "start_date IS NOT NULL OR end_date IS NOT NULL") if "start_date" in edition_cols else 0,
            "with_submission_deadline": present(db, "conference_editions", "paper_submission_deadline IS NOT NULL") if "paper_submission_deadline" in edition_cols else 0,
            "with_cfp": present(db, "conference_editions", "TRIM(COALESCE(cfp_url, '')) <> ''") if "cfp_url" in edition_cols else 0,
            "with_location": present(db, "conference_editions", "TRIM(COALESCE(location, '')) <> ''") if "location" in edition_cols else 0,
            "verified": present(db, "conference_editions", "COALESCE(is_verified, 0) = 1") if "is_verified" in edition_cols else 0,
        }
    if "conference_sources" in tables:
        report["conference_sources"] = {
            "total": count("conference_sources"),
            "official": present(db, "conference_sources", "COALESCE(is_official, 0) = 1"),
            "verified": present(db, "conference_sources", "COALESCE(is_verified, 0) = 1"),
            "valid_http_url": present(db, "conference_sources", "source_url LIKE 'http://%' OR source_url LIKE 'https://%'"),
        }
    if "conference_opportunities" in tables:
        report["conference_opportunities"] = {
            "total": count("conference_opportunities"),
            "with_deadline": present(db, "conference_opportunities", "deadline IS NOT NULL"),
            "verified": present(db, "conference_opportunities", "COALESCE(is_verified, 0) = 1"),
        }
    if "conference_discovery_candidates" in tables:
        report["conference_candidates_by_status"] = {
            row[0]: row[1]
            for row in db.execute("SELECT status, COUNT(*) FROM conference_discovery_candidates GROUP BY status")
        }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
