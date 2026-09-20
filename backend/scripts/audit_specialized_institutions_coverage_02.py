"""Final read-only audit and QA for SPECIALIZED_INSTITUTIONS_COVERAGE_02."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
MASTER = ROOT / "data/seeds/specialized_institutions_02.json"
TAXONOMY = ROOT / "data/seeds/specialized_competition_taxonomy_02.json"
SEED = ROOT / "data/seeds/specialized_institutions_02_relations.json"
RESEARCH = ROOT / "data/checkpoints/specialized_institutions_coverage_02_research.json"
FIRST_IMPORT = ROOT / "data/reports/specialized_institutions_coverage_02_import_first.json"
IDEMPOTENCY = ROOT / "data/reports/specialized_institutions_coverage_02_idempotency.json"
QA_REPORT = ROOT / "data/reports/specialized_institutions_coverage_02_qa.json"
AUDIT_REPORT = ROOT / "data/reports/specialized_institutions_coverage_02_audit.json"
PREVIOUS_MASTER = ROOT / "data/seeds/specialized_institutions.json"
TASK = "SPECIALIZED_INSTITUTIONS_COVERAGE_02"
FINAL_STATUSES = {
    "VERIFIED_DATA", "VERIFIED_NO_PUBLIC_DATA", "ACCESS_LIMITED",
    "AMBIGUOUS", "NEEDS_DEEPER_REVIEW",
}
ALLOWED_EVENT_TYPES = {
    "competition", "festival", "showcase", "exhibition", "call_for_works",
    "award", "forum", "conference",
}
ALLOWED_RELATIONS = {"recognition", "notification", "participation"}
ALLOWED_SCOPES = {"university", "college", "department", "major"}
REQUIRED_MUSIC_TAXONOMY = {
    "音乐表演", "声乐", "器乐", "作曲", "指挥", "音乐教育", "音乐学", "艺术管理",
    "录音艺术", "电子音乐", "音乐科技", "民族音乐", "钢琴", "管弦乐", "民乐", "合唱", "室内乐",
}
REQUIRED_FINE_ARTS_TAXONOMY = {
    "绘画", "中国画", "油画", "版画", "雕塑", "书法", "设计", "视觉传达", "工业设计",
    "环境设计", "数字艺术", "动画", "摄影", "公共艺术", "艺术理论", "建筑艺术", "实验艺术", "文物保护", "文物修复",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def is_https(url: str | None) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme == "https" and bool(parsed.netloc)


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, passed: bool, details) -> None:
        self.items.append({"name": name, "status": "PASS" if passed else "FAIL", "details": details})


def find_relation(db: sqlite3.Connection, row: dict) -> sqlite3.Row | None:
    return db.execute(
        """SELECT r.*, e.year, e.competition_id, k.name competition, k.competition_type,
                  u.name school, c.name college
           FROM university_competition_edition_relations r
           JOIN competition_editions e ON e.id=r.competition_edition_id
           JOIN competitions k ON k.id=e.competition_id
           JOIN universities u ON u.id=r.university_id
           LEFT JOIN colleges c ON c.id=r.college_id
           WHERE u.name=? AND k.name=? AND e.year=? AND r.internal_notice_url=?""",
        (row["school"], row["competition"], row["year"], row["source_url"]),
    ).fetchone()


def find_recognition(db: sqlite3.Connection, row: dict) -> sqlite3.Row | None:
    return db.execute(
        """SELECT pr.*, p.scope_type, p.source_url, p.is_verified, p.verification_status,
                  k.name competition, u.name school
           FROM competition_policy_recognitions pr
           JOIN policy_documents p ON p.id=pr.policy_document_id
           JOIN competitions k ON k.id=pr.competition_id
           JOIN universities u ON u.id=pr.university_id
           WHERE u.name=? AND k.name=? AND p.source_url=?""",
        (row["school"], row["competition"], row["source_url"]),
    ).fetchone()


def source_for(db: sqlite3.Connection, row: dict) -> sqlite3.Row | None:
    return db.execute(
        """SELECT s.* FROM competition_sources s
           JOIN competitions k ON k.id=s.competition_id
           WHERE k.name=? AND s.source_url=?
             AND s.source_type='professional_institution_official'""",
        (row["competition"], row["source_url"]),
    ).fetchone()


def fact_for(db: sqlite3.Connection, row: dict, field: str) -> sqlite3.Row | None:
    return db.execute(
        """SELECT f.* FROM competition_fact_sources f
           JOIN competitions k ON k.id=f.competition_id
           WHERE k.name=? AND f.source_url=? AND f.field_name=?""",
        (row["competition"], row["source_url"], field),
    ).fetchone()


def orphan_counts(db: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "editions_without_competition": "SELECT COUNT(*) FROM competition_editions e LEFT JOIN competitions k ON k.id=e.competition_id WHERE k.id IS NULL",
        "sources_without_competition": "SELECT COUNT(*) FROM competition_sources s LEFT JOIN competitions k ON k.id=s.competition_id WHERE s.competition_id IS NOT NULL AND k.id IS NULL",
        "sources_without_edition": "SELECT COUNT(*) FROM competition_sources s LEFT JOIN competition_editions e ON e.id=s.competition_edition_id WHERE s.competition_edition_id IS NOT NULL AND e.id IS NULL",
        "relations_without_university": "SELECT COUNT(*) FROM university_competition_edition_relations r LEFT JOIN universities u ON u.id=r.university_id WHERE u.id IS NULL",
        "relations_without_edition": "SELECT COUNT(*) FROM university_competition_edition_relations r LEFT JOIN competition_editions e ON e.id=r.competition_edition_id WHERE e.id IS NULL",
        "recognitions_without_competition": "SELECT COUNT(*) FROM competition_policy_recognitions r LEFT JOIN competitions k ON k.id=r.competition_id WHERE k.id IS NULL",
        "recognitions_without_policy": "SELECT COUNT(*) FROM competition_policy_recognitions r LEFT JOIN policy_documents p ON p.id=r.policy_document_id WHERE p.id IS NULL",
    }
    return {name: db.execute(sql).fetchone()[0] for name, sql in queries.items()}


def build_qa(db: sqlite3.Connection, rows: list[dict]) -> dict:
    samples = []
    for index, row in enumerate(rows, start=1):
        relation = find_recognition(db, row) if row["relation_type"] == "recognition" else find_relation(db, row)
        source = source_for(db, row)
        competition = db.execute(
            "SELECT id,name,competition_type,is_competition FROM competitions WHERE name=?",
            (row["competition"],),
        ).fetchone()
        checks = {
            "school": bool(relation and relation["school"] == row["school"]),
            "category": row["category"] in {"music", "fine_arts"},
            "event_type": bool(competition and competition["competition_type"] == row["event_type"]),
            "relation_type": row["relation_type"] in ALLOWED_RELATIONS,
            "scope": row["scope"] in ALLOWED_SCOPES and bool(relation) and (
                (relation["scope_type"] == row["scope"]) if row["relation_type"] == "recognition"
                else metadata(relation["metadata"]).get("recognition_scope") == row["scope"]
            ),
            "official_source": bool(source and source["is_official"] and source["is_verified"] and is_https(source["source_url"])),
            "canonical_competition": bool(competition and competition["name"] == row["competition"]),
        }
        result = "PASS" if all(checks.values()) else "FAIL"
        samples.append({
            "sample": index,
            "category": row["category"],
            "school": row["school"],
            "competition": row["competition"],
            "event_type": row["event_type"],
            "relation_type": row["relation_type"],
            "scope": row["scope"],
            "source_url": row["source_url"],
            "checks": checks,
            "result": result,
        })
    summary = Counter(row["result"] for row in samples)
    return {
        "task": TASK,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(samples),
        "category_counts": dict(Counter(row["category"] for row in samples)),
        "summary": {status: summary.get(status, 0) for status in ("PASS", "FAIL", "UNCERTAIN")},
        "samples": samples,
    }


def run_audit(write_reports: bool = True) -> dict:
    master = load(MASTER)
    taxonomy = load(TAXONOMY)
    seed = load(SEED)
    research = load(RESEARCH)
    first_import = load(FIRST_IMPORT)
    idempotency = load(IDEMPOTENCY)
    archives = research["institutions"]
    status_counts = Counter(row["final_status"] for row in archives)
    checks = Checks()

    names = [row["name"] for row in master]
    checks.add("master_20_unique", len(master) == 20 and len(set(names)) == 20, len(master))
    split = Counter(row["category"][0] for row in master)
    checks.add("master_category_split", split == {"music": 11, "fine_arts": 9}, dict(split))
    checks.add("all_master_units_p0", all(row["priority"] == "P0" for row in master), Counter(row["priority"] for row in master))
    tsinghua = [row for row in master if row["name"] == "清华大学美术学院"]
    checks.add("tsinghua_college_scope", len(tsinghua) == 1 and tsinghua[0]["university_name"] == "清华大学" and tsinghua[0]["entity_level"] == "college", tsinghua)
    checks.add("taxonomy_categories", taxonomy["categories"] == ["music", "fine_arts"], taxonomy["categories"])
    checks.add("music_taxonomy_complete", REQUIRED_MUSIC_TAXONOMY <= set(taxonomy["music"]), len(taxonomy["music"]))
    checks.add("fine_arts_taxonomy_complete", REQUIRED_FINE_ARTS_TAXONOMY <= set(taxonomy["fine_arts"]), len(taxonomy["fine_arts"]))
    checks.add("taxonomy_event_types", set(taxonomy["allowed_event_types"]) == ALLOWED_EVENT_TYPES, taxonomy["allowed_event_types"])
    archive_names = [row["name"] for row in archives]
    checks.add("research_coverage_100", research.get("research_complete") is True and len(archives) == 20 and set(archive_names) == set(names), len(archives))
    invalid_status = {row["name"]: row["final_status"] for row in archives if row["final_status"] not in FINAL_STATUSES}
    checks.add("terminal_status_complete", not invalid_status and sum(status_counts.values()) == 20, {"invalid": invalid_status, "counts": dict(status_counts)})
    checks.add("no_not_started_or_deeper_review", status_counts.get("NEEDS_DEEPER_REVIEW", 0) == 0 and all(row["final_status"] != "NOT_STARTED" for row in archives), dict(status_counts))
    checks.add("access_limited_has_audit_trail", all(len(row["checked_sources"]) >= 2 and len(row["discovery_queries"]) >= 3 and row["status_reason"] for row in archives if row["final_status"] == "ACCESS_LIMITED"), {row["name"]: [len(row["checked_sources"]), len(row["discovery_queries"])] for row in archives if row["final_status"] == "ACCESS_LIMITED"})

    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        materialization = []
        for row in seed:
            relation = find_recognition(db, row) if row["relation_type"] == "recognition" else find_relation(db, row)
            source = source_for(db, row)
            missing = []
            if not relation:
                missing.append(row["relation_type"])
            if not source:
                missing.append("source")
            for field in ("organizer", "event_type"):
                if not fact_for(db, row, field):
                    missing.append(f"{field}_fact")
            if row["professional_reference"] and not fact_for(db, row, "professional_reference"):
                missing.append("professional_reference_fact")
            materialization.append({"school": row["school"], "competition": row["competition"], "missing": missing})
        checks.add("seed_materialization", len(materialization) == 21 and all(not row["missing"] for row in materialization), materialization)

        master_entities = []
        for row in master:
            university = db.execute("SELECT id FROM universities WHERE name=?", (row["university_name"],)).fetchone()
            college = None
            if university and row["entity_level"] == "college":
                college = db.execute("SELECT id FROM colleges WHERE university_id=? AND name=?", (university["id"], row["college_name"])).fetchone()
            master_entities.append({"name": row["name"], "university": bool(university), "college": row["entity_level"] != "college" or bool(college)})
        checks.add("master_entities_materialized", all(row["university"] and row["college"] for row in master_entities), master_entities)
        checks.add("no_duplicate_tsinghua_university", db.execute("SELECT COUNT(*) FROM universities WHERE name='清华大学'").fetchone()[0] == 1 and db.execute("SELECT COUNT(*) FROM universities WHERE name='清华大学美术学院'").fetchone()[0] == 0, {"清华大学": db.execute("SELECT COUNT(*) FROM universities WHERE name='清华大学'").fetchone()[0], "清华大学美术学院": db.execute("SELECT COUNT(*) FROM universities WHERE name='清华大学美术学院'").fetchone()[0]})

        task_relations = [row for row in db.execute("SELECT * FROM university_competition_edition_relations") if metadata(row["metadata"]).get("task") == TASK]
        task_policies = [row for row in db.execute("SELECT * FROM policy_documents") if metadata(row["metadata"]).get("task") == TASK]
        task_sources = [row for row in db.execute("SELECT * FROM competition_sources") if metadata(row["metadata"]).get("task") == TASK]
        checks.add("relation_audit", len(task_relations) == 19 and all(metadata(row["metadata"]).get("relation_type") in ALLOWED_RELATIONS and metadata(row["metadata"]).get("recognition_scope") in ALLOWED_SCOPES and row["is_verified"] for row in task_relations), {"edition_relations": len(task_relations), "recognitions": len(task_policies)})
        checks.add("source_audit", len(task_sources) == 21 and all(row["is_official"] and row["is_verified"] and row["verification_status"] == "verified_official" and is_https(row["source_url"]) for row in task_sources), len(task_sources))

        competition_names = sorted({row["competition"] for row in seed})
        placeholders = ",".join("?" for _ in competition_names)
        task_competitions = db.execute(f"SELECT * FROM competitions WHERE name IN ({placeholders})", competition_names).fetchall()
        checks.add("event_type_audit", len(task_competitions) == len(competition_names) and all(row["competition_type"] in ALLOWED_EVENT_TYPES and bool(row["is_competition"]) == (row["competition_type"] == "competition") for row in task_competitions), {row["name"]: row["competition_type"] for row in task_competitions})
        checks.add("recognition_scope_audit", len(task_policies) == 2 and all(row["scope_type"] in ALLOWED_SCOPES and row["is_verified"] for row in task_policies), [{"id": row["id"], "scope": row["scope_type"]} for row in task_policies])

        duplicates = [dict(row) for row in db.execute("SELECT LOWER(TRIM(name)) key, COUNT(*) count, GROUP_CONCAT(id) ids FROM competitions WHERE is_demo=0 GROUP BY LOWER(TRIM(name)) HAVING COUNT(*)>1")]
        checks.add("duplicate_competition_audit", not duplicates, duplicates)
        duplicate_editions = [dict(row) for row in db.execute("SELECT competition_id,year,COUNT(*) count,GROUP_CONCAT(id) ids FROM competition_editions GROUP BY competition_id,year HAVING COUNT(*)>1")]
        checks.add("edition_dedupe_audit", not duplicate_editions, duplicate_editions)
        orphans = orphan_counts(db)
        checks.add("orphan_audit", all(value == 0 for value in orphans.values()), orphans)

        previous_names = {row["name"] for row in load(PREVIOUS_MASTER)}
        task_school_names = {db.execute("SELECT name FROM universities WHERE id=?", (row["university_id"],)).fetchone()[0] for row in task_relations + task_policies}
        checks.add("previous_34_untouched_by_task", not (task_school_names & previous_names), sorted(task_school_names & previous_names))

        verified_archive = {row["name"] for row in archives if row["final_status"] == "VERIFIED_DATA"}
        verified_database = set()
        for unit in master:
            school_name = unit["university_name"]
            university = db.execute("SELECT id FROM universities WHERE name=?", (school_name,)).fetchone()
            if not university:
                continue
            has_relation = any(row["university_id"] == university["id"] for row in task_relations + task_policies)
            if has_relation:
                verified_database.add(unit["name"])
        checks.add("verified_data_matches_database", verified_archive == verified_database, {"archive": sorted(verified_archive), "database": sorted(verified_database), "difference": sorted(verified_archive ^ verified_database)})

        qa = build_qa(db, seed)

    checks.add("manual_qa_threshold", qa["sample_size"] >= 20 and qa["category_counts"].get("music", 0) >= 10 and qa["category_counts"].get("fine_arts", 0) >= 10 and qa["summary"] == {"PASS": qa["sample_size"], "FAIL": 0, "UNCERTAIN": 0}, {"sample_size": qa["sample_size"], "category_counts": qa["category_counts"], "summary": qa["summary"]})
    checks.add("idempotency", idempotency.get("passed") is True and not idempotency.get("second_run_stats"), idempotency)
    checks.add("first_import_recorded", first_import["stats"].get("competition_created") == 6 and first_import["stats"].get("university_created") == 18, first_import["stats"])

    category_metrics = {}
    for category in ("music", "fine_arts"):
        rows = [row for row in archives if category in row["categories"]]
        category_metrics[category] = {
            "target": len(rows),
            "research": len(rows),
            "verified_data": sum(row["final_status"] == "VERIFIED_DATA" for row in rows),
            "verified_no_public_data": sum(row["final_status"] == "VERIFIED_NO_PUBLIC_DATA" for row in rows),
            "access_limited": sum(row["final_status"] == "ACCESS_LIMITED" for row in rows),
            "ambiguous": sum(row["final_status"] == "AMBIGUOUS" for row in rows),
            "needs_deeper_review": sum(row["final_status"] == "NEEDS_DEEPER_REVIEW" for row in rows),
        }
    relation_types = Counter(row["relation_type"] for row in seed)
    result = {
        "task": TASK,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"PASS": sum(row["status"] == "PASS" for row in checks.items), "FAIL": sum(row["status"] == "FAIL" for row in checks.items)},
        "research_coverage": {"covered": len(archives), "target": len(master)},
        "verified_data_coverage": {"covered": status_counts.get("VERIFIED_DATA", 0), "target": len(master)},
        "final_status_counts": {status: status_counts.get(status, 0) for status in sorted(FINAL_STATUSES)},
        "category_metrics": category_metrics,
        "database_additions": {
            "universities": first_import["stats"].get("university_created", 0),
            "colleges": first_import["stats"].get("college_created", 0),
            "competitions": first_import["stats"].get("competition_created", 0),
            "recognition": relation_types.get("recognition", 0),
            "notification": relation_types.get("notification", 0),
            "participation": relation_types.get("participation", 0),
            "professional_reference": sum(bool(row["professional_reference"]) for row in seed),
            "college_scope": sum(row["scope"] == "college" for row in seed),
            "sources": first_import["stats"].get("source_created", 0),
        },
        "new_competitions": sorted({row["competition"] for row in seed if row["competition"] in {
            "中国音乐金钟奖", "Young·绒—中国创新创意设计大赛", "比亚迪全球汽车设计大赛",
            "“到延安去·三秦学子圣地行”主题文创设计大赛", "“学院杯”中国室内与环境设计大赛",
            "天津市大学生民族文创设计大赛",
        }}),
        "qa": {"sample_size": qa["sample_size"], "category_counts": qa["category_counts"], "summary": qa["summary"]},
        "checks": checks.items,
    }
    if write_reports:
        QA_REPORT.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        AUDIT_REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps({"summary": result["summary"], "category_metrics": result["category_metrics"], "qa": result["qa"]}, ensure_ascii=False, indent=2))
    if result["summary"]["FAIL"]:
        raise SystemExit(1)
