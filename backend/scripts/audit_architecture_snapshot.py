"""V0.9 architecture audit snapshot.

Read-only: dumps table inventory, row counts, and key competition/school
relation samples from the configured DATABASE_URL database so the data
architecture audit has a reproducible evidence base.
"""

import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect, text

from app.database.session import SessionLocal
from app.models import Base as DeclBase


def table_columns(bind, table: str) -> set[str]:
    inspector = inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def model_table_columns(table_name: str) -> set[str] | None:
    table = next((t for t in DeclBase.metadata.sorted_tables if t.name == table_name), None)
    if table is None:
        return None
    return {column.name for column in table.columns}


def main() -> None:
    with SessionLocal() as db:
        inspector = inspect(db.bind)
        tables = sorted(inspector.get_table_names())
        print(f"== TABLES ({len(tables)}) ==")
        print("alembic_version:", [r[0] for r in db.execute(text("SELECT version_num FROM alembic_version"))])
        for table in tables:
            count = db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            print(f"{count:>8}  {table}")

        print("\n== MODEL vs LIVE SCHEMA DRIFT (live-table -> missing model cols) ==")
        live_names = {table.name for table in DeclBase.metadata.sorted_tables}
        for table in sorted(live_names):
            if table not in tables:
                print(f"MODEL-ONLY (not in live DB): {table}")
                continue
            live_cols = table_columns(db.bind, table)
            model_cols = model_table_columns(table) or set()
            missing = sorted(model_cols - live_cols)
            extra = sorted(live_cols - model_cols)
            if missing:
                print(f"{table}: MISSING in live DB -> {missing}")
            if extra:
                print(f"{table}: EXTRA in live DB (no model attr) -> {extra}")
        print()

        print("\n== COMPETITION NAME COUNTS ==")
        rows = db.execute(
            text(
                "SELECT name, COUNT(*) AS cnt FROM competitions "
                "GROUP BY name HAVING cnt > 1 ORDER BY cnt DESC LIMIT 30"
            )
        ).all()
        for row in rows:
            print(f"{row.cnt:>4}  {row.name}")

        print("\n== ORGANIZER FIELD DISTRIBUTION ==")
        rows = db.execute(
            text(
                "SELECT COALESCE(NULLIF(TRIM(organizer), ''), '(empty)'), COUNT(*) AS cnt "
                "FROM competitions GROUP BY organizer ORDER BY cnt DESC LIMIT 25"
            )
        ).all()
        for row in rows:
            print(f"{row.cnt:>5}  {row[0]}")

        print("\n== competition_level / category / entity_type / competition_type ==")
        for col in ("competition_level", "category", "entity_type", "competition_type", "verification_status", "status"):
            print(f"-- {col}")
            rows = db.execute(
                text(
                    f"SELECT COALESCE(NULLIF(TRIM({col}), ''), '(empty)'), COUNT(*) AS cnt "
                    f"FROM competitions GROUP BY {col} ORDER BY cnt DESC LIMIT 15"
                )
            ).all()
            for row in rows:
                print(f"   {row.cnt:>6}  {row[0]}")

        print("\n== COMPETITION EDITION COVERAGE ==")
        rows = db.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN year IS NULL THEN 1 ELSE 0 END) AS no_year, "
                "MIN(year), MAX(year), COUNT(DISTINCT competition_id) AS competitions_with_editions "
                "FROM competition_editions"
            )
        ).one()
        print(
            f"editions={rows.total} no_year={rows.no_year} year_range={rows[2]}..{rows[3]} "
            f"competitions_with_editions={rows.competitions_with_editions}"
        )

        print("\n== EDITION DEADLINE SEMANTICS SANITY ==")
        rows = db.execute(
            text(
                "SELECT "
                "COUNT(*) AS total, "
                "SUM(CASE WHEN registration_deadline IS NOT NULL THEN 1 ELSE 0 END) AS has_plain, "
                "SUM(CASE WHEN official_registration_deadline IS NOT NULL THEN 1 ELSE 0 END) AS has_official, "
                "SUM(CASE WHEN university_registration_deadline IS NOT NULL THEN 1 ELSE 0 END) AS has_university "
                "FROM competition_editions"
            )
        ).one()
        print(dict(rows._mapping))

        print("\n== EDITIONS WITH BOTH official AND university DEADLINES DIFFERING ==")
        rows = db.execute(
            text(
                "SELECT e.id, e.year, e.edition_name, e.official_registration_deadline, "
                "e.university_registration_deadline, c.name "
                "FROM competition_editions e JOIN competitions c ON c.id = e.competition_id "
                "WHERE e.official_registration_deadline IS NOT NULL "
                "AND e.university_registration_deadline IS NOT NULL "
                "AND e.official_registration_deadline <> e.university_registration_deadline "
                "LIMIT 30"
            )
        ).all()
        for row in rows:
            print(
                f"e{row.id} y{row.year} {row[5][:30]!r} official={row[3]} university={row[4]}"
            )

        print("\n== UNIVERSITY x EDITION RELATIONS ==")
        rows = db.execute(
            text(
                "SELECT r.university_id, u.name, r.competition_edition_id, e.year, c.name, "
                "r.notice_type, r.internal_notice_url "
                "FROM university_competition_edition_relations r "
                "JOIN universities u ON u.id = r.university_id "
                "JOIN competition_editions e ON e.id = r.competition_edition_id "
                "JOIN competitions c ON c.id = e.competition_id "
                "ORDER BY r.id LIMIT 15"
            )
        ).all()
        for row in rows:
            print(f"u{row[0]} {row[1]} | e{row[2]} y{row[3]} {row[4][:28]!r} [{row[5]}] {row[6][:80]}")

        print("\n== UNIVERSITY x COMPETITION POLICY RECOGNITIONS (school level) ==")
        p_cols = table_columns(db.bind, "university_competition_policies")
        level_col = "recognized_level" if "recognized_level" in p_cols else "recognition_level"
        rows = db.execute(
            text(
                f"SELECT u.name, c.name, p.year, p.{level_col}, p.usage_type, p.recognition_status "
                "FROM university_competition_policies p "
                "JOIN universities u ON u.id = p.university_id "
                "JOIN competitions c ON c.id = p.competition_id "
                "ORDER BY p.id LIMIT 20"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== COMPETITION POLICY RECOGNITIONS (document-level) ==")
        rec_cols = table_columns(db.bind, "competition_policy_recognitions")
        doc_level_col = "recognition_level" if "recognition_level" in rec_cols else "recognized_level"
        rows = db.execute(
            text(
                f"SELECT u.name, c.name, p.year, p.{doc_level_col}, p.usage_type, p.recognition_status, "
                "p.evidence_text "
                "FROM competition_policy_recognitions p "
                "JOIN universities u ON u.id = p.university_id "
                "JOIN competitions c ON c.id = p.competition_id "
                "ORDER BY p.id LIMIT 20"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== COMPETITION LEADS / DISCOVERY POOL ==")
        rows = db.execute(
            text(
                "SELECT classification, verification_status, needs_review, COUNT(*) AS cnt "
                "FROM competition_leads GROUP BY classification, verification_status, needs_review "
                "ORDER BY cnt DESC"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== LEAD MATCHING (matched vs unmatched) ==")
        rows = db.execute(
            text(
                "SELECT "
                "COUNT(*) AS total, "
                "SUM(CASE WHEN matched_competition_id IS NOT NULL THEN 1 ELSE 0 END) AS matched, "
                "SUM(CASE WHEN matched_competition_id IS NULL THEN 1 ELSE 0 END) AS unmatched "
                "FROM competition_leads"
            )
        ).one()
        print(dict(rows._mapping))

        print("\n== SOURCES ==")
        rows = db.execute(
            text(
                "SELECT source_type, reliability_tier, is_official, is_verified, COUNT(*) AS cnt "
                "FROM competition_sources GROUP BY source_type, reliability_tier, is_official, is_verified "
                "ORDER BY cnt DESC LIMIT 30"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== DUPLICATE COMPETITION NAMES NORMALIZED ==")
        rows = db.execute(
            text(
                "SELECT REPLACE(REPLACE(REPLACE(name, '（', '('), '）', ')'), ' ', ''), "
                "COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids "
                "FROM competitions GROUP BY 1 HAVING cnt > 1 ORDER BY cnt DESC LIMIT 40"
            )
        ).all()
        for row in rows:
            print(f"{row.cnt:>4}  {row[0][:60]!r}  ids={row.ids}")

        print("\n== HISTORY/TIMELINE FIELDS ==")
        rows = db.execute(
            text(
                "SELECT "
                "COUNT(*) AS total, "
                "SUM(CASE WHEN history_timeline IS NOT NULL THEN 1 ELSE 0 END) AS has_timeline, "
                "SUM(CASE WHEN development_history IS NOT NULL THEN 1 ELSE 0 END) AS has_dev_history, "
                "SUM(CASE WHEN founded_year IS NOT NULL THEN 1 ELSE 0 END) AS has_founded_year, "
                "SUM(CASE WHEN first_held_year IS NOT NULL THEN 1 ELSE 0 END) AS has_first_held "
                "FROM competitions"
            )
        ).one()
        print(dict(rows._mapping))

        print("\n== PERMANENT-VS-EDITION FIELD LEAK CHECK: organizer set + year in name ==")
        rows = db.execute(
            text(
                "SELECT id, name, organizer, founded_year FROM competitions "
                "WHERE name LIKE '%2026%' OR name LIKE '%2025%' OR name LIKE '%2027%' "
                "ORDER BY id LIMIT 40"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== EVIDENCE: competitions whose sources are only school policy docs ==")
        rows = db.execute(
            text(
                "SELECT c.id, c.name, c.organizer, c.competition_level, c.category, "
                "substr(c.description, 1, 80) AS desc_head "
                "FROM competitions c "
                "JOIN competition_sources s ON s.competition_id = c.id "
                "WHERE s.source_type = 'university_policy' "
                "ORDER BY c.id LIMIT 60"
            )
        ).all()
        print(f"count={len(rows)}")
        for row in rows:
            print(
                f"{row.id:>4} {row.name[:36]!r} organizer={row.organizer!r} "
                f"level={row.competition_level!r} category={row.category!r} desc={row[5]!r}"
            )

        print("\n== EVIDENCE: series/track rows ==")
        rows = db.execute(
            text(
                "SELECT c.id, c.name, c.competition_type, c.entity_type, "
                "COALESCE(p.name, '(root)') AS parent "
                "FROM competitions c LEFT JOIN competitions p ON p.id = c.parent_competition_id "
                "WHERE c.competition_type IN ('series','track') OR c.entity_type <> 'competition' "
                "ORDER BY c.competition_type, c.id"
            )
        ).all()
        for row in rows:
            print(
                f"{row.id:>4} type={row[2]:<12} entity={row[3]:<12} "
                f"parent={row[4][:28]!r} name={row[1][:44]!r}"
            )

        print("\n== EVIDENCE: competitions whose name is another competition's alias ==")
        rows = db.execute(
            text(
                "SELECT a.alias, a.competition_id AS alias_owner, c2.id AS name_owner, c2.name "
                "FROM competition_aliases a "
                "JOIN competitions c2 ON c2.name = a.alias "
                "WHERE a.competition_id <> c2.id "
                "ORDER BY a.alias LIMIT 60"
            )
        ).all()
        print(f"count={len(rows)}")
        for row in rows:
            print(row)

        print("\n== EVIDENCE: relations notice_type / verification distribution ==")
        rows = db.execute(
            text(
                "SELECT notice_type, verification_status, is_verified, source_type, COUNT(*) AS cnt "
                "FROM university_competition_edition_relations "
                "GROUP BY notice_type, verification_status, is_verified, source_type "
                "ORDER BY cnt DESC LIMIT 40"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== EVIDENCE: relation rows that look like award/result/activity (non-action) ==")
        rows = db.execute(
            text(
                "SELECT r.id, u.name, c.name, r.notice_type, substr(r.notice_title, 1, 70) "
                "FROM university_competition_edition_relations r "
                "JOIN universities u ON u.id = r.university_id "
                "JOIN competition_editions e ON e.id = r.competition_edition_id "
                "JOIN competitions c ON c.id = e.competition_id "
                "WHERE r.notice_type NOT IN "
                "('registration_notice','internal_selection','submission_notice','competition_announcement') "
                "ORDER BY r.id LIMIT 40"
            )
        ).all()
        for row in rows:
            print(f"r{row[0]} {row[1]} | {row[2]} | {row[3]} | {row[4]}")

        print("\n== EVIDENCE: deadline ordering violations (official > university) ==")
        rows = db.execute(
            text(
                "SELECT e.id, c.name, e.year, e.registration_deadline, "
                "e.official_registration_deadline, e.university_registration_deadline "
                "FROM competition_editions e JOIN competitions c ON c.id = e.competition_id "
                "WHERE e.official_registration_deadline IS NOT NULL "
                "AND e.university_registration_deadline IS NOT NULL "
                "AND e.university_registration_deadline > e.official_registration_deadline "
                "ORDER BY e.id"
            )
        ).all()
        print(f"count={len(rows)}")
        for row in rows:
            print(
                f"e{row[0]} {row[1][:32]!r} y{row[2]} plain={row[3]} official={row[4]} university={row[5]}"
            )

        print("\n== EVIDENCE: registration_deadline (generic) copied from university deadline ==")
        rows = db.execute(
            text(
                "SELECT e.id, c.name, e.year, e.registration_deadline, e.official_registration_deadline, "
                "e.university_registration_deadline "
                "FROM competition_editions e JOIN competitions c ON c.id = e.competition_id "
                "WHERE e.registration_deadline IS NOT NULL "
                "AND e.university_registration_deadline IS NOT NULL "
                "AND e.registration_deadline = e.university_registration_deadline "
                "AND (e.official_registration_deadline IS NULL OR "
                "e.official_registration_deadline <> e.registration_deadline) "
                "ORDER BY e.id LIMIT 40"
            )
        ).all()
        print(f"count={len(rows)}")
        for row in rows:
            print(
                f"e{row[0]} {row[1][:32]!r} y{row[2]} plain={row[3]} official={row[4]} university={row[5]}"
            )

        print("\n== EVIDENCE: 211 / 985 university coverage ==")
        rows = db.execute(
            text(
                "SELECT is_985, is_211, COUNT(*) AS cnt, "
                "SUM(CASE WHEN competition_discovery_status = 'completed' THEN 1 ELSE 0 END) AS completed, "
                "SUM(CASE WHEN competition_discovery_status = 'partial' THEN 1 ELSE 0 END) AS partial_ "
                "FROM universities GROUP BY is_985, is_211 ORDER BY is_985 DESC, is_211 DESC"
            )
        ).all()
        for row in rows:
            print(f"985={row[0]} 211={row[1]} total={row[2]} completed={row[3]} partial={row[4]}")

        print("\n== EVIDENCE: relations per university (top) ==")
        rows = db.execute(
            text(
                "SELECT u.name, COUNT(*) AS cnt, "
                "COUNT(DISTINCT r.competition_edition_id) AS editions, "
                "COUNT(DISTINCT e.competition_id) AS competitions "
                "FROM university_competition_edition_relations r "
                "JOIN universities u ON u.id = r.university_id "
                "JOIN competition_editions e ON e.id = r.competition_edition_id "
                "GROUP BY u.id ORDER BY cnt DESC LIMIT 15"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== EVIDENCE: report counts aggregate ==")
        rows = db.execute(
            text(
                "SELECT status, COUNT(*) AS cnt, SUM(competition_leads) AS leads, "
                "SUM(matched_competitions) AS matched, SUM(new_competitions) AS new_c, "
                "SUM(new_editions) AS new_e, SUM(university_notice_count) AS notices, "
                "SUM(internal_deadlines) AS deadlines "
                "FROM university_competition_discovery_reports "
                "GROUP BY status ORDER BY cnt DESC"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== EVIDENCE: 211 non-985 matched competitions count ==")
        rows = db.execute(
            text(
                "SELECT COUNT(DISTINCT l.matched_competition_id) FROM competition_leads l "
                "WHERE l.matched_competition_id IS NOT NULL"
            )
        ).scalar()
        print("distinct matched competition ids from leads:", rows)

        print("\n== EVIDENCE: competitions created with github_seed only (C-tier origin) ==")
        rows = db.execute(
            text(
                "SELECT c.id, c.name FROM competitions c "
                "JOIN competition_sources s ON s.competition_id = c.id "
                "WHERE s.source_type = 'github_seed' ORDER BY c.id LIMIT 60"
            )
        ).all()
        print(f"count={len(rows)}")
        for row in rows:
            print(f"{row[0]:>4} {row[1][:50]}")

        print("\n== SUMMARY: competition attribute coverage ==")
        rows = db.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN is_competition = 1 THEN 1 ELSE 0 END) AS is_competition_true, "
                "SUM(CASE WHEN organizer IS NOT NULL AND TRIM(organizer) <> '' THEN 1 ELSE 0 END) AS has_organizer, "
                "SUM(CASE WHEN official_website IS NOT NULL AND TRIM(official_website) <> '' THEN 1 ELSE 0 END) AS has_website, "
                "SUM(CASE WHEN description IS NOT NULL AND TRIM(description) <> '' THEN 1 ELSE 0 END) AS has_description, "
                "SUM(CASE WHEN is_official_verified = 1 THEN 1 ELSE 0 END) AS official_verified "
                "FROM competitions"
            )
        ).one()
        print(dict(rows._mapping))

        print("\n== SUMMARY: competitions whose ONLY source type is university_policy ==")
        rows = db.execute(
            text(
                "SELECT COUNT(*) AS cnt FROM competitions c "
                "WHERE EXISTS (SELECT 1 FROM competition_sources s "
                "WHERE s.competition_id = c.id AND s.source_type = 'university_policy') "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s2 "
                "WHERE s2.competition_id = c.id AND s2.source_type <> 'university_policy')"
            )
        ).scalar()
        print("policy-only competition count:", rows)

        print("\n== SUMMARY: editions by year and verification ==")
        rows = db.execute(
            text(
                "SELECT year, is_verified, verification_status, COUNT(*) AS cnt "
                "FROM competition_editions GROUP BY year, is_verified, verification_status ORDER BY year DESC"
            )
        ).all()
        for row in rows:
            print(row)

        print("\n== SUMMARY: partial / failed universities ==")
        rows = db.execute(
            text(
                "SELECT name, is_985, is_211, competition_discovery_status, "
                "COALESCE(substr(competition_discovery_error, 1, 90), '') AS err "
                "FROM universities "
                "WHERE competition_discovery_status <> 'completed' "
                "ORDER BY is_985 DESC, is_211 DESC, name"
            )
        ).all()
        for row in rows:
            print(f"{row[0]} 985={row[1]} 211={row[2]} status={row[3]} err={row[4]}")


if __name__ == "__main__":
    main()
