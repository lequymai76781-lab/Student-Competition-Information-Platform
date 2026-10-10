"""Bounded, restartable candidate staging using existing crawler_jobs.

One source and its checkpoint commit together. No official entity is created,
no source is verified, and no candidate is approved by this service.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4
import httpx

from sqlalchemy import select, update

from app.database.review_guard import is_review_guarded
from app.models import CrawlerJob, CompetitionEdition, ReviewQueue, University
from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService
from app.services.real_data_pilot_service import RealDataPilotService, _name, _published


NOTICE_TYPES = {'registration_notice', 'organization_notice', 'selection_notice',
                'recommendation_notice', 'policy_recognition', 'award_policy', 'repost', 'other',
                'competition_notice'}  # last value retained for the earlier pilot
FAILURE_REASONS = {'404', '403', 'timeout', 'ssl_error', 'blocked', 'requires_js',
                   'requires_login', 'captcha', 'removed', 'unknown'}
MAX_ITEMS = 500


def _now():
    return datetime.now(timezone.utc)


def _canonical(value):
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()
                if k not in {'key', 'accessed_at', 'collected_at', 'fetched_at'}}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def item_key(item):
    return hashlib.sha256(json.dumps(_canonical(item), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source_quality(kind):
    return {'official_website': 'A', 'organizer_notice': 'A', 'government_document': 'A',
            'university_notice': 'B', 'university_policy': 'B', 'industry_organization': 'C',
            'third_party': 'D'}.get(kind, 'E')


def probe_source(url):
    """One bounded public-source GET; no crawling, login, or verification.

    Limit response consumption to 1 MiB. Availability is independent of the
    evidence previously read with research tools; a 200 never approves facts.
    """
    from app.schemas.field_review import FieldSourceIn
    FieldSourceIn.model_validate({'source_type': 'crawler', 'source_url': url})
    result = {'fetched_at': _now().isoformat(), 'status_code': None,
              'source_failure_reason': None, 'url': url}
    try:
        with httpx.stream('GET', url, timeout=4.0, follow_redirects=True,
                          headers={'User-Agent': 'StudentCompetitionSourceCheck/1.0'}) as response:
            result.update(status_code=response.status_code, final_url=str(response.url),
                          content_type=response.headers.get('content-type'))
            if response.status_code >= 400:
                result['source_failure_reason'] = {403:'403', 404:'404', 401:'requires_login', 410:'removed',
                                                   429:'blocked'}.get(response.status_code, 'unknown')
            digest, size = hashlib.sha256(), 0
            for chunk in response.iter_bytes(chunk_size=65536):
                digest.update(chunk); size += len(chunk)
                if size >= 1024*1024:
                    result['body_truncated'] = True
                    break
            result.update(bytes_read=size, body_sample_sha256=digest.hexdigest())
    except httpx.TimeoutException:
        result['source_failure_reason'] = 'timeout'
    except httpx.HTTPError as error:
        result['source_failure_reason'] = 'ssl_error' if 'CERTIFICATE' in str(error).upper() else 'unknown'
        result['error_type'] = type(error).__name__
    return result


def school_identity(db, value):
    # Strip only known organizational suffixes; never substring-match schools.
    normalized = _name(value)
    suffixes = ('本部', '教务处', '创新创业学院', '团委', '学生工作部', '研究生院')
    queries = {normalized}
    for suffix in suffixes:
        if normalized.endswith(suffix):
            queries.add(normalized[:-len(suffix)])
    matches = [r for r in db.scalars(select(University))
               if queries & {_name(n) for n in [r.name, r.short_name, *(r.aliases or [])] if n}]
    return matches[0] if len(matches) == 1 else None


def _checkpoint(db, job_id, owner, **values):
    claimed = db.execute(update(CrawlerJob).where(CrawlerJob.id == job_id,
        CrawlerJob.status == 'running', CrawlerJob.metadata_json['lease_owner'].as_string() == owner).values(**values))
    if claimed.rowcount != 1:
        db.rollback()
        raise ValueError('Job lease changed; stale worker cannot persist candidates or checkpoints')
    db.commit()


class MidScaleIngestionService:
    @staticmethod
    def create_job(db, items, *, source):
        if not is_review_guarded(db):
            raise ValueError('Batch requires the runtime guarded session')
        if not 1 <= len(items) <= MAX_ITEMS:
            raise ValueError('Bounded batch requires 1–500 source items')
        unique = {item_key(item): deepcopy(item) for item in items}
        job = CrawlerJob(job_type='mid_scale_candidate', target_type='source_manifest', target_name=str(source)[:255],
            status='pending', pages_discovered=len(unique), metadata_json={
                'schema_version': 1, 'source': source, 'items_found': len(items),
                'duplicate_inputs': len(items)-len(unique), 'items': {
                    key: {'input': item, 'status': 'pending', 'attempts': 0, 'candidate_ids': [],
                          'candidates_created': 0, 'duplicates_skipped': 0}
                    for key, item in unique.items()}})
        db.add(job)
        db.commit()
        return job

    @staticmethod
    def summary(db, job_id):
        job = db.get(CrawlerJob, job_id, populate_existing=True)
        if job is None or job.job_type != 'mid_scale_candidate':
            raise ValueError('Unknown mid-scale job')
        meta = job.metadata_json
        entries = list(meta['items'].values())
        return {'job_id': job.id, 'source': meta['source'], 'target_type': job.target_type,
                'target_id': job.target_id, 'started_at': job.started_at.isoformat() if job.started_at else None,
                'finished_at': job.finished_at.isoformat() if job.finished_at else None, 'status': job.status,
                'items_found': meta['items_found'], 'items_processed': sum(e['status'] == 'completed' for e in entries),
                'candidates_created': sum(e['candidates_created'] for e in entries),
                'duplicates_skipped': meta['duplicate_inputs'] + sum(e['duplicates_skipped'] for e in entries),
                'failures': sum(e['status'] == 'failed' for e in entries),
                'source_failures': sum(bool(e.get('source_failure_reason')) for e in entries),
                'attempts': sum(e['attempts'] for e in entries), 'error_summary': job.error_summary,
                'items': deepcopy(meta['items'])}

    @staticmethod
    def run(db, job_id, *, max_items=None, retry_failed=False, item_keys=None, recover=False, probe=None):
        """Owns transactions; caller must pass a clean dedicated session.

        Hard exits retain a running lease. Recovery is explicit and only possible
        once the lease expires; ordinary reruns cannot steal an active job.
        """
        if not is_review_guarded(db):
            raise ValueError('Batch requires the runtime guarded session')
        if max_items is not None and max_items < 1:
            raise ValueError('max_items must be positive')
        job = db.get(CrawlerJob, job_id, populate_existing=True)
        if job is None or job.job_type != 'mid_scale_candidate':
            raise ValueError('Unknown mid-scale job')
        meta = deepcopy(job.metadata_json)
        if item_keys is not None and set(item_keys)-set(meta['items']):
            raise ValueError('Unknown item key')
        old_status, old_meta = job.status, deepcopy(job.metadata_json)
        if old_status == 'running':
            expires = datetime.fromisoformat(meta['lease_until'])
            if not recover or expires > _now():
                raise ValueError('Job is running; expired lease requires explicit recovery')
        token = uuid4().hex
        meta.update(lease_owner=token, lease_until=(_now()+timedelta(minutes=2)).isoformat())
        # JSON equality includes the owner so a concurrent recovery cannot steal
        # the same expired lease twice.
        claimed = db.execute(update(CrawlerJob).where(CrawlerJob.id == job.id,
            CrawlerJob.status == old_status, CrawlerJob.metadata_json == old_meta).values(
                status='running', metadata_json=meta, started_at=job.started_at or _now(), finished_at=None))
        if claimed.rowcount != 1:
            db.rollback()
            raise ValueError('Job is running in another worker')
        db.commit()
        selected = [key for key, entry in meta['items'].items() if
                    (item_keys is not None and key in item_keys) or
                    (item_keys is None and (entry['status'] == 'pending' or retry_failed and
                        (entry['status'] == 'failed' or entry.get('source_failure_reason'))))]
        for key in selected[:max_items]:
            job = db.get(CrawlerJob, job_id, populate_existing=True)
            meta = deepcopy(job.metadata_json)
            if meta.get('lease_owner') != token:
                raise ValueError('Job lease changed')
            entry = meta['items'][key]
            if 'attempt_history' not in entry:
                entry['attempt_history'] = ([{k: deepcopy(entry.get(k)) for k in
                    ('attempts', 'status', 'started_at', 'finished_at', 'error', 'source_failure_reason', 'fetch_result')}]
                    if entry['attempts'] else [])
            entry['attempts'] += 1
            entry['started_at'] = _now().isoformat()
            attempt_fetch = None
            try:
                if probe:
                    attempt_fetch = probe(entry['input']['source']['url'])
                    entry['fetch_result'] = attempt_fetch
                # An explicit outer BEGIN is required for SQLite's legacy
                # SAVEPOINT behavior; candidate adapters may use savepoints.
                connection = db.connection()
                if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
                    connection.exec_driver_sql('BEGIN')
                before = set(db.scalars(select(ReviewQueue.id)))
                rows = MidScaleIngestionService.stage_item(db, entry['input'])
                db.flush()
                ids = sorted({r.id for r in rows})
                created = len(set(ids)-before)
                entry.update(status='completed', candidate_ids=ids, error=None,
                    source_failure_reason=entry['fetch_result'].get('source_failure_reason') if probe else
                        entry['input']['source'].get('source_failure_reason') or
                        ('unknown' if entry['input']['source'].get('access_status') != 'readable' else None))
                entry['candidates_created'] += created
                entry['duplicates_skipped'] += len(ids)-created
            except Exception as error:
                db.rollback()
                job = db.get(CrawlerJob, job_id, populate_existing=True)
                # Discard all attempted candidates, persist only failed attempt.
                entry.update(status='failed', error=f'{type(error).__name__}: {error}'[:1000])
            entry['finished_at'] = _now().isoformat()
            entry['attempt_history'].append({k: deepcopy(entry.get(k)) for k in
                ('attempts', 'status', 'started_at', 'finished_at', 'error', 'source_failure_reason')})
            entry['attempt_history'][-1]['fetch_result'] = attempt_fetch
            meta.update(lease_until=(_now()+timedelta(minutes=2)).isoformat())
            _checkpoint(db, job_id, token, metadata_json=meta)  # candidates + checkpoint, only current owner
        job = db.get(CrawlerJob, job_id, populate_existing=True)
        meta = deepcopy(job.metadata_json)
        pending = any(e['status'] == 'pending' for e in meta['items'].values())
        errors = [e['error'] for e in meta['items'].values() if e['status'] == 'failed']
        meta.pop('lease_owner', None); meta.pop('lease_until', None)
        _checkpoint(db, job_id, token, metadata_json=meta,
            status='paused' if pending else 'completed_with_errors' if errors else 'completed',
            finished_at=None if pending else _now(),
            pages_fetched=sum(e['status'] == 'completed' for e in meta['items'].values()),
            documents_found=len(meta['items']),
            documents_parsed=sum(e['status'] == 'completed' and e['input']['source'].get('access_status') == 'readable'
                                 for e in meta['items'].values()),
            competitions_found=len({e['input'].get('competition_id') for e in meta['items'].values()} - {None}),
            errors_count=len(errors), error_summary='\n'.join(errors[:10]) or None)
        return MidScaleIngestionService.summary(db, job_id)

    @staticmethod
    def stage_item(db, item):
        if not is_review_guarded(db):
            raise ValueError('Batch requires the runtime guarded session')
        # Timestamp-only recollection should not reopen previous work. Preserve
        # the original first observation in the candidate; jobs retain retries.
        key = item_key(item)
        existing = list(db.scalars(select(ReviewQueue).where(
            ReviewQueue.item_type == 'field_candidate', ReviewQueue.raw_value.contains('mid_scale_source:' + key))))
        if existing:
            return existing
        source = deepcopy(item['source'])
        if source.get('access_status') not in {'readable', 'blocked', 'unavailable'}:
            raise ValueError('Unknown source access status')
        failure = source.get('source_failure_reason')
        if failure and failure not in FAILURE_REASONS:
            raise ValueError('Unknown source failure reason')
        if not source.get('url') or not source.get('accessed_at'):
            raise ValueError('Source URL and observation timestamp required')
        sample = {'competition_id': item.get('competition_id'), 'name': item.get('competition_name') or '',
                  'sources': [source], 'aliases': []}
        competition, identity = RealDataPilotService().identity(db, sample)
        context = {'kind': item['kind'], 'source_quality': source_quality(source['source_type']),
                   'source_type': source['source_type'], 'source_failure_reason': failure or
                        ('unknown' if source['access_status'] != 'readable' else None),
                   'source_url': source['url'], 'source_title': source['title'], 'publisher': source['publisher'],
                   'access_status': source['access_status'], 'accessed_at': source['accessed_at'],
                   'published_at': source.get('published_at'), 'identity_check': identity,
                   'evidence_notes': source.get('evidence_notes'), 'source_key': key,
                   'flags': ['DUPLICATE_SUSPECTED'] if competition is None and item.get('competition_name') else []}
        if item['kind'] == 'competition':
            if source_quality(source['source_type']) != 'A':
                # Non-primary sources are clues, not the competition backbone.
                source['competition_fields'], source['edition_fields'] = {}, {}
            rows = RealDataPilotService().stage_sample(db, sample)
        elif item['kind'] == 'school_mapping':
            notice = source.get('university_notice') or {}
            kind = notice.get('notice_type')
            if kind not in NOTICE_TYPES:
                raise ValueError('Unknown school notice type')
            recognition = notice.get('is_formal_recognition', False)
            if recognition and (source['source_type'] != 'university_policy'
                    or kind not in {'policy_recognition', 'award_policy'}
                    or not notice.get('recognition_evidence') or competition is None
                    or source['access_status'] != 'readable'):
                raise ValueError('Recognition needs readable, explicit competition policy evidence')
            school = school_identity(db, item['university_name'])
            year = source.get('year')
            if year is not None and (type(year) is not int or not 1900 <= year <= 2200):
                raise ValueError('Invalid edition year')
            editions = list(db.scalars(select(CompetitionEdition).where(CompetitionEdition.competition_id == competition.id,
                CompetitionEdition.year == year))) if year is not None and competition is not None else []
            uncertain = year is None or competition is None
            context.update(school_name=school.name if school else item['university_name'],
                school_source_name=item.get('school_source_name'), university_id=school.id if school else None,
                notice_type=kind, is_formal_recognition=recognition,
                recognition_evidence=notice.get('recognition_evidence'), school_deadline=notice.get('school_deadline'),
                year=year, edition_id=editions[0].id if len(editions) == 1 else None,
                edition_status='edition_uncertain' if uncertain else 'duplicate' if len(editions)>1 else
                    'existing' if editions else 'year_known_pending_edition')
            if uncertain:
                context['flags'].append('edition_uncertain')
            if school is None or len(editions)>1:
                context['flags'].append('DUPLICATE_SUSPECTED')
            rows = [CompetitionFieldIngestionService().stage(db, entity_type='competition', fields={},
                title=f"学校材料 · {context['school_name']} · {kind} · {source['title']}",
                competition_id=competition.id if competition else None, university_id=school.id if school else None,
                producer='mid_scale_school_mapping', raw={'source': source, 'mapping': context}, source={
                    'source_type': source['source_type'], 'source_url': source['url'], 'source_title': source['title'],
                    'publisher': source['publisher'], 'published_at': _published(source.get('published_at'))})]
        else:
            raise ValueError('Unknown item kind')
        for row in rows:
            doc = json.loads(row.raw_value)
            doc['collection_context'] = context
            doc['collection_key'] = 'mid_scale_source:' + key
            row.raw_value = json.dumps(doc, ensure_ascii=False)
            from app.services.document_policy_service import DocumentPolicyService
            DocumentPolicyService.classify_candidate(db, row.id)
        db.flush()
        return rows
