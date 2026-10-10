from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Competition, CompetitionEdition, UniversityCompetitionEditionRelation


def update_edition(db, **values):
    edition = db.get(CompetitionEdition, 1)
    for field, value in values.items():
        setattr(edition, field, value)
    db.commit()
    return edition


def test_expired_cached_open_is_excluded_and_read_does_not_write(client, db_session):
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    update_edition(db_session, registration_deadline=yesterday, official_registration_deadline=yesterday)
    assert client.get('/api/competitions?edition_status=registration_open').json()['data'] == []
    detail = client.get('/api/competitions/1').json()['data']
    assert detail['current_status'] == 'registration_closed'
    assert detail['editions'][0]['current_status'] == 'registration_closed'
    assert not db_session.dirty
    assert db_session.get(CompetitionEdition, 1).current_status == 'registration_open'


def test_future_start_overrides_cached_open(client, db_session):
    start = datetime.now(timezone.utc) + timedelta(days=3)
    update_edition(db_session, registration_start=start)
    assert client.get('/api/competitions?edition_status=registration_open').json()['data'] == []
    rows = client.get('/api/competitions?edition_status=registration_upcoming').json()['data']
    assert len(rows) == 1
    assert rows[0]['action_deadline_label'] == '报名开始'
    assert datetime.fromisoformat(rows[0]['action_deadline']).replace(tzinfo=timezone.utc) == start


@pytest.mark.parametrize('values', [
    {'registration_deadline': None, 'official_registration_deadline': None},
    {'is_verified': False},
    {'current_status': 'cancelled'},
    {'current_status': 'finished'},
])
def test_no_actionable_dates_or_unverified_or_terminal_not_open(client, db_session, values):
    update_edition(db_session, **values)
    assert client.get('/api/competitions?edition_status=registration_open').json()['data'] == []
    assert client.get('/api/competitions?availability=next_30_days').json()['data'] == []


def test_official_deadline_takes_precedence_over_legacy_deadline(client, db_session):
    now = datetime.now(timezone.utc)
    update_edition(db_session, registration_deadline=now - timedelta(days=1),
                   official_registration_deadline=now + timedelta(days=5))
    rows = client.get('/api/competitions?availability=next_30_days&edition_status=registration_open').json()['data']
    assert len(rows) == 1
    assert rows[0]['action_deadline'] == rows[0]['official_registration_deadline']


def test_school_deadline_closes_only_selected_school(client, db_session):
    relation = db_session.get(UniversityCompetitionEditionRelation, 1)
    relation.internal_registration_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    assert len(client.get('/api/competitions?edition_status=registration_open').json()['data']) == 1
    assert client.get('/api/competitions?edition_status=registration_open&university_id=1').json()['data'] == []
    detail = client.get('/api/competitions/1?university_id=1').json()['data']
    assert detail['current_status'] == 'registration_closed'
    assert detail['editions'][0]['current_status'] == 'registration_closed'


def test_unverified_school_notice_cannot_override_deadline(client, db_session):
    relation = db_session.get(UniversityCompetitionEditionRelation, 1)
    relation.is_verified = False
    relation.internal_registration_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    detail = client.get('/api/competitions/1?university_id=1').json()['data']
    assert detail['effective_deadline'] == detail['official_registration_deadline']


def test_sort_by_effective_deadline_before_pagination(client, db_session):
    now = datetime.now(timezone.utc)
    for index, days in enumerate([20, 3, 10]):
        competition = Competition(name=f'分页测试赛事{index}', is_competition=True,
                                  verification_status='verified_official', is_demo=False,
                                  updated_at=now + timedelta(minutes=index))
        db_session.add(competition)
        db_session.flush()
        db_session.add(CompetitionEdition(competition_id=competition.id, year=now.year,
            official_registration_deadline=now + timedelta(days=days), is_verified=True,
            current_status='registration_open'))
    db_session.commit()
    first = client.get('/api/competitions?sort=deadline&limit=1').json()['data']
    second = client.get('/api/competitions?sort=deadline&limit=1&offset=1').json()['data']
    assert first[0]['name'] == '分页测试赛事1'
    assert second[0]['name'] == '分页测试赛事2'


def test_filtered_edition_is_the_edition_displayed(client, db_session):
    now = datetime.now(timezone.utc)
    old = update_edition(db_session, year=2025, current_status='finished',
                        official_registration_deadline=now - timedelta(days=400),
                        registration_deadline=now - timedelta(days=400))
    db_session.add(CompetitionEdition(competition_id=old.competition_id, year=2027,
        edition_name='2027测试届次', is_verified=True, current_status='registration_open',
        registration_deadline=now + timedelta(days=3)))
    db_session.commit()
    assert client.get('/api/competitions?year=2025&edition_status=registration_open').json()['data'] == []
    rows = client.get('/api/competitions?year=2025').json()['data']
    assert rows[0]['current_edition_name'] != '2027测试届次'
    detail = client.get('/api/competitions/1').json()['data']
    assert detail['current_edition_id'] == 2


def test_unknown_status_with_verified_dates_is_resolved(client, db_session):
    update_edition(db_session, current_status='unknown')
    rows = client.get('/api/competitions?edition_status=registration_open').json()['data']
    assert len(rows) == 1
    assert rows[0]['current_status'] == 'registration_open'


def test_notice_scope_and_status_match_the_same_edition(client, db_session):
    now = datetime.now(timezone.utc)
    old = update_edition(db_session, year=now.year - 1, current_status='finished')
    db_session.add(CompetitionEdition(competition_id=old.competition_id, year=now.year,
        edition_name='新届无学校通知', is_verified=True, current_status='registration_open',
        official_registration_deadline=now + timedelta(days=3)))
    db_session.commit()
    scope = '/api/competitions?source_scope=my_university_notice&university_id=1'
    assert client.get(scope + '&edition_status=registration_open').json()['data'] == []
    assert client.get(scope + f'&year={now.year}').json()['data'] == []
    rows = client.get(scope).json()['data']
    assert len(rows) == 1
    assert rows[0]['current_edition_id'] == old.id


def test_unverified_notice_does_not_satisfy_school_scope(client, db_session):
    relation = db_session.get(UniversityCompetitionEditionRelation, 1)
    relation.is_verified = False
    db_session.commit()
    assert client.get('/api/competitions?source_scope=my_university_notice&university_id=1').json()['data'] == []


def test_conflicting_open_scope_and_finished_status_returns_no_rows(client, db_session):
    update_edition(db_session, current_status='finished')
    assert client.get('/api/competitions?source_scope=registration_open&edition_status=finished').json()['data'] == []


def test_submission_window_is_separate_from_registration(client, db_session):
    now = datetime.now(timezone.utc)
    update_edition(db_session, registration_deadline=now - timedelta(days=1),
        official_registration_deadline=now - timedelta(days=1),
        official_submission_deadline=now + timedelta(days=7))
    assert client.get('/api/competitions?edition_status=registration_open').json()['data'] == []
    rows = client.get('/api/competitions?edition_status=submission_open').json()['data']
    assert rows[0]['action_deadline_label'] == '官方作品截止'


def test_school_scope_requires_a_school(client):
    assert client.get('/api/competitions?source_scope=my_university_notice').status_code == 422


def test_open_stats_use_current_dates(client, db_session):
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    update_edition(db_session, registration_deadline=yesterday, official_registration_deadline=yesterday)
    assert client.get('/api/stats').json()['data']['registration_open'] == 0


def test_open_stats_use_official_deadline_and_future_start(client, db_session):
    now = datetime.now(timezone.utc)
    update_edition(db_session, registration_deadline=now - timedelta(days=1),
                   official_registration_deadline=now + timedelta(days=5))
    assert client.get('/api/stats').json()['data']['registration_open'] == 1
    update_edition(db_session, registration_start=now + timedelta(days=1))
    assert client.get('/api/stats').json()['data']['registration_open'] == 0
