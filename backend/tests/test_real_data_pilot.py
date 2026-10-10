"""Pilot ingestion/review acceptance; every database is isolated and guarded."""
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, CompetitionAlias, User, ReviewQueue
from app.services.field_review_service import FieldReviewService as Review
from app.services.real_data_pilot_service import RealDataPilotService as Pilot


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        seed.add_all([
            Competition(id=1, name='全国大学生广告艺术大赛', short_name='大广赛',
                        english_name='Advertising Art Competition', former_names=['旧赛事名'],
                        organizer='原主办方', official_website='https://contest.example.test'),
            Competition(id=2, name='其他比赛', organizer='其他主办方'),
            CompetitionEdition(id=1, competition_id=1, year=2025, edition_name='第17届大广赛'),
            CompetitionAlias(competition_id=1, alias='大广', normalized_alias='大广', confidence=1, is_verified=True),
            User(id=1, email='pilot@example.test', username='pilot', hashed_password='fixture', is_admin=True),
        ])
        seed.commit()
    with SessionLocal(bind=engine) as session:
        yield session
    engine.dispose()


def source(key='a', **changes):
    value = {'key': key, 'url': f'https://contest.example.test/{key}', 'title': '大赛通知',
             'publisher': '组委会', 'source_type': 'organizer_notice', 'published_at': '2025-03-01',
             'accessed_at': '2026-09-27T09:00:00+08:00', 'access_status': 'readable', 'year': 2025,
             'competition_fields': {'short_name': '大广赛'},
             'edition_fields': {'official_registration_deadline': '2025-06-01T18:00:00+08:00'},
             'evidence_notes': '日期来源于正文', 'university_notice': None}
    value.update(changes)
    return value


def sample(*sources, **changes):
    value = {'competition_id': 1, 'name': '全国大学生广告艺术大赛', 'aliases': [],
             'reason': '多来源', 'sources': list(sources or [source()])}
    value.update(changes)
    return value


def details(db, value):
    return [Review.detail(db, row) for row in Pilot().stage_sample(db, value)]


def approve(db, detail, field_name):
    admin = db.get(User, 1)
    field = next(f for f in detail['fields'] if f['field_name'] == field_name)
    proposal = field['proposals'][0]
    checked = Review.verify_source(db, detail['id'], proposal['id'],
                                  {'preview_token': detail['preview_token'], 'note': '核对原文'}, admin=admin)
    return Review.review(db, detail['id'], {'preview_token': checked['preview_token'], 'note': '人工确认',
        'decisions': [{'field_name': field_name, 'action': 'approve', 'proposal_id': proposal['id']}]}, admin=admin)


def test_official_enters_unverified_candidate(db):
    result = details(db, sample())
    assert all(r['status'] == 'pending' and 'UNVERIFIED' in r['flags'] for r in result)


def test_university_notice_keeps_scope_without_recognition(db):
    notice = {'university_name': '样本大学', 'notice_type': 'registration_notice',
              'is_formal_recognition': False, 'school_deadline': '2025-05-15'}
    result = details(db, sample(source(source_type='university_notice', university_notice=notice)))
    assert all('registration_notice' in r['description'] for r in result)
    assert all(f['field_name'] != 'university_registration_deadline' for r in result for f in r['fields'])


def test_multiple_sources_remain_separate(db):
    result = details(db, sample(source(), source('b')))
    assert len(result) == 4
    assert {f['source_url'] for r in result for f in r['fields']} == {'https://contest.example.test/a', 'https://contest.example.test/b'}


def test_conflicting_values_and_extension_are_preserved(db):
    details(db, sample(source(), source('extension', published_at='2025-05-30',
        edition_fields={'official_registration_deadline': '2025-06-15T18:00:00+08:00'})))
    result = Review.list_candidates(db)['items']
    editions = [r for r in result if r['entity_type'] == 'edition']
    assert all('CONFLICT' in r['flags'] for r in editions)
    assert all(Review.detail(db, r['id'])['fields'][0]['conflicts'][0]['source']['published_at'] for r in editions)
    assert db.get(CompetitionEdition, 1).official_registration_deadline is None


def test_years_never_cross(db):
    result = details(db, sample(source(), source('next', year=2026)))
    new = next(r for r in result if r['year'] == 2026)
    approve(db, new, 'official_registration_deadline')
    assert db.get(CompetitionEdition, 1).official_registration_deadline is None
    assert db.scalar(select(func.count()).select_from(CompetitionEdition)) == 2


@pytest.mark.parametrize('name', ['大广赛', '大广', '旧赛事名', 'Advertising Art Competition', '第17届大广赛'])
def test_aliases_resolve_existing_competition(db, name):
    result = details(db, sample(name=name, competition_id=None))
    assert all(r['competition_id'] == 1 for r in result)
    assert db.scalar(select(func.count()).select_from(Competition)) == 2


def test_same_year_multiple_sources_and_rerun_do_not_duplicate(db):
    value = sample(source(year=2026), source('b', year=2026))
    first = details(db, value)
    assert [r['id'] for r in first] == [r['id'] for r in details(db, value)]
    for r in first:
        if r['entity_type'] == 'edition':
            approve(db, Review.detail(db, r['id']), 'official_registration_deadline')
    assert db.scalar(select(func.count()).select_from(CompetitionEdition).where(CompetitionEdition.year == 2026)) == 1


def test_notice_cannot_claim_formal_recognition(db):
    with pytest.raises(ValueError, match='recognition'):
        details(db, sample(source(university_notice={'notice_type': 'registration_notice', 'is_formal_recognition': True})))


def test_missing_source_cannot_be_approved(db):
    result = Review.create_candidate(db, {'entity_type': 'competition', 'competition_id': 1,
        'title': '无来源负例', 'fields': [{'field_name': 'first_held_year', 'candidate_value': 1999}]})
    detail = Review.detail(db, result)
    assert 'NO_SOURCE' in detail['flags']
    with pytest.raises(HTTPException):
        approve(db, detail, 'first_held_year')
    assert db.get(Competition, 1).first_held_year is None


def test_missing_history_is_not_inferred_from_edition_number(db):
    result = details(db, sample(source(edition_fields={'edition_number': 17})))
    assert not any(f['field_name'] in {'first_held_year', 'founded_year'} for r in result for f in r['fields'])


def test_source_url_survives_unstructured_candidate(db):
    result = details(db, sample(source(competition_fields={}, edition_fields={}, access_status='blocked')))
    assert len(result) == 1 and not result[0]['fields']
    assert result[0]['origin_source_url'] == 'https://contest.example.test/a'


def test_candidate_does_not_change_official_until_review(db):
    result = details(db, sample(source(competition_fields={'organizer': '新主办方'})))
    db.commit()
    assert db.get(Competition, 1).organizer == '原主办方'
    approve(db, result[0], 'organizer')
    db.commit()
    assert db.get(Competition, 1).organizer == '新主办方'


def test_partial_review_leaves_other_fields_pending(db):
    result = details(db, sample(source(competition_fields={'organizer': '新主办方', 'short_name': '简称'})))
    reviewed = approve(db, result[0], 'short_name')
    assert reviewed['status'] == 'partially_approved'
    assert db.get(Competition, 1).organizer == '原主办方'


def test_conflict_is_not_auto_resolved_by_later_import(db):
    details(db, sample(source(competition_fields={'organizer': '甲'}), source('b', competition_fields={'organizer': '乙'})))
    db.commit()
    assert db.get(Competition, 1).organizer == '原主办方'
    assert sum('CONFLICT' in r['flags'] for r in Review.list_candidates(db)['items']) == 2


def test_website_and_organizer_only_match_is_quarantined(db):
    result = details(db, sample(name='名称无法确认', competition_id=None,
        sources=[source(competition_fields={'official_website': 'https://contest.example.test/', 'organizer': '原主办方'})]))
    assert result[0]['competition_id'] is None and not result[0]['fields']
    assert 'DUPLICATE_SUSPECTED' in result[0]['title']
    assert 'website_ids' in result[0]['description'] and 'organizer_ids' in result[0]['description']


def test_explicit_wrong_id_does_not_override_name_match(db):
    result = details(db, sample(competition_id=2))
    assert not result[0]['fields'] and 'DUPLICATE_SUSPECTED' in result[0]['title']


def test_unreviewed_session_is_rejected(db):
    with Session(db.bind) as unguarded:
        with pytest.raises(ValueError, match='guarded'):
            Pilot().stage_sample(unguarded, sample())


def test_real_manifest_contract_and_scope():
    from app.services.field_review_service import validate_candidate_value
    from app.services.real_data_pilot_service import NOTICE_TYPES
    root = Path(__file__).resolve().parents[2]
    samples = []
    for group in 'abc':
        samples.extend(json.loads((root / f'docs/real-data-pilot/sources-{group}.json').read_text(encoding='utf-8-sig')))
    assert len(samples) == len({s['competition_id'] for s in samples}) == 24
    keys = set()
    for item in samples:
        assert any(s['access_status'] == 'readable' for s in item['sources'])
        for s in item['sources']:
            assert s['key'] not in keys
            keys.add(s['key'])
            assert s['url'].startswith(('http://', 'https://')) and s['accessed_at']
            if s['access_status'] != 'readable':
                assert not s['competition_fields'] and not s['edition_fields']
            if s['edition_fields']:
                assert type(s['year']) is int
            for kind in ('competition', 'edition'):
                for name, value in s[f'{kind}_fields'].items():
                    validate_candidate_value(kind, name, value)
            n = s.get('university_notice')
            if n:
                assert n['notice_type'] in NOTICE_TYPES
                if n['is_formal_recognition']:
                    assert s['source_type'] == 'university_policy' and n.get('recognition_evidence')
