from sqlalchemy.orm import Session

from app.models import Competition
from app.services.competition_normalization_service import CompetitionNormalizationService


def test_verified_alias_merges_to_competition(db_session: Session) -> None:
    competition = Competition(name="中国国际大学生创新大赛", short_name="国创赛", is_demo=False)
    db_session.add(competition)
    db_session.flush()

    service = CompetitionNormalizationService()
    service.ensure_alias(db_session, competition, "中国国际大学生互联网创新创业大赛", confidence=0.95, is_verified=True)

    result = service.normalize(db_session, "中国国际大学生互联网创新创业大赛")

    assert result.competition is not None
    assert result.competition.id == competition.id
    assert result.method == "exact_alias"
    assert result.needs_manual_review is False


def test_challenge_cup_short_name_is_not_auto_merged(db_session: Session) -> None:
    db_session.add_all(
        [
            Competition(name="挑战杯全国大学生课外学术科技作品竞赛", short_name="大挑", is_demo=False),
            Competition(name="挑战杯中国大学生创业计划竞赛", short_name="小挑", is_demo=False),
        ]
    )
    db_session.flush()

    result = CompetitionNormalizationService().normalize(db_session, "挑战杯")

    assert result.competition is None
    assert result.needs_manual_review is True
    assert result.reason == "ambiguous_short_name"


def test_verified_policy_can_create_new_competition(db_session: Session) -> None:
    service = CompetitionNormalizationService()

    result = service.normalize_or_create(
        db_session,
        "全国大学生数学建模竞赛",
        trusted_policy=True,
        source_title="已验证政策",
        category="学科竞赛",
    )

    assert result.competition is not None
    assert result.method == "created_from_verified_policy"
    assert result.competition.is_demo is False


def test_challenge_cup_variants_stay_distinct(db_session: Session) -> None:
    service = CompetitionNormalizationService()
    first = service.normalize_or_create(
        db_session,
        "“挑战杯”全国大学生课外学术科技作品竞赛",
        trusted_policy=True,
        source_title="已验证政策",
    )
    second = service.normalize_or_create(
        db_session,
        "“挑战杯”中国大学生创业计划竞赛",
        trusted_policy=True,
        source_title="已验证政策",
    )

    assert first.competition is not None
    assert second.competition is not None
    assert first.competition.id != second.competition.id
