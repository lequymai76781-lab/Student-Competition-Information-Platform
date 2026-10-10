"""Source classification is independent of field approval and policy recognition."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AdminAuditLog, Competition, ReviewQueue, University, User


def require_admin(db, admin):
    identity = getattr(admin, 'id', None)
    with db.no_autoflush:
        actual = db.execute(select(User.id, User.is_admin, User.is_active).where(User.id == identity)).first()
    if not actual or not actual.is_admin or not actual.is_active:
        raise HTTPException(403, '需要有效管理员身份')
    return actual.id


def candidate_document(row):
    try:
        doc = json.loads(row.raw_value or '')
        if not isinstance(doc, dict) or doc.get('schema_version') != 1:
            raise ValueError()
        return doc
    except (TypeError, ValueError):
        raise HTTPException(409, '候选文档格式无效')


def candidate_source(doc, row=None):
    context = doc.get('collection_context') or {}
    proposals = doc.get('proposals') or []
    source = deepcopy(context or (proposals[0].get('source') if proposals else {}) or {})
    try:
        evidence = json.loads((doc.get('description') or '').split('\n', 1)[1])
        raw = evidence.get('input') or {}
        original = raw.get('source') or raw
        if isinstance(original, dict):
            source = {**original, **source}
    except (ValueError, IndexError, AttributeError, TypeError):
        pass
    source['title'] = source.get('source_title') or source.get('title') or doc.get('title') or ''
    source['source_url'] = source.get('source_url') or source.get('url') or getattr(row, 'source_url', None)
    return source


def _source_fingerprint(doc,row=None):
    payload={'source':candidate_source(doc,row),'proposals':doc.get('proposals'),
        'context':doc.get('collection_context'),'university_id':doc.get('university_id'),'competition_id':doc.get('competition_id')}
    return sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def classification_for(doc, row=None):
    from app.services.hierarchical_source_classifier import classify_source_document
    from app.services.document_taxonomy import HIERARCHY_VERSION, map_primary_type, map_secondary_type
    context = doc.get('collection_context') or {}
    current = classify_source_document(candidate_source(doc, row), has_fact_changes=bool(doc.get('proposals')),
        has_conflicts=bool(context.get('flags')),
        has_valuable_relation=context.get('kind') == 'school_mapping')
    saved = doc.get('document_classification')
    if not (isinstance(saved, dict) and saved.get("source_fingerprint") == _source_fingerprint(doc, row)):
        return current
    if saved.get('classification_status') == 'HUMAN_CONFIRMED' and saved.get('corrected_at'):
        # Preserve the human semantic decision, re-evaluate current evidence and
        # safety separately. An old archive flag is never a safety attestation.
        primary = map_primary_type(saved.get('primary_type') or saved.get('document_type'))
        fine = saved.get('document_type', 'other')
        result = {**current, **{key: deepcopy(saved[key]) for key in (
            'document_type', 'secondary_types', 'classification_reason', 'corrected_at',
            'reviewer', 'predicted_type', 'source_fingerprint', 'human_primary_type',
        ) if key in saved}}
        result.update(primary_type=primary, secondary_type=map_secondary_type(fine)
                      if map_primary_type(fine) == primary else None,
                      classification_status='HUMAN_CONFIRMED', requires_human_confirmation=False,
                      hierarchy_version=HIERARCHY_VERSION)
        if primary == 'update' or current.get('risk_level') == 'HIGH_RISK':
            result['risk_level'] = 'HIGH_RISK'
        result['informational_only'] = bool(primary == 'information'
            and current.get('primary_type') == 'information' and current.get('informational_only')
            and result.get('risk_level') != 'HIGH_RISK')
        return result
    # Fresh classification is pure and cheap. Recomputing also prevents cached
    # machine decisions from bypassing a changed safety threshold or taxonomy.
    return current


def classification_item(db, row):
    doc = candidate_document(row)
    comp = db.get(Competition, row.competition_id) if row.competition_id else None
    school = db.get(University, row.university_id) if row.university_id else None
    return {'id': row.id, 'title': doc.get('title') or row.reason, 'source_url': row.source_url or candidate_source(doc).get('source_url'),
        'school_name': school.name if school else None, 'competition_name': comp.name if comp else None,
        'status': row.status, 'classification': classification_for(doc, row), 'relation_evidence':doc.get('participation_evidence')}


def _candidate(db, identity):
    row = db.get(ReviewQueue, identity)
    if row is None or row.item_type != 'field_candidate':
        raise HTTPException(404, '来源候选不存在')
    return row


def _route(row, doc, classification):
    # Routing never marks a fact as approved, rejected, or verified.
    context = doc.get('collection_context') or {}
    safe = not doc.get('proposals') and not context.get('flags') and context.get('kind') != 'school_mapping' and classification['risk_level'] != 'HIGH_RISK'
    classification['informational_only'] = bool(classification.get('primary_type') == 'information' and classification.get('informational_only') and safe)
    if row.status in {'pending', 'informational'}:
        row.status = 'informational' if classification['informational_only'] else 'pending'
    classification['source_fingerprint']=_source_fingerprint(doc,row)
    source=candidate_source(doc,row)
    ordinary={'participation','result'}
    if (classification.get('primary_type') in ordinary and classification['classification_status'] in {'AUTO_CLASSIFIED','HUMAN_CONFIRMED'}
            and context.get('kind')=='school_mapping' and row.university_id and row.competition_id and source.get('source_url')):
        doc['participation_evidence']={'relation_type':'participation_evidence','status':'evidence_only',
            'school_id':row.university_id,'competition_id':row.competition_id,'edition_id':doc.get('edition_id'),
            'document_type':classification['document_type'],'source_url':source['source_url'],'source_title':source['title'],
            'publisher':source.get('publisher'),'collected_at':source.get('collected_at') or doc.get('created_at'),
            'verification_method':'DOCUMENT_CLASSIFICATION','source_fingerprint':classification['source_fingerprint']}
    else:doc.pop('participation_evidence',None)
    doc['document_classification'] = classification
    row.raw_value = json.dumps(doc, ensure_ascii=False)


class DocumentPolicyService:
    @staticmethod
    def classify_candidate(db, identity, *, admin=None):
        actor = require_admin(db, admin) if admin is not None else None
        row = _candidate(db, identity)
        doc = candidate_document(row)
        prior = doc.get('document_classification')
        if prior and prior.get('corrected_at') and prior.get('source_fingerprint')==_source_fingerprint(doc,row):
            # Preserve the human type, but reapply current routing permissions:
            # confirming a type alone never certifies informational safety.
            _route(row, doc, classification_for(doc, row))
            db.flush()
            return classification_item(db, row)
        doc.pop('document_classification', None)
        classification = classification_for(doc, row)
        _route(row, doc, classification)
        if prior != classification and actor is not None:
            db.add(AdminAuditLog(admin_id=actor, action='document_classified', object_type='field_candidate', object_id=row.id,
                before=prior, after=classification, created_at=datetime.now(timezone.utc)))
        db.flush()
        return classification_item(db, row)

    @staticmethod
    def correct_classification(db, identity, document_type, reason, *, admin):
        from app.services.source_document_classifier import DOCUMENT_TYPES
        from app.services.document_taxonomy import PRIMARY_TYPES, HIERARCHY_VERSION, map_primary_type, map_secondary_type
        actor = require_admin(db, admin)
        if document_type not in {*DOCUMENT_TYPES, *PRIMARY_TYPES} or not reason or not reason.strip():
            raise HTTPException(422, '需要有效分类及更正原因')
        row = _candidate(db, identity); doc = candidate_document(row)
        before = classification_for(doc, row)
        at = datetime.now(timezone.utc)
        primary = map_primary_type(document_type)
        # A broad human decision need not invent a precise secondary label.
        fine = document_type if document_type in DOCUMENT_TYPES else (
            before['document_type'] if map_primary_type(before['document_type']) == primary else 'other')
        secondary = map_secondary_type(fine) if map_primary_type(fine) == primary else None
        classification = {**before, 'document_type': fine, 'primary_type': primary,
            'secondary_type': secondary, 'human_primary_type': primary,
            'secondary_types': [t for t in before.get('secondary_types', [])
                                if t != fine and map_primary_type(t) == primary],
            'classification_status': 'HUMAN_CONFIRMED', 'requires_human_confirmation': False,
            'classification_reason': reason.strip(), 'corrected_at': at.isoformat(), 'reviewer': actor,
            'hierarchy_version': HIERARCHY_VERSION,
            'predicted_type': before.get('predicted_type', before['document_type']),
            'informational_only': bool(primary == 'information' and before.get('primary_type') == 'information'
                                       and before.get('informational_only'))}
        if primary == 'update' or before.get('risk_level') == 'HIGH_RISK':
            classification['risk_level'] = 'HIGH_RISK'
        _route(row, doc, classification)
        db.add(AdminAuditLog(admin_id=actor, action='document_classification_corrected', object_type='field_candidate', object_id=row.id,
            before=before, after={**classification, 'final_type': document_type, 'reason': reason.strip()}, created_at=at))
        db.flush()
        return classification_item(db, row)

    @staticmethod
    def list_sources(db, *, limit=50, offset=0):
        from app.services.source_document_classifier import DOCUMENT_TYPE_LABELS
        from app.services.document_taxonomy import PRIMARY_TYPE_LABELS
        rows = list(db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == 'field_candidate').order_by(ReviewQueue.id)))
        stats = Counter(); types = Counter()
        for row in rows:
            c = classification_for(candidate_document(row), row)
            stats[c['classification_status']] += 1; types[c['primary_type']] += 1
            stats['informational_only'] += int(c['informational_only'])
            stats['pending_field_review'] += int(row.status in {'pending', 'partially_approved', 'deferred'})
        return {'items': [classification_item(db, r) for r in rows[offset:offset + limit]], 'total': len(rows),
            'statistics': {**dict(stats), 'by_type': dict(types)}, 'document_types': [{'value': value, 'label': label} for value, label in PRIMARY_TYPE_LABELS.items()],
            'secondary_document_types': [{'value': value, 'label': label} for value, label in DOCUMENT_TYPE_LABELS.items()]}

    @staticmethod
    def replay(db, *, admin):
        require_admin(db, admin)
        ids = list(db.scalars(select(ReviewQueue.id).where(ReviewQueue.item_type == 'field_candidate', ReviewQueue.status.in_(['pending', 'informational']))))
        for identity in ids:
            DocumentPolicyService.classify_candidate(db, identity, admin=admin)
        return DocumentPolicyService.list_sources(db)


from app.services.policy_automation_service import PolicyAutomationService  # Public integration facade.
