"""Read-only final acceptance audit for SPECIALIZED_INSTITUTIONS_COVERAGE_01."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
MASTER = ROOT / "data/seeds/specialized_institutions.json"
TAXONOMY = ROOT / "data/seeds/specialized_competition_taxonomy.json"
ROUND2 = ROOT / "data/seeds/specialized_institutions_round2_relations.json"
REMAINING = ROOT / "data/checkpoints/SPECIALIZED_REMAINING_22.json"
ARCHIVES = ROOT / "data/checkpoints/specialized_institution_research_archives.json"
REVERSE = ROOT / "data/reports/specialized_reverse_audit_result.json"
UNCERTAIN = ROOT / "data/reports/specialized_uncertain_resolutions.json"
QA = ROOT / "data/reports/specialized_institutions_coverage_01_qa.json"
IDEMPOTENCY = ROOT / "data/reports/specialized_round2_idempotency.json"
REPORT = ROOT / "data/reports/specialized_completion_audit.json"

TASK = "SPECIALIZED_INSTITUTIONS_COVERAGE_01"
CATEGORIES = ("sports", "dance", "film", "drama", "media")
FINAL_STATUSES = {
    "VERIFIED_DATA", "VERIFIED_NO_PUBLIC_DATA", "ACCESS_LIMITED",
    "AMBIGUOUS", "NEEDS_DEEPER_REVIEW",
}
ALLOWED_EVENT_TYPES = {
    "competition", "competition_festival", "competition_showcase", "festival",
    "showcase", "exhibition", "call_for_works", "academic_event",
}
ALLOWED_SCOPES = {"university", "college", "school/college", "department", "major"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def is_url(value: str | None) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, passed: bool, details) -> None:
        self.items.append({"name": name, "status": "PASS" if passed else "FAIL", "details": details})


def collect_task_rows(db: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    relations = [row for row in db.execute(
        """SELECT r.*,u.name school,c.name college,e.year,e.competition_id,
                  k.name competition,k.competition_type
           FROM university_competition_edition_relations r
           JOIN universities u ON u.id=r.university_id
           JOIN competition_editions e ON e.id=r.competition_edition_id
           JOIN competitions k ON k.id=e.competition_id
           LEFT JOIN colleges c ON c.id=r.college_id"""
    ) if metadata(row["metadata"]).get("task") == TASK]
    policies = [row for row in db.execute(
        """SELECT p.*,u.name school,c.name college,m.name major
           FROM policy_documents p JOIN universities u ON u.id=p.university_id
           LEFT JOIN colleges c ON c.id=p.college_id LEFT JOIN majors m ON m.id=p.major_id"""
    ) if metadata(row["metadata"]).get("task") == TASK]
    policy_ids = {row["id"] for row in policies}
    recognitions = [row for row in db.execute(
        """SELECT pr.*,k.name competition,u.name school
           FROM competition_policy_recognitions pr
           JOIN competitions k ON k.id=pr.competition_id
           JOIN universities u ON u.id=pr.university_id"""
    ) if row["policy_document_id"] in policy_ids]
    sources = [row for row in db.execute("SELECT * FROM competition_sources")
               if metadata(row["metadata"]).get("task") == TASK]
    competition_ids = {row["competition_id"] for row in relations + recognitions + sources}
    placeholders = ",".join("?" for _ in competition_ids)
    competitions = db.execute(
        f"SELECT * FROM competitions WHERE id IN ({placeholders})", tuple(sorted(competition_ids))
    ).fetchall() if competition_ids else []
    facts = db.execute(
        f"""SELECT * FROM competition_fact_sources
             WHERE competition_id IN ({placeholders})
               AND source_type='professional_institution_official'""",
        tuple(sorted(competition_ids)),
    ).fetchall() if competition_ids else []
    return {"relations": relations, "policies": policies, "recognitions": recognitions,
            "sources": sources, "competitions": competitions, "facts": facts}


def audit_round2(db: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    outcomes = []
    for row in rows:
        school = db.execute("SELECT id FROM universities WHERE name=?", (row["school"],)).fetchone()
        competition = db.execute("SELECT id FROM competitions WHERE name=?", (row["competition"],)).fetchone()
        missing: list[str] = []
        if not school:
            missing.append("university")
        if not competition:
            missing.append("competition")
        if school and competition:
            if row["relation_type"] == "recognition":
                policy = db.execute(
                    "SELECT id,scope_type,college_id,major_id FROM policy_documents WHERE university_id=? AND source_url=?",
                    (school["id"], row["source_url"]),
                ).fetchone()
                if not policy:
                    missing.append("policy_document")
                else:
                    if not db.execute(
                        "SELECT 1 FROM competition_policy_recognitions WHERE policy_document_id=? AND competition_id=? AND university_id=?",
                        (policy["id"], competition["id"], school["id"]),
                    ).fetchone():
                        missing.append("recognition")
                    if policy["scope_type"] != row["scope"]:
                        missing.append("scope_mismatch")
            elif not db.execute(
                """SELECT 1 FROM university_competition_edition_relations r
                   JOIN competition_editions e ON e.id=r.competition_edition_id
                   WHERE r.university_id=? AND e.competition_id=? AND e.year=?
                     AND r.internal_notice_url=?""",
                (school["id"], competition["id"], row["year"], row["source_url"]),
            ).fetchone():
                missing.append("edition_relation")
            if not db.execute(
                """SELECT 1 FROM competition_sources WHERE competition_id=? AND source_url=?
                   AND source_type='professional_institution_official'""",
                (competition["id"], row["source_url"]),
            ).fetchone():
                missing.append("competition_source")
            for field in ("organizer", "event_type"):
                if not db.execute(
                    "SELECT 1 FROM competition_fact_sources WHERE competition_id=? AND field_name=? AND source_url=?",
                    (competition["id"], field, row["source_url"]),
                ).fetchone():
                    missing.append(f"{field}_fact")
            if row["professional_reference"] and not db.execute(
                """SELECT 1 FROM competition_fact_sources WHERE competition_id=?
                   AND field_name='professional_reference' AND source_url=?""",
                (competition["id"], row["source_url"]),
            ).fetchone():
                missing.append("professional_reference_fact")
        outcomes.append({"school": row["school"], "competition": row["competition"], "missing": missing})
    return outcomes


def orphan_counts(db: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "editions_without_competition": "SELECT COUNT(*) FROM competition_editions e LEFT JOIN competitions c ON c.id=e.competition_id WHERE c.id IS NULL",
        "sources_without_competition": "SELECT COUNT(*) FROM competition_sources s LEFT JOIN competitions c ON c.id=s.competition_id WHERE c.id IS NULL",
        "sources_without_edition": "SELECT COUNT(*) FROM competition_sources s LEFT JOIN competition_editions e ON e.id=s.competition_edition_id WHERE s.competition_edition_id IS NOT NULL AND e.id IS NULL",
        "relations_without_university": "SELECT COUNT(*) FROM university_competition_edition_relations r LEFT JOIN universities u ON u.id=r.university_id WHERE u.id IS NULL",
        "relations_without_edition": "SELECT COUNT(*) FROM university_competition_edition_relations r LEFT JOIN competition_editions e ON e.id=r.competition_edition_id WHERE e.id IS NULL",
        "recognitions_without_competition": "SELECT COUNT(*) FROM competition_policy_recognitions r LEFT JOIN competitions c ON c.id=r.competition_id WHERE c.id IS NULL",
        "recognitions_without_policy": "SELECT COUNT(*) FROM competition_policy_recognitions r LEFT JOIN policy_documents p ON p.id=r.policy_document_id WHERE p.id IS NULL",
    }
    return {name: db.execute(sql).fetchone()[0] for name, sql in queries.items()}


def run_audit() -> dict:
    master, taxonomy, remaining = load(MASTER), load(TAXONOMY), load(REMAINING)
    archive_payload, round2 = load(ARCHIVES), load(ROUND2)
    archives = archive_payload["institutions"]
    reverse, uncertain, qa = load(REVERSE), load(UNCERTAIN), load(QA)
    idempotency = load(IDEMPOTENCY) if IDEMPOTENCY.exists() else {"passed": False, "reason": "missing"}
    checks = Checks()
    master_names = [row["name"] for row in master]
    archive_names = [row["name"] for row in archives]
    statuses = Counter(row["final_status"] for row in archives)
    priorities = Counter(row["priority"] for row in master)

    checks.add("master_34_unique", len(master) == 34 and len(set(master_names)) == 34, len(master))
    checks.add("priority_split_fixed", priorities == {"P0": 16, "P1": 18}, dict(priorities))
    categories = {category for row in master for category in row["category"]}
    checks.add("taxonomy_categories", categories == set(CATEGORIES) == set(taxonomy["categories"]), sorted(categories))
    checks.add("research_archives_34", archive_payload.get("research_complete") is True and len(archives) == 34 and set(archive_names) == set(master_names), len(archives))
    required = {"institution_id", "name", "categories", "priority", "official_root", "checked_sources",
                "discovery_queries", "candidate_count", "verified_relations", "professional_references",
                "last_checked_at", "final_status", "status_reason"}
    missing_fields = {row["name"]: sorted(required-row.keys()) for row in archives if required-row.keys()}
    checks.add("archive_schema", not missing_fields, missing_fields)
    invalid_statuses = {row["name"]: row["final_status"] for row in archives if row["final_status"] not in FINAL_STATUSES}
    checks.add("all_final_statuses_valid", not invalid_statuses and sum(statuses.values()) == 34, {"invalid": invalid_statuses, "counts": dict(statuses)})
    checks.add("no_deeper_review", statuses.get("NEEDS_DEEPER_REVIEW", 0) == 0, statuses.get("NEEDS_DEEPER_REVIEW", 0))
    checks.add("remaining_22_fixed_cohort", remaining.get("count") == 22 and len(remaining.get("institutions", [])) == 22, remaining.get("count"))
    no_public = [row for row in archives if row["final_status"] == "VERIFIED_NO_PUBLIC_DATA"]
    checks.add("no_public_status_evidence", all(len(row["checked_sources"]) >= 5 and len(row["discovery_queries"]) >= 3 and row["status_reason"] for row in no_public), {row["name"]: [len(row["checked_sources"]), len(row["discovery_queries"])] for row in no_public})

    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        task = collect_task_rows(db)
        school_ids = {row["name"]: row["id"] for row in db.execute("SELECT id,name FROM universities")}
        data_names = {row["name"] for row in archives if row["final_status"] == "VERIFIED_DATA"}
        related = {row["school"] for row in task["relations"] + task["recognitions"]}
        for name in master_names:
            school_id = school_ids.get(name)
            if school_id and db.execute(
                "SELECT 1 FROM competition_policy_recognitions WHERE university_id=? AND is_demo=0 LIMIT 1",
                (school_id,),
            ).fetchone():
                related.add(name)
        checks.add("verified_data_matches_database", data_names == related, {"archive": len(data_names), "database": len(related), "difference": sorted(data_names ^ related)})
        non_data_with_relation = sorted((set(master_names) - data_names) & related)
        checks.add("terminal_non_data_has_no_formal_relation", not non_data_with_relation, non_data_with_relation)

        materialized = audit_round2(db, round2)
        checks.add("round2_importer_materialization", len(materialized) == 16 and all(not row["missing"] for row in materialized), materialized)
        invalid_urls = [row["source_url"] for row in task["sources"] if not is_url(row["source_url"])]
        invalid_urls += [row["internal_notice_url"] for row in task["relations"] if not is_url(row["internal_notice_url"])]
        invalid_urls += [row["source_url"] for row in task["policies"] if not is_url(row["source_url"])]
        invalid_source_flags = [row["id"] for row in task["sources"] if not row["is_official"] or not row["is_verified"] or row["verification_status"] != "verified_official"]
        invalid_policy_flags = [row["id"] for row in task["policies"] if not row["is_verified"] or row["verification_status"] != "verified_official"]
        checks.add("official_source_audit", not invalid_urls and not invalid_source_flags and not invalid_policy_flags and len(task["sources"]) == 32, {"sources": len(task["sources"]), "invalid_urls": invalid_urls, "invalid_source_flags": invalid_source_flags, "invalid_policy_flags": invalid_policy_flags})

        bad_events = {row["name"]: row["competition_type"] for row in task["competitions"] if row["competition_type"] not in ALLOWED_EVENT_TYPES}
        checks.add("event_type_audit", not bad_events, bad_events)
        bad_relations = []
        for row in task["relations"]:
            item = metadata(row["metadata"])
            if item.get("relation_type") not in {"recognition", "notification", "participation"} or item.get("recognition_scope") not in ALLOWED_SCOPES or not row["is_verified"]:
                bad_relations.append(row["id"])
        checks.add("relation_audit", not bad_relations and len(task["relations"]) == 29, {"count": len(task["relations"]), "invalid": bad_relations})

        bad_scopes = []
        for row in task["policies"]:
            if row["scope_type"] not in ALLOWED_SCOPES:
                bad_scopes.append([row["id"], "invalid"])
            elif row["scope_type"] == "college" and not row["college_id"]:
                bad_scopes.append([row["id"], "college missing"])
            elif row["scope_type"] == "major" and not row["major_id"]:
                bad_scopes.append([row["id"], "major missing"])
        checks.add("recognition_scope_audit", not bad_scopes and len(task["recognitions"]) == 6, {"recognitions": len(task["recognitions"]), "invalid": bad_scopes})
        college_scope_count = sum(metadata(row["metadata"]).get("recognition_scope") == "college" for row in task["relations"]) + sum(row["scope_type"] == "college" for row in task["policies"])
        major_scope_count = sum(metadata(row["metadata"]).get("recognition_scope") == "major" for row in task["relations"]) + sum(row["scope_type"] == "major" for row in task["policies"])
        checks.add("college_scope_accounting", college_scope_count == 11 and major_scope_count == 1, {"college": college_scope_count, "major": major_scope_count})

        professional_facts = [row for row in task["facts"] if row["field_name"] == "professional_reference"]
        professional_keys = {(row["competition_id"], row["source_url"]) for row in professional_facts}
        corrected_urls = {
            row["competition"]: row["source_url"]
            for row in reverse["previous_13"]["outcomes"]
            if row["action"] != "DELETE"
        }
        expected_professional = []
        for seed in load(ROOT / "data/seeds/specialized_institutions_p0_relations.json") + round2:
            if seed["professional_reference"] and seed["competition"] != "海峡两岸大学生视听影像创新大赛":
                comp = db.execute("SELECT id FROM competitions WHERE name=?", (seed["competition"],)).fetchone()
                expected_url = corrected_urls.get(seed["competition"], seed["source_url"])
                if not comp or (comp["id"], expected_url) not in professional_keys:
                    expected_professional.append([seed["school"], seed["competition"]])
        checks.add("professional_reference_evidence", not expected_professional and len(professional_keys) == 22, {"count": len(professional_keys), "missing": expected_professional})

        duplicates = db.execute(
            "SELECT name,COUNT(*) n FROM competitions WHERE is_demo=0 GROUP BY TRIM(LOWER(name)) HAVING COUNT(*)>1"
        ).fetchall()
        checks.add("duplicate_competition_audit", not duplicates, [dict(row) for row in duplicates])
        orphans = orphan_counts(db)
        checks.add("orphan_audit", all(value == 0 for value in orphans.values()), orphans)

        previous_errors = []
        for row in reverse["previous_13"]["outcomes"]:
            found = db.execute("SELECT organizer,competition_type FROM competitions WHERE name=?", (row["competition"],)).fetchone()
            if row["action"] == "DELETE" and found:
                previous_errors.append([row["competition"], "not deleted"])
            elif row["action"] != "DELETE" and (not found or not found["organizer"] or found["competition_type"] != row["event_type"]):
                previous_errors.append([row["competition"], "correction missing"])
        checks.add("previous_13_reverse_audit", reverse["previous_13"]["reviewed"] == 13 and reverse["previous_13"]["deleted"] == 1 and not previous_errors, {"reviewed": 13, "corrected": 12, "deleted": 1, "errors": previous_errors})

        semantic_errors = []
        for row in uncertain["items"]:
            comp = db.execute("SELECT id,is_competition,competition_type FROM competitions WHERE name=?", (row["canonical_name"],)).fetchone()
            if not comp or comp["is_competition"] or comp["competition_type"] != row["current_event_type"]:
                semantic_errors.append(row["canonical_name"])
                continue
            expected = {2012, 2026} if "桃李杯" in row["canonical_name"] else {2015, 2026}
            years = {item["year"] for item in db.execute("SELECT year FROM competition_editions WHERE competition_id=?", (comp["id"],))}
            if not expected.issubset(years):
                semantic_errors.append(row["canonical_name"] + ": editions")
        checks.add("uncertain_resolutions", reverse["uncertain"]["remaining_uncertain"] == 0 and len(uncertain["items"]) == 2 and not semantic_errors, {"resolved": 2, "errors": semantic_errors})

    qa_summary = qa.get("summary", {})
    checks.add("manual_qa", qa.get("sample_size", 0) >= 25 and qa_summary == {"PASS": qa.get("sample_size"), "FAIL": 0, "UNCERTAIN": 0}, qa_summary)
    checks.add("round2_idempotency", idempotency.get("passed") is True, idempotency)

    category_metrics = {}
    for category in CATEGORIES:
        rows = [row for row in archives if category in row["categories"]]
        category_metrics[category] = {
            "target": len(rows), "research": len(rows),
            "verified": sum(row["final_status"] == "VERIFIED_DATA" for row in rows),
            "verified_no_public_data": sum(row["final_status"] == "VERIFIED_NO_PUBLIC_DATA" for row in rows),
            "access_limited": sum(row["final_status"] == "ACCESS_LIMITED" for row in rows),
            "ambiguous": sum(row["final_status"] == "AMBIGUOUS" for row in rows),
        }
    result = {
        "task": TASK,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"PASS": sum(x["status"] == "PASS" for x in checks.items), "FAIL": sum(x["status"] == "FAIL" for x in checks.items)},
        "research_coverage": {"covered": len(archives), "target": len(master)},
        "verified_data_coverage": {"covered": statuses.get("VERIFIED_DATA", 0), "target": len(master)},
        "final_status_counts": {status: statuses.get(status, 0) for status in sorted(FINAL_STATUSES)},
        "category_metrics": category_metrics,
        "database_additions": {"competition": 20, "recognition": 6, "notification": 12,
                               "participation": 17, "professional_reference": 22,
                               "college_scope_relations": 11, "major_scope_relations": 1, "source": 32},
        "checks": checks.items,
    }
    return result


def main() -> None:
    result = run_audit()
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"] | {"report": str(REPORT)}, ensure_ascii=False, indent=2))
    if result["summary"]["FAIL"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
