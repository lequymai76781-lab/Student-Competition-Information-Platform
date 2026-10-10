"""Read-only bridge from business review evidence to an isolated learning ledger.

The predictor receives allowlisted source content, never old human answers.
The learning store never receives a business Session or a write capability.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import AdminAuditLog, Competition, ReviewQueue, University
from app.services.document_policy_service import candidate_document, candidate_source, require_admin

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
AUDIT_ACTIONS = {'field_review', 'field_reject_unstructured', 'school_relation_review'}
SOURCE_KEYS = {'title', 'source_title', 'source_url', 'url', 'publisher', 'section', 'source_type',
    'content_preview', 'content_text', 'content', 'body', 'text', 'attachment_title', 'attachment_titles',
    'content_is_complete', 'content_truncated', 'published_at', 'collected_at', 'evidence_notes'}
PRIMARY = {'participation', 'result', 'information', 'policy', 'update', 'repost', 'other'}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_content_hash(features):
    """Original evidence remains fixed while humans may prepare review fields."""
    return canonical_hash({'source': features['source'], 'source_id': features.get('source_id')})


def _has_preparation(db, candidate_id, after_id=0):
    return db.scalar(select(AdminAuditLog.id).where(AdminAuditLog.object_type == 'field_candidate',
        AdminAuditLog.object_id == candidate_id, AdminAuditLog.id > after_id,
        AdminAuditLog.action.in_({'field_prepare','school_relation_prepare','field_review'})).limit(1)) is not None


def _source(value):
    clean = {key: deepcopy(item) for key, item in (value or {}).items() if key in SOURCE_KEYS}
    attachments = (value or {}).get('attachments')
    if isinstance(attachments, list):
        clean['attachments'] = [{k: a[k] for k in ('title', 'name', 'url', 'content_text') if k in a}
            if isinstance(a, dict) else str(a) for a in attachments]
    return clean


def candidate_features(db, candidate_id):
    row = db.get(ReviewQueue, candidate_id)
    if row is None or row.item_type != 'field_candidate':
        raise HTTPException(404, '审核候选不存在')
    doc = candidate_document(row)
    source = _source(candidate_source(doc, row))
    description = doc.get('description') or ''
    if description and not description.startswith('ingestion_sha256:') and not source.get('content_text'):
        source['content_text'] = description
    context = doc.get('collection_context') or {}
    comp = db.get(Competition, row.competition_id) if row.competition_id else None
    school = db.get(University, row.university_id) if row.university_id else None
    source_id = context.get('source_id') or canonical_hash({'url': source.get('source_url'), 'title': source.get('title')})[:16]
    return {'candidate_id': row.id, 'source_id': source_id,
        'title': source.get('title') or doc.get('title'), 'publisher': source.get('publisher'),
        'school': school.name if school else None, 'competition': comp.name if comp else None,
        'edition': doc.get('year'), 'entity_type': doc.get('entity_type'), 'kind': context.get('kind'),
        'source_type': source.get('source_type'), 'source_url': source.get('source_url'),
        'document_preview': source.get('content_preview') or source.get('content_text') or source.get('evidence_notes'),
        'source': source, 'flags': sorted(context.get('flags') or []),
        'proposals': [{'id': p.get('id'), 'field_name': p.get('field_name'),
            'candidate_value': deepcopy(p.get('candidate_value')), 'source': _source(p.get('source'))}
            for p in doc.get('proposals') or []]}


def _runtime(db):
    raw = os.environ.get('REVIEW_LEARNING_DB')
    if not raw:
        return None
    path = Path(raw).resolve()
    business = db.get_bind().url
    business_path = Path(business.database).resolve() if business.drivername.startswith('sqlite') and business.database not in {None, ':memory:'} else None
    if path == (ROOT / 'data/v02.sqlite').resolve() or path == business_path:
        raise HTTPException(409, '学习库必须与正式库和业务库分离')
    manifest_path = os.environ.get('REVIEW_LEARNING_MANIFEST')
    if not manifest_path:
        raise HTTPException(409, '未配置真实候选来源清单')
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise HTTPException(409, '无法读取候选来源清单') from exc
    if manifest.get('origin') != 'real_candidate' or not manifest.get('dataset_id') or not isinstance(manifest.get('candidates'), dict):
        raise HTTPException(409, '候选来源清单无效')
    mode = os.environ.get('REVIEW_LEARNING_ACTOR_MODE', 'automation')
    if mode not in {'human', 'automation'}:
        raise HTTPException(409, '审核运行模式无效')
    namespace = canonical_hash({'business': str(business), 'dataset': manifest['dataset_id']})
    return {'path': path, 'manifest': manifest, 'mode': mode, 'namespace': namespace}


def learning_config(db):
    from app.services.review_shadow_predictor import MODEL_VERSION
    runtime = _runtime(db)
    return {'enabled': bool(runtime), 'actor_mode': runtime['mode'] if runtime else None,
        'model_version': MODEL_VERSION, 'model_writes_enabled': False}


def learning_store(db):
    from app.services.review_learning_store import ReviewLearningStore
    runtime = _runtime(db)
    if runtime is None:
        raise HTTPException(409, '学习观察尚未启用')
    return ReviewLearningStore(runtime['path'], namespace=runtime['namespace']), runtime


def _public_session(session):
    return {key: session.get(key) for key in ('session_id', 'id', 'candidate_id', 'started_at', 'state')}


def start_learning(db, admin, candidate_id):
    from app.services.review_shadow_predictor import predict_shadow
    actor_id = require_admin(db, admin)
    store, runtime = learning_store(db)
    features = candidate_features(db, candidate_id)
    entry = runtime['manifest']['candidates'].get(str(candidate_id))
    initial_match = entry and entry.get('candidate_sha256') == canonical_hash(features)
    prepared_match = entry and entry.get('source_sha256') == source_content_hash(features) and _has_preparation(db, candidate_id)
    if not (initial_match or prepared_match):
        raise HTTPException(409, '候选不在真实样本清单中或输入已变化，请核对来源快照')
    row = db.get(ReviewQueue, candidate_id)
    if row.status not in {'pending', 'partially_approved', 'deferred'}:
        raise HTTPException(409, '该候选已完成审核')
    max_audit_id = db.scalar(select(func.max(AdminAuditLog.id))) or 0
    provenance = {'origin': 'real_candidate', 'actor_mode': runtime['mode'],
        'source': 'review_audit', 'dataset_id': runtime['manifest']['dataset_id'],
        'candidate_sha256': entry['candidate_sha256'], 'max_audit_id': max_audit_id}
    # Nothing from prediction is assigned to row, doc, queue or official facts.
    session = store.start_session(admin_id=actor_id, candidate_id=candidate_id,
        input_features=features, shadow_prediction=predict_shadow(features), provenance=provenance)
    return _public_session(session)


def _human_labels(data):
    primary = data.get('human_primary_type')
    if primary not in PRIMARY:
        raise HTTPException(422, '请独立选择文档一级类型')
    secondary = data.get('human_secondary_type') or None
    risk = data.get('human_risk_level') or None
    if risk not in {None, 'LOW_RISK', 'NORMAL', 'HIGH_RISK'}:
        raise HTTPException(422, '人工风险判断无效')
    return {'human_primary_type': primary, 'human_secondary_type': secondary,
        'human_risk_level': risk, 'human_policy': primary == 'policy'}


def learning_event(db, admin, session_id, event, details):
    actor_id = require_admin(db, admin)
    store, _ = learning_store(db)
    if event == 'submit':
        details = _human_labels(details or {})
    else:
        # Client clocks, claimed decisions and arbitrary source strings are not trusted.
        details = {}
    return _public_session(store.event(session_id, actor_id, event, details))


def _utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _human_audit(audit, labels):
    review = (audit.after or {}).get('review') or {}
    decisions = review.get('decisions') or []
    fields = {d['field_name']: d['action'] for d in decisions if d.get('field_name') and d.get('action') in {'approve','reject','defer'}}
    actions = set(fields.values())
    relation = None
    if audit.action == 'school_relation_review':
        action = review.get('action')
        if action not in {'approve','reject','defer'}:
            action = next((d.get('action') for d in decisions if d.get('action') in {'approve','reject','defer'}), None)
        relation = {'action': action, 'values': deepcopy((audit.after or {}).get('values') or {})}
    elif audit.action == 'field_reject_unstructured':
        action = 'reject'
    else:
        action = next(iter(actions)) if len(actions) == 1 else 'mixed' if actions else None
    if action is None:
        raise HTTPException(409, '该审计记录没有完成的人工决定')
    return {**labels, 'human_action': action, 'human_field_decisions': fields,
        'human_relation_decision': relation, 'human_note': review.get('note')}


def complete_learning(db, admin, session_id, data):
    actor_id = require_admin(db, admin)
    store, runtime = learning_store(db)
    session = store.get_session(session_id, actor_id)
    labels = _human_labels(data)
    completed = next((e for e in store.examples(active_only=False) if e['session_id'] == session_id and not e.get('supersedes_example_id')), None)
    if completed:
        if any(completed['human_ground_truth'].get(k) != v for k,v in labels.items()):
            raise HTTPException(409, '原审核已记录，修改标签请使用纠正入口')
        return completed
    if runtime['mode'] != 'human' or session['provenance'].get('actor_mode') != 'human':
        raise HTTPException(403, '自动化操作不能进入真实人工学习集')
    current = session['input_features']
    submitted = [e for e in session.get('events', []) if e.get('event') == 'submit']
    if not submitted:
        raise HTTPException(409, '缺少本次人工提交事件')
    if _human_labels(submitted[-1].get('details') or {}) != labels:
        raise HTTPException(409, '人工标签与提交时记录不一致')
    audits = list(db.scalars(select(AdminAuditLog).where(AdminAuditLog.id > session['provenance']['max_audit_id'],
        AdminAuditLog.admin_id == actor_id, AdminAuditLog.object_id == session['candidate_id'],
        AdminAuditLog.object_type == 'field_candidate', AdminAuditLog.action.in_(AUDIT_ACTIONS)).order_by(AdminAuditLog.id)))
    submit_at = _utc(submitted[-1].get('at') or submitted[-1]['timestamp'])
    audit = next((a for a in audits if _utc(a.created_at) >= submit_at
        and (a.after or {}).get('learning_session_id') == session_id
        and (a.after or {}).get('learning_submit_event_id') == submitted[-1].get('event_id')
        and (a.after or {}).get('learning_input_sha256') == session['snapshot_sha256']), None)
    if audit is None:
        raise HTTPException(409, '没有本次提交成功的人工审核记录')
    human = _human_audit(audit, labels)
    events = session.get('events') or []
    sources = [e for e in events if e.get('event') == 'source_open']
    decisions = [e for e in events if e.get('event') == 'decision']
    stamp = lambda e: e.get('at') or e.get('timestamp')
    reviewed = _utc(audit.created_at)
    context = {'audit_id': audit.id, 'audit_action': audit.action, 'reviewer_id': actor_id,
        'review_started_at': session['started_at'], 'opened_original_source': bool(sources),
        'source_open_count': len(sources), 'first_source_opened_at': stamp(sources[0]) if sources else None,
        'decision_at': stamp(decisions[0]) if decisions else None, 'submit_requested_at': stamp(submitted[-1]),
        'submitted_at': reviewed.isoformat(), 'reviewed_at': reviewed.isoformat(),
        'review_duration': max(0.0, (reviewed-_utc(session['started_at'])).total_seconds()),
        'candidate_status_after': db.get(ReviewQueue, session['candidate_id']).status,
        'policy_relation': human['human_relation_decision'],
        'recognition_type': ((human['human_relation_decision'] or {}).get('values') or {}).get('notice_type'),
        'approved_fields': [k for k,v in human['human_field_decisions'].items() if v == 'approve'],
        'rejected_fields': [k for k,v in human['human_field_decisions'].items() if v == 'reject'],
        'business_before': deepcopy(audit.before), 'business_after': deepcopy(audit.after),
        'prepared_during_review': bool((audit.after or {}).get('learning_prepared_during_review')),
        'conflict_handling': {'observed_flags': current.get('flags'),
            'decisions': deepcopy(((audit.after or {}).get('review') or {}).get('decisions') or [])},
        'source_open_is_click_observation': True, 'business_database_namespace': runtime['namespace']}
    return store.complete(session_id, actor_id, human_ground_truth=human, review_context=context,
        decision_key=f"{runtime['namespace']}:audit:{audit.id}")


def bind_learning_review(db, admin, candidate_id, session_id):
    """Validate frozen input and explicit submission before any business writes."""
    try:
        actor_id = require_admin(db, admin)
        store, _ = learning_store(db)
        session = store.get_session(session_id, actor_id)
        if session['candidate_id'] != candidate_id or session['state'] == 'completed':
            raise HTTPException(409, '学习会话不属于当前待提交候选')
        submits = [e for e in session['events'] if e['event'] == 'submit']
        if not submits:
            raise HTTPException(409, '请先保存本次独立人工选择')
        _human_labels(submits[-1]['details'])
        current = candidate_features(db, candidate_id)
        prepared = canonical_hash(current) != session['snapshot_sha256']
        if prepared and not (source_content_hash(current) == source_content_hash(session['input_features'])
            and _has_preparation(db, candidate_id, session['provenance']['max_audit_id'])):
            raise HTTPException(409, '候选输入已变化，请重新打开审核并确认材料')
        return {'learning_session_id': session_id, 'learning_submit_event_id': submits[-1]['event_id'],
            'learning_input_sha256': session['snapshot_sha256'],
            'learning_prepared_during_review': prepared,
            'before_audit_id': db.scalar(select(func.max(AdminAuditLog.id))) or 0}
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, '无法绑定有效学习会话') from exc


def attach_learning_audit(db, admin, candidate_id, binding):
    """Append binding to the same transaction as the human business decision."""
    db.flush()
    audit = db.scalar(select(AdminAuditLog).where(AdminAuditLog.id > binding['before_audit_id'],
        AdminAuditLog.admin_id == admin.id, AdminAuditLog.object_id == candidate_id,
        AdminAuditLog.object_type == 'field_candidate', AdminAuditLog.action.in_(AUDIT_ACTIONS))
        .order_by(AdminAuditLog.id.desc()))
    if audit is None:
        raise HTTPException(409, '业务提交缺少可绑定的人工审核日志')
    audit.after = {**(audit.after or {}), **{k: v for k,v in binding.items() if k != 'before_audit_id'}}
    db.flush()


def finalize_learning_after_commit(db, admin, result, session_id=None):
    """Best effort after a successful business commit; pending events remain retryable.

    Never raises into the completed business transaction or synthesizes labels.
    """
    if not session_id or not os.environ.get('REVIEW_LEARNING_DB') or not isinstance(result, dict) or not result.get('id'):
        return
    try:
        store, runtime = learning_store(db)
        if runtime['mode'] != 'human':
            return
        session = store.get_session(session_id, admin.id)
        submits = [e for e in session.get('events', []) if e.get('event') == 'submit']
        if submits:
            complete_learning(db, admin, session_id, submits[-1].get('details') or {})
    except Exception:
        log.exception('Committed review retained; learning record pending retry (candidate=%s)', result.get('id'))


def correct_learning(db, admin, example_id, truth, reason):
    actor_id = require_admin(db, admin)
    store, runtime = learning_store(db)
    if runtime['mode'] != 'human':
        raise HTTPException(403, '自动化环境不能纠正真实标签')
    old = next((e for e in store.examples(active_only=False) if e['id'] == example_id), None)
    if not old:
        raise HTTPException(404, '有效学习样本不存在')
    allowed = {'human_primary_type','human_secondary_type','human_risk_level'}
    if set(truth) - allowed:
        raise HTTPException(422, '字段、关系和动作只能来自业务审核日志，不能在学习库改写')
    merged = {**old['human_ground_truth'], **_human_labels({**old['human_ground_truth'], **truth})}
    return store.correct(example_id, actor_id, human_ground_truth=merged, reason=reason)
