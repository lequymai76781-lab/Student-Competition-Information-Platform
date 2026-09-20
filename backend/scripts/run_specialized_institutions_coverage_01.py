"""Audit and idempotently register the specialized-institution master list.

This batch deliberately does not turn discovery hits into competitions.  It
separates institution registration from evidence-backed relation ingestion.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "v02.sqlite"
MASTER = ROOT / "data" / "seeds" / "specialized_institutions.json"
REPORT = ROOT / "data" / "reports" / "specialized_institutions_coverage_01.json"
CATEGORIES = ("sports", "dance", "film", "drama", "media")


def table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def load_master() -> list[dict]:
    rows = json.loads(MASTER.read_text(encoding="utf-8"))
    required = {
        "name", "official_name", "official_url", "category", "province", "city",
        "institution_type", "existing_school_id", "already_covered", "priority",
    }
    names: set[str] = set()
    for row in rows:
        missing = required - row.keys()
        if missing:
            raise ValueError(f"{row.get('name', '<unknown>')} missing {sorted(missing)}")
        if row["name"] in names:
            raise ValueError(f"duplicate institution: {row['name']}")
        names.add(row["name"])
        if not row["category"] or not set(row["category"]).issubset(CATEGORIES):
            raise ValueError(f"invalid category: {row['name']}")
        if row["priority"] not in {"P0", "P1", "P2"}:
            raise ValueError(f"invalid priority: {row['name']}")
        if urlparse(row["official_url"]).scheme != "https":
            raise ValueError(f"non-https official URL: {row['name']}")
    return rows


def relation_counts(db: sqlite3.Connection, school_id: int) -> dict[str, int]:
    recognition = 0
    notification = 0
    participation = 0
    professional_keys: set[tuple[int, str]] = set()
    if table_exists(db, "competition_policy_recognitions"):
        recognition = db.execute(
            """SELECT COUNT(*) FROM competition_policy_recognitions
               WHERE university_id=? AND is_demo=0
               AND recognition_status IN ('recognized','expired')""",
            (school_id,),
        ).fetchone()[0]
    if table_exists(db, "university_competition_edition_relations"):
        rows = db.execute(
            """SELECT r.notice_type, r.metadata, e.competition_id, r.internal_notice_url
               FROM university_competition_edition_relations r
               JOIN competition_editions e ON e.id=r.competition_edition_id
               WHERE r.university_id=? AND r.is_demo=0""",
            (school_id,),
        ).fetchall()
        for notice_type, metadata_value, competition_id, source_url in rows:
            if notice_type in {"participation_news", "award_news"}:
                participation += 1
            else:
                notification += 1
            if metadata_value:
                try:
                    if json.loads(metadata_value).get("professional_reference"):
                        professional_keys.add((competition_id, source_url))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
    if all(table_exists(db, name) for name in (
        "competition_policy_recognitions", "policy_documents", "competition_fact_sources"
    )):
        rows = db.execute(
            """SELECT DISTINCT pr.competition_id, p.source_url
               FROM competition_policy_recognitions pr
               JOIN policy_documents p ON p.id=pr.policy_document_id
               JOIN competition_fact_sources f
                 ON f.competition_id=pr.competition_id AND f.source_url=p.source_url
               WHERE pr.university_id=? AND pr.is_demo=0
                 AND f.field_name='professional_reference'
                 AND f.source_type='professional_institution_official'""",
            (school_id,),
        ).fetchall()
        professional_keys.update((competition_id, source_url) for competition_id, source_url in rows)
    return {
        "recognition": recognition,
        "notification": notification,
        "participation": participation,
        "professional_reference": len(professional_keys),
    }

def register_missing(db: sqlite3.Connection, rows: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    for row in rows:
        found = db.execute("SELECT id FROM universities WHERE name=?", (row["name"],)).fetchone()
        if found:
            continue
        domain = urlparse(row["official_url"]).netloc.lower().removeprefix("www.")
        db.execute(
            """INSERT INTO universities
               (name, province, city, university_type, is_985, is_211,
                is_double_first_class, official_website, official_domain,
                policy_crawl_status, competition_discovery_status, is_demo,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, 'not_started', 'not_started', 0, ?, ?)""",
            (row["name"], row["province"], row["city"], row["institution_type"],
             row["official_url"], domain, now, now),
        )
        created += 1
    return created


def audit(db: sqlite3.Connection, rows: list[dict]) -> dict:
    by_category = {category: {"target": 0, "present": 0, "with_data": 0} for category in CATEGORIES}
    institutions = []
    states = Counter()
    totals = Counter()
    for row in rows:
        found = db.execute("SELECT id FROM universities WHERE name=?", (row["name"],)).fetchone()
        counts = relation_counts(db, found[0]) if found else {
            "recognition": 0, "notification": 0, "participation": 0,
            "professional_reference": 0,
        }
        if not found:
            state = "absent"
        elif counts["recognition"]:
            state = "has_recognition"
        elif counts["notification"]:
            state = "notification_only"
        elif counts["participation"]:
            state = "participation_only"
        else:
            state = "no_relation_data"
        states[state] += 1
        totals.update(counts)
        for category in row["category"]:
            by_category[category]["target"] += 1
            by_category[category]["present"] += int(bool(found))
            by_category[category]["with_data"] += int(any(counts.values()))
        institutions.append({
            **row,
            "existing_school_id": found[0] if found else None,
            "already_covered": bool(found),
            "coverage_state": state,
            **counts,
        })
    return {
        "task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(DB),
        "target_total": len(rows),
        "states": dict(states),
        "relation_totals": dict(totals),
        "by_category": by_category,
        "institutions": institutions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="register missing universities")
    args = parser.parse_args()
    rows = load_master()
    with sqlite3.connect(DB) as db:
        before = audit(db, rows)
        created = register_missing(db, rows) if args.apply else 0
        if args.apply:
            db.commit()
        after = audit(db, rows)
    result = {"mode": "apply" if args.apply else "audit", "created": created, "before": before, "after": after}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    MASTER.write_text(
        json.dumps(after["institutions"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "mode": result["mode"], "created": created,
        "target_total": after["target_total"], "states": after["states"],
        "by_category": after["by_category"], "relation_totals": after["relation_totals"],
        "report": str(REPORT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
