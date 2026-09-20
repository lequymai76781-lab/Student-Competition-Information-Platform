"""V0.8.2 precision fixes over the imported V0.8.1 data.

1. Re-classifies V0.8.1 leads with the refined classifier (result/award/activity/
   training/irrelevant buckets, teacher/admission noise).
2. Removes relations that are award/result/activity/training/column pages and
   de-duplicates relations per (university, competition, normalized title).
3. Clears impossible internal deadlines (deadline earlier than publish date).
4. Recomputes edition university_registration_deadline from surviving relations.
"""

import json
import re
import sys
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import (
    CompetitionEdition,
    CompetitionLead,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_discovery_service import CompetitionDiscoveryService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.university_radar_discovery_service import UniversityRadarDiscoveryService

ACTION_RELATION_CLASSES = {
    "registration_notice",
    "competition_announcement",
    "internal_selection",
    "submission_notice",
    "team_recruitment",
}


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (value or "").lower())


def _is_article_url(url: str) -> bool:
    from urllib.parse import urlparse

    path = urlparse(url).path.lower().rstrip("/")
    if path in {"", "/index.htm", "/index.html", "/index.php", "/default.htm", "/default.html", "/main.htm"}:
        return False
    if path.endswith(("list.htm", "list.html", "more.jsp", "more.do", "more.htm")):
        return False
    if re.search(r"/(?:tzgg|notice|news|list|gg|zxdt|tongzhi|cxcy|cxds|xkjs)[/-]?$", path):
        return False
    return True


def _garbage_title(title: str) -> bool:
    return bool(re.match(r"^【\s*作者|^【\s*来自|责任编辑", title or ""))


def _audit_class(title: str, text: str, url: str, classifier) -> str:
    if _garbage_title(title):
        return "irrelevant"
    if not _is_article_url(url):
        return "irrelevant"
    return classifier(title or "", text or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Compute decisions without persisting.")
    args = parser.parse_args()
    seed_path = ROOT / "data" / "seeds" / "v081_211_radar_fix_discovery.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    leads_payload = seed["leads"]
    rels_payload = seed["edition_relations"]
    seed_urls = {item["internal_notice_url"] for item in rels_payload}

    probe = UniversityRadarDiscoveryService()
    classifier = probe._classification

    with SessionLocal() as db:
        # ---------------- 1. Reclassify leads ---------------- #
        lead_updates: Counter = Counter()
        lead_rows = list(db.execute(select(CompetitionLead)).scalars())
        by_url_title = {(row.source_url, row.raw_title): row for row in lead_rows}
        for item in leads_payload:
            row = by_url_title.get((item["source_url"], item["raw_title"]))
            if row is None:
                continue
            audit_class = _audit_class(
                item.get("raw_title") or "",
                item.get("raw_content") or "",
                item.get("source_url") or "",
                classifier,
            )
            old_class = row.classification
            if old_class != audit_class:
                row.classification = audit_class
                lead_updates["reclassified"] += 1
            if audit_class in {"activity", "training_notice", "irrelevant", "unknown"}:
                row.needs_review = True
                lead_updates["needs_review"] += 1
        db.flush()

        # ---------------- 2. Relation audit ---------------- #
        relations = list(
            db.execute(
                select(UniversityCompetitionEditionRelation).where(
                    UniversityCompetitionEditionRelation.internal_notice_url.in_(seed_urls)
                )
            ).scalars()
        )
        rel_by_url = {row.internal_notice_url: row for row in relations}
        kept: list[UniversityCompetitionEditionRelation] = []
        invalid_urls: list[str] = []
        class_by_url: dict[str, str] = {}
        for item in rels_payload:
            row = rel_by_url.get(item["internal_notice_url"])
            if row is None:
                continue
            title = item.get("notice_title") or item.get("raw_title") or item.get("edition_name") or ""
            audit_class = _audit_class(
                title,
                "",
                item.get("internal_notice_url") or "",
                classifier,
            )
            class_by_url[item["internal_notice_url"]] = audit_class
            if audit_class not in ACTION_RELATION_CLASSES:
                invalid_urls.append(item["internal_notice_url"])
            else:
                kept.append(row)

        # de-duplicate by (university, competition, normalized title)
        seen_keys: dict[tuple, UniversityCompetitionEditionRelation] = {}
        duplicate_rows: list[UniversityCompetitionEditionRelation] = []
        for row in kept:
            key = (
                row.university_id,
                row.competition_edition_id,
                _norm(row.notice_title or ""),
            )
            existing = seen_keys.get(key)
            if existing is None:
                seen_keys[key] = row
            else:
                duplicate_rows.append(row)

        removed_urls = set(invalid_urls)
        for row in relations:
            if row in duplicate_rows or row.internal_notice_url in removed_urls:
                db.delete(row)

        # update notice_type for survivors
        survivors = [row for row in relations if row not in duplicate_rows and row.internal_notice_url not in removed_urls]
        for row in survivors:
            audit_class = class_by_url.get(row.internal_notice_url)
            if audit_class and audit_class in ACTION_RELATION_CLASSES:
                row.notice_type = audit_class

        # ---------------- 3. Deadline sanity ---------------- #
        cleared_deadlines = 0
        for row in survivors:
            deadline = row.internal_registration_deadline
            if deadline is None:
                continue
            if row.published_at and deadline < row.published_at:
                row.internal_registration_deadline = None
                row.college_registration_deadline = None
                cleared_deadlines += 1
                continue
            if deadline.year not in {2025, 2026, 2027}:
                row.internal_registration_deadline = None
                row.college_registration_deadline = None
                cleared_deadlines += 1

        # ---------------- 4. Recompute edition university deadline ---------------- #
        all_survivors = list(
            db.execute(
                select(UniversityCompetitionEditionRelation).where(
                    UniversityCompetitionEditionRelation.competition_edition_id.in_(
                        select(CompetitionEdition.id)
                    )
                )
            ).scalars()
        )
        deadline_by_edition: dict[int, datetime] = {}
        for relation in all_survivors:
            if relation.college_id is not None:
                continue
            deadline = relation.internal_registration_deadline
            if deadline is None:
                continue
            current = deadline_by_edition.get(relation.competition_edition_id)
            if current is None or deadline < current:
                deadline_by_edition[relation.competition_edition_id] = deadline
        for edition in db.execute(select(CompetitionEdition)).scalars():
            deadline = deadline_by_edition.get(edition.id)
            if deadline is not None and edition.university_registration_deadline != deadline:
                edition.university_registration_deadline = deadline

        db.flush()
        removed_relations = len(invalid_urls) + len(duplicate_rows)
        print("leads reclassified:", lead_updates["reclassified"])
        print("leads marked review:", lead_updates["needs_review"])
        print("relations removed (invalid+dup):", removed_relations, f"(invalid={len(invalid_urls)}, dup={len(duplicate_rows)})")
        print("relations surviving v081:", len(survivors))
        print("deadlines cleared:", cleared_deadlines)
        if args.dry_run:
            db.rollback()
            print("DRY RUN - no changes persisted")
            return

        # write audited seed artifact
        classification_by_item: dict[int, str] = {}
        for index, item in enumerate(leads_payload):
            row = by_url_title.get((item["source_url"], item["raw_title"]))
            if row is not None:
                classification_by_item[index] = row.classification
        for index, item in enumerate(leads_payload):
            if index in classification_by_item:
                item["classification"] = classification_by_item[index]
        seed["audit_note"] = "V0.8.2 classification applied"
        out_path = ROOT / "data" / "seeds" / "v081_211_radar_fix_discovery_audited.json"
        out_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

        intelligence = CompetitionIntelligenceService()
        intelligence.apply_tags(db)
        intelligence.refresh_all(db)
        db.commit()
        coverage = CompetitionDiscoveryService().v08_coverage_summary(db)
        report_path = ROOT / "data" / "reports" / "v081_precision_fix_summary.json"
        report_path.write_text(
            json.dumps(
                {
                    "leads_reclassified": lead_updates["reclassified"],
                    "leads_marked_review": lead_updates["needs_review"],
                    "relations_removed": removed_relations,
                    "relations_invalid": len(invalid_urls),
                    "relations_duplicates": len(duplicate_rows),
                    "relations_surviving_v081": len(survivors),
                    "deadlines_cleared": cleared_deadlines,
                    "coverage": coverage,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print("wrote audited seed + summary")


if __name__ == "__main__":
    main()
