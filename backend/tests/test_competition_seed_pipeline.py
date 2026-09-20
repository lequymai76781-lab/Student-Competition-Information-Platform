import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionEdition, CompetitionSource
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_seed_import_service import CompetitionSeedImportService


def test_markdown_seed_is_unverified_and_idempotent(db_session: Session, tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.md"
    catalog.write_text(
        """# Catalog

## 算法编程类

### 1. 蓝桥杯全国软件和信息技术专业人才大赛

- **主办方**：工业和信息化部人才交流中心
- **官网**：dasai.lanqiao.cn
- **周期**：每年，省赛 4 月，国赛 5 月
- **赛制**：个人赛
""",
        encoding="utf-8",
    )
    service = CompetitionSeedImportService()

    first = service.import_file(db_session, catalog, source_repository="owner/repo", source_file="catalog.md")
    second = service.import_file(db_session, catalog, source_repository="owner/repo", source_file="catalog.md")

    competition = db_session.execute(
        select(Competition).where(Competition.name == "蓝桥杯全国软件和信息技术专业人才大赛")
    ).scalar_one()
    sources = list(
        db_session.execute(
            select(CompetitionSource).where(CompetitionSource.competition_id == competition.id)
        ).scalars()
    )
    assert first["parsed"] == 1
    assert second["created"] == 0
    assert len(sources) == 1
    assert sources[0].source_type == "github_seed"
    assert sources[0].is_verified is False
    assert sources[0].is_official is False


def test_json_and_csv_seed_formats_are_supported(tmp_path: Path) -> None:
    json_path = tmp_path / "seed.json"
    json_path.write_text(json.dumps({"competitions": [{"name": "JSON赛事"}]}, ensure_ascii=False), encoding="utf-8")
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text("name,category\nCSV赛事,传媒\n", encoding="utf-8")
    service = CompetitionSeedImportService()

    assert service.parse_file(json_path)[0].name == "JSON赛事"
    assert service.parse_file(csv_path)[0].category == "传媒"


def test_hierarchy_tags_and_priority_score(db_session: Session) -> None:
    parent = Competition(
        name="全国大学生机器人大赛—①RoboMaster②RoboCon",
        category="学科竞赛",
        team_type="团队赛",
        is_demo=False,
    )
    db_session.add(parent)
    db_session.flush()
    parent.editions.append(
        CompetitionEdition(
            year=2026,
            edition_name="2026测试届次",
            registration_deadline=datetime.now(timezone.utc) + timedelta(days=10),
            current_status="registration_open",
            is_verified=True,
        )
    )
    db_session.commit()

    service = CompetitionIntelligenceService()
    service.build_hierarchy(db_session)
    count_after_first_build = len(list(db_session.execute(select(Competition)).scalars()))
    service.build_hierarchy(db_session)
    count_after_second_build = len(list(db_session.execute(select(Competition)).scalars()))
    service.apply_tags(db_session)
    service.refresh_all(db_session)
    db_session.refresh(parent)

    children = list(
        db_session.execute(select(Competition).where(Competition.parent_competition_id == parent.id)).scalars()
    )
    assert parent.competition_type == "series"
    assert count_after_second_build == count_after_first_build
    assert {child.name for child in children} >= {"RoboMaster机甲大师赛", "ABU RoboCon全国大学生机器人大赛"}
    assert parent.tags
    assert parent.statistics is not None
    assert parent.statistics.priority_score >= 20
    assert parent.statistics.score_breakdown["registration_status"] == 20
