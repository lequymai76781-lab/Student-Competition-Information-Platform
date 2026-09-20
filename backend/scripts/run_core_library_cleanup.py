"""V11 core-library cleanup: duplicate resolution + historical/common aliases.

Only evidence-backed decisions are applied:
- 全国大学生生命科学竞赛 (id 102) is a duplicate of the CAHE-directory row
  “全国大学生生命科学竞赛（CULSC）”(id 53).
- 全国高校商业精英挑战赛会展专业创新创业实践竞赛 (id 118) is a duplicate /
  former-name of 文旅与会展创新创业实践竞赛 (id 121), which now carries an
  A-level CAHE directory source.

Nothing is deleted; every change is idempotent and logged to AdminAuditLog.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import AdminAuditLog, Competition, CompetitionAlias


def _ensure_alias(
    db,
    competition_id: int,
    alias: str,
    *,
    source: str,
    confidence: float,
    is_verified: bool,
) -> bool:
    normalized = alias.strip()
    exists = db.execute(
        select(CompetitionAlias).where(
            CompetitionAlias.competition_id == competition_id,
            CompetitionAlias.alias == normalized,
        )
    ).scalars().first()
    if exists:
        return False
    db.add(
        CompetitionAlias(
            competition_id=competition_id,
            alias=normalized,
            normalized_alias=normalized,
            source=source,
            confidence=confidence,
            is_verified=is_verified,
            is_demo=False,
        )
    )
    return True


def _audit(db, action: str, object_type: str, object_id: int, before: dict, after: dict) -> None:
    db.add(
        AdminAuditLog(
            admin_id=None,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before,
            after=after,
            created_at=datetime.now(timezone.utc),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply
    changes: list[dict] = []

    with SessionLocal() as db:
        # --- duplicate resolutions -------------------------------------
        duplicate_pairs = [
            {
                "dup_id": 102,
                "keep_id": 53,
                "reason": "同名赛事：全国大学生生命科学竞赛（CULSC）为高教学会2023目录第44项；id=102 为无CULSC后缀的重复记录，仅含D级来源",
            },
            {
                "dup_id": 118,
                "keep_id": 121,
                "reason": "高教学会2023目录第47项子赛名称为“文旅与会展创新创业实践竞赛”（=id121）；id=118 “会展专业创新创业实践竞赛”为历史/别名形式，未获目录独立收录",
            },
        ]
        for pair in duplicate_pairs:
            dup = db.get(Competition, pair["dup_id"])
            keep = db.get(Competition, pair["keep_id"])
            if dup is None or keep is None:
                continue
            alias_added = _ensure_alias(
                db,
                keep.id,
                dup.name,
                source="core-library-cleanup-v11",
                confidence=0.99,
                is_verified=True,
            )
            before = {
                "verification_status": dup.verification_status,
                "is_official_verified": dup.is_official_verified,
            }
            after = {"verification_status": "duplicate", "is_official_verified": False}
            changes.append(
                {
                    "type": "duplicate",
                    "dup_id": dup.id,
                    "keep_id": keep.id,
                    "alias_added": alias_added,
                    "before": before,
                    "after": after,
                    "reason": pair["reason"],
                }
            )
            if not dry_run and dup.verification_status != "duplicate":
                dup.verification_status = "duplicate"
                dup.is_official_verified = False
                _audit(db, "mark_duplicate", "competition", dup.id, before, after)

        # --- aliases: colloquial / historical names --------------------
        alias_plan = [
            (2, "大挑", "common_name", 0.95, False, "学生俗称，非官方名称"),
            (3, "小挑", "common_name", 0.95, False, "学生俗称，非官方名称"),
            (1, "中国“互联网+”大学生创新创业大赛", "cahe-directory-2023", 1.0, True, "2023目录原始名称"),
            (1, "“互联网+”大学生创新创业大赛", "historical_name", 1.0, True, "历史官方名称"),
            (3, "“挑战杯”中国大学生创业计划大赛", "cahe-directory-2023", 1.0, True, "2023目录用名（大赛/竞赛变体）"),
            (24, "外研社全国大学生英语系列赛", "cahe-directory-2023", 1.0, True, "2023目录原始名称"),
            (28, "全国大学生机器人大赛（CURC）", "cahe-directory-2023", 1.0, True, "2023目录用名"),
            (35, "中国高校计算机大赛（C4）", "common_name", 0.95, False, "英文缩写"),
            (101, "NECCS", "common_name", 0.95, False, "英文缩写"),
            (98, "美赛", "common_name", 0.95, False, "学生俗称"),
        ]
        for comp_id, alias, source, confidence, verified, note in alias_plan:
            competition = db.get(Competition, comp_id)
            if competition is None:
                continue
            added = _ensure_alias(
                db,
                comp_id,
                alias,
                source=source,
                confidence=confidence,
                is_verified=verified,
            )
            changes.append(
                {
                    "type": "alias",
                    "competition_id": comp_id,
                    "alias": alias,
                    "source": source,
                    "is_verified": verified,
                    "note": note,
                    "added": added,
                }
            )
            if not dry_run and added:
                _audit(
                    db,
                    "add_alias",
                    "competition",
                    comp_id,
                    {"alias": alias},
                    {"alias": alias, "source": source, "is_verified": verified},
                )
        if not dry_run:
            db.commit()
        statuses = dict(
            db.execute(
                text("SELECT verification_status, COUNT(*) FROM competitions GROUP BY verification_status")
            ).fetchall()
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "changes": changes,
        "status_after": dict(statuses),
    }
    out = PROJECT_ROOT / "data" / "reports" / "v11_core_library_cleanup_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
