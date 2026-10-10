"""Regression coverage uses only conftest's isolated SQLite database."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import DateTime, select, text
from sqlalchemy.orm import Session
from app.core.ratelimit import _store

from app.models import (
    Base, College, CompetitionEdition, CompetitionFactSource, CompetitionPolicyRecognition,
    CompetitionSource, CompetitionUpdateEvent, Competition, Major, PolicyDocument, University, UniversityCompetitionEditionRelation,
    User, UniversityPolicy,
)
from app.services.deadline_resolution_service import DeadlineResolutionService
from app.services.competition_freshness_service import CompetitionFreshnessService


UTC = timezone.utc
NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_rate_limits():
    _store.clear()
    yield
    _store.clear()


def login(client):
    result = client.post('/api/auth/register', json={
        'email': 'edition-boundaries@example.com', 'password': 'StrongPass123!', 'username': 'edition-boundaries',
    })
    assert result.status_code == 200, result.text
    token = result.json()['data']['token']
    return {'Authorization': f'Bearer {token}'}


def editions(db):
    current = db.get(CompetitionEdition, 1)
    current.registration_start = datetime(2026, 10, 1, tzinfo=UTC)
    current.official_registration_deadline = datetime(2026, 10, 10, tzinfo=UTC)
    current.registration_deadline = current.official_registration_deadline
    result = {2026: current}
    for year in (2024, 2025):
        row = CompetitionEdition(competition_id=1, year=year, edition_name=f'{year}历史届次',
            is_verified=True, current_status='finished',
            registration_start=datetime(year, 3, 1, tzinfo=UTC),
            official_registration_deadline=datetime(year, 4, 1, tzinfo=UTC))
        db.add(row)
        db.flush()
        result[year] = row
    for year, row in result.items():
        db.add(CompetitionSource(competition_id=1, competition_edition_id=row.id,
            source_type='official', source_url=f'https://example.com/{year}',
            is_verified=True, verification_status='verified_official'))
        db.add(CompetitionFactSource(competition_id=1, competition_edition_id=row.id,
            field_name='registration_start', fact_value=str(year), source_type='official',
            source_url=f'https://example.com/facts/{year}', reliability_tier=1,
            observed_at=NOW, verification_status='verified_official'))
        if year != 2026:
            db.add(UniversityCompetitionEditionRelation(university_id=1,
                competition_edition_id=row.id, notice_title=f'{year}历史通知',
                notice_type='registration_notice', source_type='university_official_notice',
                internal_notice_url=f'https://example.edu.cn/{year}', observed_at=NOW,
                internal_registration_deadline=datetime(year, 3, 20, tzinfo=UTC),
                is_verified=True, verification_status='verified_official'))
    db.commit()
    return result


@pytest.mark.parametrize('year', [2024, 2025, 2026])
def test_explicit_edition_scopes_detail_and_personal_context(client, db_session, year):
    rows = editions(db_session)
    headers = login(client)
    client.put('/api/users/me/profile', headers=headers, json={'university_id': 1})
    target = rows[year]
    detail = client.get(f'/api/competitions/1?edition_id={target.id}&university_id=1').json()['data']
    context = client.get(f'/api/users/me/competitions/1/context?edition_id={target.id}&university_id=1',
        headers=headers).json()['data']['item']
    assert context['edition_year'] == year
    assert context['current_status'] == detail['current_status']
    assert context['effective_deadline'] == detail['action_deadline'] or (
        datetime.fromisoformat(context['effective_deadline']) == datetime.fromisoformat(detail['action_deadline']))
    assert all(n['competition_edition_id'] == target.id for n in detail['university_notices'])
    source_urls = {s['source_url'] for s in detail['sources']}
    assert f'https://example.com/{year}' in source_urls
    assert all(f'https://example.com/{other}' not in source_urls for other in (2024, 2025, 2026) if other != year)
    assert all(s['competition_edition_id'] in (None, target.id) for s in detail['fact_sources'])


def test_explicit_missing_edition_is_unknown_and_school_override_is_respected(client, db_session):
    rows = editions(db_session)
    headers = login(client)
    client.put('/api/users/me/profile', headers=headers, json={'university_id': 1})
    other = University(name='另一所隔离学校')
    db_session.add(other)
    db_session.commit()
    item = client.get(f'/api/users/me/competitions/1/context?edition_id={rows[2025].id}&university_id={other.id}',
        headers=headers).json()['data']['item']
    assert item['school_notice'] is False
    assert item['university_deadline'] is None
    item = client.get('/api/users/me/competitions/1/context?edition_id=99999', headers=headers).json()['data']['item']
    assert item['current_status'] == 'unknown'
    assert item['effective_deadline'] is None
    assert item['relation'] is None


def test_latest_personal_context_does_not_reuse_historical_notice(client, db_session):
    rows = editions(db_session)
    db_session.delete(db_session.get(UniversityCompetitionEditionRelation, 1))
    db_session.commit()
    headers = login(client)
    client.put('/api/users/me/profile', headers=headers, json={'university_id': 1})
    item = client.get('/api/users/me/competitions/1/context', headers=headers).json()['data']['item']
    assert item['edition_year'] == 2026
    assert item['school_notice'] is False
    assert item['relation'] is None


@pytest.mark.parametrize('school_start,school_end,official_start,expected', [
    (NOW + timedelta(days=3), None, None, 'registration_upcoming'),
    (None, NOW + timedelta(days=2), NOW + timedelta(days=5), 'registration_open'),
])
def test_school_registration_start_is_independent_of_deadline_source(db_session, school_start, school_end, official_start, expected):
    edition = db_session.get(CompetitionEdition, 1)
    relation = db_session.get(UniversityCompetitionEditionRelation, 1)
    edition.registration_start = official_start
    edition.official_registration_deadline = NOW + timedelta(days=20)
    relation.internal_registration_start = school_start
    relation.internal_registration_deadline = school_end
    db_session.commit()
    assert DeadlineResolutionService().status(edition, university_id=1, now=NOW) == expected


def test_registration_after_competition_end_cannot_be_actionable(db_session):
    edition = db_session.get(CompetitionEdition, 1)
    edition.competition_end = NOW + timedelta(days=1)
    edition.registration_start = NOW + timedelta(days=3)
    edition.official_registration_deadline = NOW + timedelta(days=20)
    assert DeadlineResolutionService().status(edition, now=NOW) == 'unknown'


@pytest.mark.parametrize('timestamp', [
    '2026-10-06T23:59:59+08:00', '2026-10-07T00:00:00+08:00',
    '2026-11-01T01:30:00-04:00', '2026-11-01T01:30:00-05:00',
    '2026-03-08T01:59:59-05:00', '2026-03-08T03:00:00-04:00',
    '2026-10-06T23:59:59',
])
def test_deadline_round_trip_preserves_instant_and_exact_boundary(db_session, client, timestamp):
    original = datetime.fromisoformat(timestamp)
    expected = original.replace(tzinfo=UTC) if original.tzinfo is None else original.astimezone(UTC)
    edition = db_session.get(CompetitionEdition, 1)
    CompetitionFreshnessService().update_edition_fact(db_session, edition,
        field_name='official_registration_deadline', value=original, changed_at=NOW,
        source_url='https://example.com/verified')
    db_session.commit()
    with Session(db_session.bind) as fresh:
        reloaded = fresh.get(CompetitionEdition, 1)
        assert reloaded.official_registration_deadline == expected
        assert reloaded.official_registration_deadline.utcoffset() == timedelta(0)
        service = DeadlineResolutionService()
        assert service.status(reloaded, now=expected) == 'registration_open'
        assert service.status(reloaded, now=expected + timedelta(microseconds=1)) == 'registration_closed'
        stored = fresh.execute(text('SELECT official_registration_deadline FROM competition_editions WHERE id=1')).scalar_one()
        assert datetime.fromisoformat(stored) == expected.replace(tzinfo=None)
    detail = client.get('/api/competitions/1?edition_id=1').json()['data']
    api_value = detail['official_registration_deadline']
    assert api_value.endswith(('Z', '+00:00'))
    assert datetime.fromisoformat(api_value) == expected


def test_utc_policy_covers_notice_and_source_dates_without_schema_change(db_session):
    incoming = datetime(2026, 10, 7, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    relation = db_session.get(UniversityCompetitionEditionRelation, 1)
    source = db_session.get(CompetitionSource, 1)
    relation.internal_registration_start = incoming
    source.published_at = incoming
    db_session.commit()
    with Session(db_session.bind) as fresh:
        assert fresh.get(UniversityCompetitionEditionRelation, 1).internal_registration_start == incoming
        assert fresh.get(CompetitionSource, 1).published_at == incoming
    # All pre-existing timestamp columns keep the original SQL DateTime DDL.
    dialect = db_session.bind.dialect
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime) or isinstance(getattr(column.type, 'impl', None), DateTime):
                assert column.type.compile(dialect=dialect) == DateTime(timezone=True).compile(dialect=dialect)


@pytest.mark.parametrize('status,manual,verified', [
    ('insufficient_evidence', True, False), ('recognized', True, True),
    ('recognized', False, False), ('pending', False, True),
])
def test_unverified_recognition_never_becomes_a_public_fact(client, db_session, status, manual, verified):
    policy = PolicyDocument(university_id=1, title='测试核验政策', source_url='https://example.edu.cn/policy',
        year=2026, is_verified=verified, verification_status='verified_official' if verified else 'pending')
    db_session.add(policy)
    db_session.flush()
    db_session.add(CompetitionPolicyRecognition(competition_id=1, university_id=1,
        policy_document_id=policy.id, recognition_status=status, needs_manual_review=manual,
        evidence_text='隔离测试证据', evidence_hash='boundary', recognition_level='测试认定'))
    db_session.commit()
    assert client.get('/api/competition/1/university-recognition').json()['data'] == []
    assert client.get('/api/v0.2/policies/recognitions').json()['data'] == []
    detail = client.get('/api/competitions/1').json()['data']
    assert detail['featured_recognition'] is None
    assert detail['university_inclusion_count'] == 0


def test_profile_free_text_does_not_create_verified_directory_facts(client, db_session):
    headers = login(client)
    response = client.put('/api/users/me/profile', headers=headers, json={
        'university_id': 1, 'college_name': '用户新填测试学院', 'major_name': '用户新填测试专业'})
    assert response.status_code == 200
    assert db_session.scalar(select(College).where(College.name == '用户新填测试学院')) is None
    assert db_session.scalar(select(Major).where(Major.name == '用户新填测试专业')) is None
    profile = client.get('/api/users/me/profile', headers=headers).json()['data']
    assert profile['college_name'] == '用户新填测试学院'
    assert profile['major_name'] == '用户新填测试专业'


def test_unverified_college_is_hidden_from_public_directory(client, db_session):
    db_session.add(College(university_id=1, name='待审测试学院', is_verified=False))
    db_session.commit()
    assert client.get('/api/directory/universities/1/colleges').json()['data'] == []


@pytest.mark.parametrize('year', [2024, 2025, 2026])
def test_update_feed_is_scoped_to_explicit_edition(client, db_session, year):
    rows = editions(db_session)
    for event_year, row in rows.items():
        db_session.add(CompetitionUpdateEvent(competition_id=1, competition_edition_id=row.id,
            event_type='deadline_changed', field_name='official_registration_deadline',
            new_value=str(event_year), source_url=f'https://example.com/{event_year}',
            changed_at=NOW, observed_at=NOW))
    db_session.commit()
    data = client.get(f'/api/competitions/1/updates?edition_id={rows[year].id}').json()['data']
    assert [item['new_value'] for item in data] == [str(year)]
    assert client.get('/api/competitions/1/updates?edition_id=999999').json()['data'] == []


@pytest.mark.parametrize('verified,manual', [(False, False), (True, True)])
def test_public_policy_resolution_ignores_pending_evidence(client, db_session, verified, manual):
    policy = PolicyDocument(university_id=1, title='待核验推免政策',
        source_url='https://example.edu.cn/pending', is_verified=verified)
    db_session.add(policy)
    db_session.flush()
    db_session.add(CompetitionPolicyRecognition(competition_id=1, university_id=1,
        policy_document_id=policy.id, recognition_status='recognized', needs_manual_review=manual,
        evidence_text='候选证据', evidence_hash='pending'))
    db_session.commit()
    data = client.get('/api/v0.2/policies/resolve?competition_id=1&university_id=1').json()['data']
    assert data['effective_status'] != 'recognized'
    assert data['effective_recognition_id'] is None
    if not verified:
        assert client.get('/api/v0.2/policies/documents?include_demo=true').json()['data'] == []
        assert client.get('/api/universities/1/policies').json()['data'] == []


def test_verified_negative_policy_remains_a_fact(client, db_session):
    policy = PolicyDocument(university_id=1, title='明确不认定测试政策',
        source_url='https://example.edu.cn/negative', is_verified=True, verification_status='verified_official')
    db_session.add(policy)
    db_session.flush()
    db_session.add(CompetitionPolicyRecognition(competition_id=1, university_id=1,
        policy_document_id=policy.id, recognition_status='explicitly_not_recognized', needs_manual_review=False,
        evidence_text='明确否定证据', evidence_hash='negative'))
    db_session.commit()
    data = client.get('/api/v0.2/policies/resolve?competition_id=1&university_id=1').json()['data']
    assert data['effective_status'] == 'explicitly_not_recognized'


@pytest.mark.parametrize('status', ['pending_verification', 'suspected', 'unverified'])
def test_unverified_competition_is_hidden_from_public_facts(client, db_session, status):
    row = Competition(name='隔离候选赛事', verification_status=status, is_official_verified=False)
    db_session.add(row)
    db_session.commit()
    assert all(item['id'] != row.id for item in client.get('/api/competitions').json()['data'])
    assert client.get(f'/api/competitions/{row.id}').status_code == 404


def test_approval_api_persists_offset_deadline_and_event_as_utc(client, db_session):
    headers = login(client)
    user = db_session.scalar(select(User).where(User.email == 'edition-boundaries@example.com'))
    user.is_admin = True
    db_session.commit()
    submitted = client.post('/api/users/me/corrections', headers=headers, json={
        'competition_id': 1, 'competition_edition_id': 1, 'correction_type': '报名截止错误',
        'description': '测试官方时区截止', 'source_url': 'https://example.com/updated'})
    correction_id = submitted.json()['data']['id']
    response = client.put(f'/api/admin/review/corrections/{correction_id}', headers=headers,
        json={'status': 'approved', 'new_deadline': '2026-10-06T23:59:59+08:00', 'note': '已核验'})
    assert response.status_code == 409
    field_id = submitted.json()['data']['field_review_id']
    detail = client.get(f'/api/admin/field-reviews/{field_id}', headers=headers).json()['data']
    response = client.put(f'/api/admin/field-reviews/{field_id}/prepare', headers=headers, json={
        'preview_token': detail['preview_token'], 'entity_type': 'edition', 'competition_id': 1,
        'edition_id': 1, 'title': '核验带时区的报名截止',
        'fields': [{'field_name': 'official_registration_deadline', 'candidate_value': '2026-10-06T23:59:59+08:00',
            'source': {'source_type': 'organizer_notice', 'source_url': 'https://example.com/updated'}}],
    })
    assert response.status_code == 200, response.text
    detail = response.json()['data']
    proposal_id = detail['fields'][0]['proposals'][0]['id']
    response = client.post(f'/api/admin/field-reviews/{field_id}/sources/{proposal_id}/verify', headers=headers,
        json={'preview_token': detail['preview_token'], 'note': '已核验原文时区'})
    assert response.status_code == 200, response.text
    detail = response.json()['data']
    response = client.post(f'/api/admin/field-reviews/{field_id}/review', headers=headers, json={
        'preview_token': detail['preview_token'], 'note': '批准官方截止',
        'decisions': [{'field_name': 'official_registration_deadline', 'action': 'approve', 'proposal_id': proposal_id}],
    })
    assert response.status_code == 200, response.text
    expected = datetime(2026, 10, 6, 15, 59, 59, tzinfo=UTC)
    with Session(db_session.bind) as fresh:
        assert fresh.get(CompetitionEdition, 1).official_registration_deadline == expected
        event = fresh.scalar(select(CompetitionUpdateEvent))
        assert datetime.fromisoformat(event.new_value) == expected
    value = client.get('/api/competitions/1?edition_id=1').json()['data']['official_registration_deadline']
    assert datetime.fromisoformat(value) == expected


def test_pending_college_is_hidden_in_university_detail(client, db_session):
    db_session.add(College(university_id=1, name='待审学校详情学院', is_verified=False))
    db_session.commit()
    assert client.get('/api/universities/1').json()['data']['colleges'] == []


def test_legacy_recognition_requires_verified_policy(client, db_session):
    assert client.get('/api/universities/1/competition-policies').json()['data'] == []
    db_session.get(UniversityPolicy, 1).is_verified = True
    db_session.commit()
    assert len(client.get('/api/universities/1/competition-policies').json()['data']) == 1


def test_profile_new_free_text_replaces_prior_directory_association(client, db_session):
    college = College(university_id=1, name='已核验测试学院', is_verified=True)
    major = Major(name='已有测试专业')
    db_session.add_all([college, major])
    db_session.commit()
    headers = login(client)
    client.put('/api/users/me/profile', headers=headers, json={
        'university_id': 1, 'college_id': college.id, 'major_id': major.id})
    response = client.put('/api/users/me/profile', headers=headers, json={
        'university_id': 1, 'college_name': '新填自由学院', 'major_name': '新填自由专业'})
    assert response.status_code == 200
    profile = client.get('/api/users/me/profile', headers=headers).json()['data']
    assert profile['college_id'] is None
    assert profile['major_id'] is None
    assert profile['college_name'] == '新填自由学院'
    assert profile['major_name'] == '新填自由专业'


def test_unverified_edition_dates_never_become_public_or_personal_facts(client, db_session):
    edition = db_session.get(CompetitionEdition, 1)
    edition.is_verified = False
    edition.registration_start = NOW + timedelta(days=2)
    edition.official_registration_deadline = NOW + timedelta(days=20)
    db_session.commit()
    headers = login(client)
    detail = client.get('/api/competitions/1?edition_id=1').json()['data']
    assert detail['current_status'] == 'unknown'
    assert detail['official_registration_deadline'] is None
    assert detail['action_deadline'] is None
    assert detail['editions'] == []
    context = client.get('/api/users/me/competitions/1/context?edition_id=1', headers=headers).json()['data']['item']
    assert context['current_status'] == 'unknown'
    assert context['effective_deadline'] is None
    assert DeadlineResolutionService().resolve_action(edition)[0] is None


def test_newer_unverified_edition_cannot_replace_verified_personal_context(client, db_session):
    db_session.add(CompetitionEdition(competition_id=1, year=2027, is_verified=False,
        official_registration_deadline=datetime(2027, 10, 1, tzinfo=UTC)))
    db_session.commit()
    headers = login(client)
    item = client.get('/api/users/me/competitions/1/context', headers=headers).json()['data']['item']
    assert item['edition_year'] == 2026


@pytest.mark.parametrize('field', ['history_timeline', 'participation_requirements', 'competition_process',
                                    'submission_requirements', 'award_settings'])
def test_pending_structured_field_does_not_become_verified_fact(client, db_session, field):
    competition = db_session.get(Competition, 1)
    confirmed = dict(getattr(competition, field)[0])
    setattr(competition, field, [confirmed, {**confirmed, 'verification_status': 'pending'}])
    db_session.commit()
    data = client.get('/api/competitions/1').json()['data'][field]
    assert len(data) == 1
    assert data[0]['verification_status'] == 'verified_official'


def test_pending_college_recognition_does_not_satisfy_public_filter(client, db_session):
    college = College(university_id=1, name='已核验学院', is_verified=True)
    policy = PolicyDocument(university_id=1, title='学院认定证据',
        source_url='https://example.edu.cn/college-policy', is_verified=True, verification_status='verified_official')
    db_session.add_all([college, policy])
    db_session.flush()
    db_session.add(CompetitionPolicyRecognition(competition_id=1, university_id=1,
        college_id=college.id, policy_document_id=policy.id, recognition_status='recognized',
        needs_manual_review=True, evidence_text='待审记录', evidence_hash='college-pending'))
    db_session.commit()
    assert client.get('/api/competitions?has_college_recognition=true').json()['data'] == []


def test_demo_policy_never_becomes_personal_directory_reason(client, db_session):
    policy = PolicyDocument(university_id=1, title='演示认定政策',
        source_url='https://example.edu.cn/demo-policy', is_verified=True, is_demo=True, verification_status='verified_official')
    db_session.add(policy)
    db_session.flush()
    db_session.add(CompetitionPolicyRecognition(competition_id=1, university_id=1,
        policy_document_id=policy.id, recognition_status='recognized', needs_manual_review=False,
        evidence_text='演示记录', evidence_hash='demo-policy'))
    db_session.commit()
    headers = login(client)
    client.put('/api/users/me/profile', headers=headers, json={'university_id': 1})
    item = client.get('/api/users/me/competitions/1/context', headers=headers).json()['data']['item']
    assert item['school_directory'] is False


@pytest.mark.parametrize('status', ['pending', 'reviewing', 'conflicting'])
def test_explicit_pending_flag_overrides_verified_edition_boolean(client, db_session, status):
    edition = db_session.get(CompetitionEdition, 1)
    edition.verification_status = status
    db_session.commit()
    headers = login(client)
    detail = client.get('/api/competitions/1?edition_id=1').json()['data']
    assert detail['action_deadline'] is None
    assert detail['editions'] == []
    item = client.get('/api/users/me/competitions/1/context?edition_id=1', headers=headers).json()['data']['item']
    assert item['effective_deadline'] is None
    assert DeadlineResolutionService().status(edition) == 'unknown'


@pytest.mark.parametrize('status', ['pending', 'reviewing', 'conflicting'])
def test_explicit_pending_flag_overrides_verified_policy_boolean(client, db_session, status):
    policy = PolicyDocument(university_id=1, title='核验标志冲突测试',
        source_url='https://example.edu.cn/conflict-policy', is_verified=True, verification_status=status)
    db_session.add(policy)
    db_session.flush()
    db_session.add(CompetitionPolicyRecognition(competition_id=1, university_id=1,
        policy_document_id=policy.id, recognition_status='recognized', needs_manual_review=False,
        evidence_text='核验标志冲突', evidence_hash='conflict-policy'))
    db_session.commit()
    assert client.get('/api/competition/1/university-recognition').json()['data'] == []
    assert client.get('/api/v0.2/policies/recognitions').json()['data'] == []
    assert client.get('/api/v0.2/policies/documents').json()['data'] == []
    assert client.get('/api/v0.2/policies/resolve?competition_id=1&university_id=1').json()['data']['effective_status'] != 'recognized'
    headers = login(client)
    client.put('/api/users/me/profile', headers=headers, json={'university_id': 1})
    assert client.get('/api/users/me/competitions/1/context', headers=headers).json()['data']['item']['school_directory'] is False


@pytest.mark.parametrize('status', ['pending', 'reviewing', 'conflicting'])
def test_explicit_pending_flag_overrides_verified_source_boolean(client, db_session, status):
    db_session.get(CompetitionSource, 1).verification_status = status
    db_session.commit()
    assert client.get('/api/competitions/1').json()['data']['sources'] == []
