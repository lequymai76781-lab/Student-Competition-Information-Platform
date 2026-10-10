"""Recovery and governance acceptance at bounded, mid-scale candidate volume."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database.base import Base
from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, University, User, ReviewQueue, CrawlerJob
from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService
from app.services.field_review_service import FieldReviewService as Review
from app.services.mid_scale_ingestion_service import MidScaleIngestionService as Batch, source_quality


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        seed.add_all([Competition(id=1, name='全国样本竞赛', short_name='样本赛', first_held_year=2000),
                      Competition(id=2, name='另一竞赛'),
                      CompetitionEdition(id=1, competition_id=1, year=2024),
                      CompetitionEdition(id=2, competition_id=1, year=2025),
                      User(id=1, username='admin', email='mid@example.test', hashed_password='fixture', is_admin=True)])
        seed.add_all([University(id=i, name=f'样本{i}大学') for i in range(1, 56)])
        seed.commit()
    with SessionLocal(bind=engine) as session:
        yield session
    engine.dispose()


def item(n=1, *, school=None, year=2025, **source_changes):
    source = {'key': f's{n}', 'url': f'https://official.example.test/{n}', 'title': f'通知{n}',
              'publisher': '主办方', 'source_type': 'organizer_notice', 'published_at': None,
              'accessed_at': '2026-09-28T00:00:00+08:00', 'access_status': 'readable',
              'year': year, 'competition_fields': {'description': f'有来源的介绍{n}'},
              'edition_fields': {}, 'evidence_notes': '已阅读原文', 'university_notice': None}
    result = {'kind': 'competition', 'competition_id': 1, 'competition_name': '全国样本竞赛', 'source': source}
    if school:
        result.update(kind='school_mapping', university_name=school, school_source_name=school+'教务处')
        source.update(source_type='university_notice', competition_fields={}, university_notice={
            'university_name': school, 'notice_type': 'registration_notice', 'is_formal_recognition': False})
    source.update(source_changes)
    return result


def count(db):
    return db.scalar(select(func.count()).select_from(ReviewQueue))


def run(db, items, **kwargs):
    job = Batch.create_job(db, items, source='test-manifest')
    return Batch.run(db, job.id, **kwargs)


def test_pause_resume_and_replay_keep_candidates_pending_and_official_unchanged(db):
    job = Batch.create_job(db, [item(1), item(2), item(3)], source='test')
    first = Batch.run(db, job.id, max_items=1)
    assert first['status'] == 'paused' and count(db) == 1
    done = Batch.run(db, job.id)
    assert done['status'] == 'completed' and count(db) == 3
    again = Batch.run(db, job.id)
    assert again['candidates_created'] == 3 and count(db) == 3
    assert db.get(Competition, 1).description is None
    assert set(db.scalars(select(ReviewQueue.status))) == {'pending'}
    assert db.get(CrawlerJob, job.id).finished_at is not None


def test_changed_fetch_time_deduplicates_but_changed_content_creates_new_version(db):
    run(db, [item()])
    changed = item(accessed_at='2026-09-29T00:00:00+08:00')
    assert run(db, [changed])['duplicates_skipped'] == 1
    assert count(db) == 1
    changed['source']['competition_fields']['description'] = '来源内容已更新'
    run(db, [changed])
    assert count(db) == 2


def test_empty_fields_different_sources_are_not_collapsed(db):
    adapter = CompetitionFieldIngestionService()
    for path in ['a', 'b']:
        adapter.stage(db, entity_type='competition', competition_id=1, fields={}, title='相同标题',
                      source={'source_type': 'organizer_notice', 'source_url': f'https://source.example.test/{path}'})
    assert count(db) == 2


def test_failure_rolls_back_candidate_and_retry_does_not_repeat_success(db, monkeypatch):
    original = Batch.stage_item
    def failing(db, value):
        rows = original(db, value)
        if value['source']['key'] == 's2':
            raise ValueError('reproduced failure after candidate creation')
        return rows
    monkeypatch.setattr(Batch, 'stage_item', staticmethod(failing))
    job = Batch.create_job(db, [item(1), item(2)], source='test')
    failed = Batch.run(db, job.id)
    assert failed['status'] == 'completed_with_errors' and failed['failures'] == 1
    assert count(db) == 1
    monkeypatch.setattr(Batch, 'stage_item', staticmethod(original))
    done = Batch.run(db, job.id, retry_failed=True)
    assert done['status'] == 'completed' and count(db) == 2
    assert done['failures'] == 0 and done['attempts'] == 3


def test_crash_rollback_and_expired_lease_recovery(db, monkeypatch):
    original = Batch.stage_item
    def crash(db, value):
        original(db, value)
        raise KeyboardInterrupt()
    job = Batch.create_job(db, [item()], source='test')
    monkeypatch.setattr(Batch, 'stage_item', staticmethod(crash))
    with pytest.raises(KeyboardInterrupt):
        Batch.run(db, job.id)
    db.rollback()
    assert count(db) == 0
    with pytest.raises(ValueError, match='running'):
        Batch.run(db, job.id)
    row = db.get(CrawlerJob, job.id)
    row.metadata_json = {**row.metadata_json, 'lease_until': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    db.commit()
    monkeypatch.setattr(Batch, 'stage_item', staticmethod(original))
    assert Batch.run(db, job.id, recover=True)['status'] == 'completed'
    assert count(db) == 1


@pytest.mark.parametrize('suffix', ['', '（本部）', '教务处', '创新创业学院'])
def test_department_is_not_a_new_university(db, suffix):
    run(db, [item(school='样本1大学'+suffix)])
    row = db.scalar(select(ReviewQueue))
    assert row.university_id == 1
    assert db.scalar(select(func.count()).select_from(University)) == 55
    d = Review.detail(db, row)
    assert d['collection_context']['school_name'] == '样本1大学'
    assert d['collection_context']['notice_type'] == 'registration_notice'
    assert d['collection_context']['is_formal_recognition'] is False
    assert d['fields'] == []


def test_similar_unknown_university_is_not_guessed(db):
    run(db, [item(school='样本1大学附属学院')])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert d['university_id'] is None
    assert 'DUPLICATE_SUSPECTED' in d['flags']


def test_uncertain_edition_not_inferred_from_publication_or_existing_latest(db):
    run(db, [item(school='样本1大学', year=None, published_at='2025-03-01')])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert d['collection_context']['edition_status'] == 'edition_uncertain'
    assert d['collection_context']['edition_id'] is None
    assert 'edition_uncertain' in d['flags']


def test_same_school_distinct_years_and_many_schools_same_contest(db):
    run(db, [item(1, school='样本1大学', year=2024), item(2, school='样本1大学', year=2025), item(3, school='样本2大学')])
    docs = [Review.detail(db, r) for r in db.scalars(select(ReviewQueue).order_by(ReviewQueue.id))]
    assert [d['collection_context']['edition_id'] for d in docs] == [1, 2, 2]
    assert db.scalar(select(func.count()).select_from(Competition)) == 2
    assert db.scalar(select(func.count()).select_from(CompetitionEdition)) == 2


def test_false_recognition_rejected_and_real_policy_kept_pending(db):
    invalid = item(school='样本1大学')
    invalid['source']['university_notice']['is_formal_recognition'] = True
    assert run(db, [invalid])['failures'] == 1
    assert count(db) == 0
    valid = item(2, school='样本1大学', source_type='university_policy')
    valid['source']['university_notice'].update(notice_type='policy_recognition', is_formal_recognition=True,
                                               recognition_evidence='学校正式目录第1项：全国样本竞赛')
    run(db, [valid])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert d['collection_context']['is_formal_recognition'] and d['status'] == 'pending'
    assert d['collection_context']['source_quality'] == 'B'
    # Mapping evidence must not be converted into general competition fields.
    with pytest.raises(HTTPException) as e:
        Review.prepare(db, d['id'], {'entity_type':'competition', 'competition_id':1, 'title':'误转赛事',
            'preview_token':d['preview_token'], 'fields':[{'field_name':'description', 'candidate_value':'不合法'}]}, admin=db.get(User,1))
    assert e.value.status_code == 409


@pytest.mark.parametrize('reason', ['404','timeout','ssl_error','blocked','requires_js','requires_login','captcha','removed','unknown'])
def test_failed_sources_retained_without_proposed_facts(db, reason):
    result = run(db, [item(access_status='blocked', source_failure_reason=reason)])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert d['fields'] == [] and d['origin_source_url']
    assert d['collection_context']['source_failure_reason'] == reason
    assert result['source_failures'] == 1


def test_wrong_competition_id_is_quarantined(db):
    value = item(); value['competition_id'] = 2
    run(db, [value])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert 'DUPLICATE_SUSPECTED' in d['flags'] and d['fields'] == []


def test_more_than_100_candidates_50_schools_and_bounded_page_details(db, monkeypatch):
    items = [item(n, school=f'样本{n%55+1}大学') for n in range(111)]
    run(db, items)
    assert count(db) == 111
    calls = []
    original = Review.detail
    def detail(db, row):
        calls.append(row.id if hasattr(row, 'id') else row)
        return original(db, row)
    monkeypatch.setattr(Review, 'detail', staticmethod(detail))
    page = Review.list_candidates(db, limit=10, offset=100)
    assert page['total'] == 111 and len(page['items']) == 10
    assert len(calls) == 10
    filtered = Review.list_candidates(db, source_type='university_notice', university_id=1, limit=50)
    assert filtered['total'] == 3


def test_conflict_filter_stays_correct_after_pagination_optimization(db):
    run(db, [item(1), item(2), item(3)])
    d = Review.list_candidates(db, flag='CONFLICT', limit=1, offset=1)
    assert d['total'] == 3 and len(d['items']) == 1
    assert 'CONFLICT' in d['items'][0]['flags']


@pytest.mark.parametrize('kind,grade', [('official_website','A'),('government_document','A'),('organizer_notice','A'),
    ('university_notice','B'),('university_policy','B'),('industry_organization','C'),('third_party','D'),('ai_assisted','E')])
def test_quality_is_a_sorting_hint_only(kind, grade):
    assert source_quality(kind) == grade


def test_partial_rerun_and_unknown_keys(db):
    job = Batch.create_job(db, [item(1),item(2)], source='test')
    result = Batch.run(db, job.id)
    key = next(iter(result['items']))
    rerun = Batch.run(db, job.id, item_keys=[key])
    assert rerun['attempts'] == 3 and count(db) == 2
    with pytest.raises(ValueError, match='Unknown'):
        Batch.run(db, job.id, item_keys=['nonexistent'])


def test_source_fetch_checkpoints_resume_and_failed_links_can_be_retried(db):
    calls = []
    def probe(url):
        calls.append(url)
        return {'status_code': None, 'source_failure_reason': 'timeout', 'fetched_at': '2026-09-28T00:00:00Z'}
    job = Batch.create_job(db, [item(1),item(2)], source='test')
    first = Batch.run(db, job.id, max_items=1, probe=probe)
    assert len(calls) == 1 and first['status'] == 'paused'
    resumed = Batch.run(db, job.id, probe=probe)
    assert len(calls) == 2 and resumed['source_failures'] == 2
    def recovered(url):
        calls.append(url)
        return {'status_code': 200, 'source_failure_reason': None, 'fetched_at': '2026-09-28T00:01:00Z'}
    done = Batch.run(db, job.id, retry_failed=True, probe=recovered)
    assert len(calls) == 4 and done['source_failures'] == 0
    for entry in done['items'].values():
        assert [h['source_failure_reason'] for h in entry['attempt_history']] == ['timeout', None]
    assert count(db) == 2 and all(r.status == 'pending' for r in db.scalars(select(ReviewQueue)))


def test_duplicate_edition_is_rejected_by_existing_schema(db):
    with Session(db.bind) as seed:
        seed.add(CompetitionEdition(competition_id=1,year=2025))
        with pytest.raises(IntegrityError):
            seed.commit()
    run(db, [item(school='样本1大学')])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert d['collection_context']['edition_id'] == 2
    assert db.scalar(select(func.count()).select_from(CompetitionEdition)) == 2


@pytest.mark.parametrize('late_error', [False, True])
def test_expired_worker_cannot_overwrite_recovered_checkpoint(db, monkeypatch, late_error):
    import app.services.mid_scale_ingestion_service as module
    job = Batch.create_job(db, [item()], source='lease-test')
    start = module._now()
    def takeover(url):
        monkeypatch.setattr(module, '_now', lambda: start+timedelta(minutes=3))
        with SessionLocal(bind=db.bind) as second:
            completed = Batch.run(second, job.id, recover=True)
            assert completed['candidates_created'] == 1
        if late_error:
            raise ValueError('late error from expired worker')
        return {'status_code': 200, 'source_failure_reason': None}
    with pytest.raises(ValueError, match='lease'):
        Batch.run(db, job.id, probe=takeover)
    db.rollback()
    result = Batch.summary(db, job.id)
    assert result['status'] == 'completed' and result['candidates_created'] == count(db) == 1
    assert next(iter(result['items'].values()))['candidate_ids']


def test_manifest_local_source_key_does_not_duplicate_same_evidence(db):
    run(db, [item()])
    renamed = item(key='renamed-local-label')
    assert run(db, [renamed])['duplicates_skipped'] == 1
    assert count(db) == 1


def test_new_collection_jobs_do_not_leak_through_public_policy_jobs(db):
    from app.services.policy_data_service import PolicyDataService
    db.add(CrawlerJob(job_type='university_policy', target_type='university', target_name='公开任务'))
    db.commit()
    Batch.create_job(db, [item()], source='PRIVATE_MANIFEST_PATH')
    jobs = PolicyDataService().list_jobs(db, limit=1, offset=0)
    assert len(jobs) == 1 and jobs[0].target_name == '公开任务'


def test_founding_year_is_only_identity_hint_not_automatic_merge(db):
    value = item(competition_fields={'first_held_year': 2000})
    value['competition_name'] = '未经确认的新名字'
    run(db, [value])
    d = Review.detail(db, db.scalar(select(ReviewQueue)))
    assert d['collection_context']['identity_check']['first_held_year_ids'] == [1]
    assert d['competition_id'] is None and 'DUPLICATE_SUSPECTED' in d['flags']
