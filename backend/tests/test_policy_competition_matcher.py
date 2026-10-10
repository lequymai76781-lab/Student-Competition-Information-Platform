from sqlalchemy import select

from app.models import Competition, CompetitionAlias
from app.services.policy_competition_matcher import match_policy_competition


def add_competition(db, name, **kwargs):
    competition = Competition(name=name, is_demo=False, **kwargs)
    db.add(competition)
    db.flush()
    return competition


def test_unique_exact_name_short_name_english_and_verified_alias_auto_match(db_session):
    competition = add_competition(db_session, "全国大学生数学建模竞赛", short_name="国赛建模", english_name="China Undergraduate Mathematical Contest in Modeling")
    db_session.add(CompetitionAlias(competition_id=competition.id, alias="全国大学生数学模型竞赛", normalized_alias="全国大学生数学模型竞赛", is_verified=True))
    db_session.flush()
    for raw in [competition.name, "国赛建模", competition.english_name, "全国大学生数学模型竞赛", "2026年第35届全国大学生数学建模竞赛"]:
        result = match_policy_competition(db_session, raw)
        assert result["match_status"] == "AUTO_MATCHED", raw
        assert result["matched_competition_id"] == competition.id


def test_unverified_alias_and_former_name_never_auto_match(db_session):
    competition = add_competition(db_session, "中国国际大学生创新大赛", former_names=["旧版创新创业赛"])
    db_session.add(CompetitionAlias(competition_id=competition.id, alias="创新创业杯", normalized_alias="创新创业杯", is_verified=False))
    db_session.flush()
    for raw in ["创新创业杯", "旧版创新创业赛"]:
        result = match_policy_competition(db_session, raw)
        assert result["match_status"] == "NEEDS_QUICK_CONFIRM"
        assert result["matched_competition_id"] is None
        assert result["candidate_ids"] == [competition.id]


def test_duplicate_alias_and_parent_child_track_ambiguity_require_manual_review(db_session):
    parent = add_competition(db_session, "挑战杯全国大学生课外学术科技作品竞赛", short_name="挑战杯")
    child = add_competition(db_session, "挑战杯全国大学生课外学术科技作品竞赛人工智能专项赛", short_name="挑战杯", parent_competition_id=parent.id)
    for item in (parent, child):
        db_session.add(CompetitionAlias(competition_id=item.id, alias="挑战杯", normalized_alias="挑战杯", is_verified=True))
    db_session.flush()
    result = match_policy_competition(db_session, "挑战杯")
    assert result["match_status"] == "NEEDS_MANUAL_MATCH"
    assert result["matched_competition_id"] is None
    assert result["candidate_ids"] == [parent.id, child.id]
    result = match_policy_competition(db_session, "挑战杯全国大学生课外学术科技作品竞赛人工智能赛道")
    assert result["match_status"] != "AUTO_MATCHED"


def test_national_china_and_similar_names_need_confirmation(db_session):
    competition = add_competition(db_session, "全国大学生电子设计竞赛")
    for raw in ["中国大学生电子设计竞赛", "全国大学生电子设计大赛"]:
        result = match_policy_competition(db_session, raw)
        assert result["match_status"] != "AUTO_MATCHED"
        assert result["matched_competition_id"] is None


def test_demo_and_noncompetition_are_not_formal_candidates(db_session):
    db_session.add_all([
        Competition(name="虚构演示赛", is_demo=True),
        Competition(name="学生发展活动", is_demo=False, is_competition=False),
    ])
    db_session.flush()
    for raw in ["虚构演示赛", "学生发展活动", ""]:
        result = match_policy_competition(db_session, raw)
        assert result["match_status"] == "NEEDS_MANUAL_MATCH"
        assert result["matched_competition_id"] is None


def test_matcher_does_not_write_to_database(db_session):
    before = db_session.execute(select(Competition.id)).all()
    match_policy_competition(db_session, "全新未知比赛")
    assert db_session.execute(select(Competition.id)).all() == before
