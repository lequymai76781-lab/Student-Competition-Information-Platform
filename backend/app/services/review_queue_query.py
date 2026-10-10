"""Request-local read batching and conservative review risk."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import select
from app.models import Competition, CompetitionEdition, CompetitionFactSource, ReviewQueue, University, CrawlerJob

CONTEXT_KEY='field_review_read_context'
STRONG_SOURCES={'official_website','organizer_notice','government_document','university_notice','university_policy'}
IMPORTANT_FIELDS={'name','short_name','english_name','former_names','organizer','co_organizers','guiding_organizations','undertakers','founded_year','first_held_year','edition_count','development_history','history_timeline','edition_name','edition_number','registration_start','registration_deadline','official_registration_deadline','university_registration_deadline','submission_deadline','official_submission_deadline','competition_start','competition_end','official_competition_date','announcement_date','official_website','official_registration_url'}

def classification(detail,*,target_exists):
    from app.services.field_review_service import _empty_value,_dump,FINAL
    context=detail.get('collection_context') or {}
    reasons=set(detail['flags']) & {'CONFLICT','NO_SOURCE','DUPLICATE_SUSPECTED','edition_uncertain','RELATION_CONFLICT'}
    if not target_exists:reasons.add('ENTITY_UNCERTAIN')
    if context.get('kind')=='school_mapping':reasons.add('SCHOOL_RELATION')
    fields=[f for f in detail['fields'] if f['decision'] not in FINAL]
    low,eligible=[],[]
    for field in fields:
        local=set()
        if field['change_type']=='modify':local.add('OVERWRITE_EXISTING')
        if field['change_type']=='delete':local.add('DELETE_VALUE')
        if field['field_name'] in IMPORTANT_FIELDS:local.add('IMPORTANT_FIELD')
        if len({_dump(p['candidate_value']) for p in field['proposals']+field['conflicts']})>1:local.add('CONFLICT')
        for p in field['proposals']:
            source=p['source']
            if source.get('verification_state')=='NO_SOURCE':local.add('NO_SOURCE')
            if source.get('source_type') not in STRONG_SOURCES:local.add('WEAK_SOURCE')
        if field['current_value'] is not None and field['change_type']!='unchanged':local.add('OVERWRITE_EXISTING')
        field['risk_reasons']=sorted(local);reasons.update(local)
        if not local and field['current_value'] is None and not _empty_value(field['candidate_value']):
            low.append(field['field_name'])
            if all(p['source'].get('verification_state')=='VERIFIED' for p in field['proposals']):eligible.append(field['field_name'])
    if not fields and detail['status'] in {'pending','partially_approved'}:reasons.add('UNSTRUCTURED')
    level='HIGH_RISK' if reasons else 'LOW_RISK' if low else 'NORMAL'
    detail.update(risk_level=level,risk_reasons=sorted(reasons),low_risk_fields=low if not reasons else [],bulk_eligible_fields=eligible if not reasons else [])
    if level!='NORMAL':detail['flags']=sorted(set(detail['flags'])|{level})
    return detail

def timeline(field,*,candidate_id,entity_type):
    rows=[{'candidate_id':candidate_id,'proposal_id':p['id'],'candidate_value':p['candidate_value'],'source':p['source']} for p in field['proposals']]+field['conflicts']
    scope='校内截止' if field['field_name'].startswith('university_') else '赛事本体' if entity_type=='competition' else '赛事官方届次'
    def key(row):
        source=row.get('source') or {}
        def timestamp(value):
            if not value:return float('inf')
            try:
                parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
                return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).timestamp()
            except (ValueError,TypeError):return float('inf')
        return timestamp(source.get('published_at')),timestamp(source.get('collected_at')),row['candidate_id']
    return [{**r,'scope':scope,'announcement_hint':next((v for v in ('延期','更正','补充') if v in ((r.get('source') or {}).get('source_title') or '')),None)} for r in sorted(rows,key=key)]

@contextmanager
def preload(db,rows):
    """Read-only request scope; never use cached previews for mutations."""
    from app.services.field_review_service import _document,_identity,FINAL
    rows=list(rows)
    pending=list(db.scalars(select(ReviewQueue).where(ReviewQueue.item_type=='field_candidate',ReviewQueue.status.in_(['pending','partially_approved']))))
    all_rows={r.id:r for r in [*pending,*rows]};documents={i:_document(r) for i,r in all_rows.items()}
    ids={d['competition_id'] for d in documents.values() if d.get('competition_id')}
    comps={c.id:c for c in db.scalars(select(Competition).where(Competition.id.in_(ids)))}
    editions={e.id:e for e in db.scalars(select(CompetitionEdition).where(CompetitionEdition.competition_id.in_(ids)))}
    universities={u.id:u for u in db.scalars(select(University).where(University.id.in_({r.university_id for r in rows if r.university_id})))}
    facts=defaultdict(list)
    for f in db.scalars(select(CompetitionFactSource).where(CompetitionFactSource.competition_id.in_(ids)).order_by(CompetitionFactSource.id.desc())):facts[(f.competition_id,f.competition_edition_id,f.field_name)].append(f)
    external=defaultdict(lambda:defaultdict(list))
    for row in pending:
        doc=documents[row.id];identity=_identity(doc)
        if identity:
            for p in doc['proposals']:
                if doc['decisions'].get(p['field_name'],{}).get('action') not in FINAL:external[identity][p['field_name']].append({'candidate_id':row.id,'proposal_id':p['id'],'candidate_value':p['candidate_value'],'source':p['source']})
    cache=dict(rows=all_rows,documents=documents,competitions=comps,editions=editions,years={(e.competition_id,e.year):e for e in editions.values()},universities=universities,facts=facts,external=external)
    previous=db.info.get(CONTEXT_KEY);db.info[CONTEXT_KEY]=cache
    try:yield cache
    finally:
        if previous is None:db.info.pop(CONTEXT_KEY,None)
        else:db.info[CONTEXT_KEY]=previous

def list_candidates(db,**params):
    from app.services.field_review_service import FieldReviewService as Review,FIELDS
    status=params.get('status');limit=params.get('limit',50);offset=params.get('offset',0)
    query=select(ReviewQueue).where(ReviewQueue.item_type=='field_candidate')
    if status and status!='all':query=query.where(ReviewQueue.status==status)
    for name in ('competition_id','university_id'):
        if params.get(name) is not None:query=query.where(getattr(ReviewQueue,name)==params[name])
    if params.get('created_from'):query=query.where(ReviewQueue.created_at>=params['created_from'])
    if params.get('created_to'):query=query.where(ReviewQueue.created_at<=params['created_to'])
    rows=list(db.scalars(query.order_by(ReviewQueue.created_at.desc(),ReviewQueue.id.desc())))
    derived=any(params.get(k) for k in ('flag','risk')) or params.get('sort')=='priority'
    matches=[]
    with preload(db,rows) as cache:
        for row in rows:
            doc=cache['documents'][row.id];context=doc.get('collection_context') or {}
            if params.get('entity_type') and doc['entity_type']!=params['entity_type']:continue
            if params.get('submitter_id') and doc.get('submitter_id')!=params['submitter_id']:continue
            if params.get('relation_type') and context.get('notice_type')!=params['relation_type']:continue
            if params.get('source_type') and context.get('source_type')!=params['source_type'] and not any(p['source'].get('source_type')==params['source_type'] for p in doc['proposals']):continue
            if term:=(params.get('search') or '').strip().casefold():
                comp=cache['competitions'].get(doc.get('competition_id'));school=cache['universities'].get(row.university_id)
                haystack=' '.join(str(v or '') for v in [doc.get('title'),getattr(comp,'name',None),getattr(school,'name',None),context.get('school_name'),context.get('source_title'),*[p['field_name']+' '+FIELDS[doc['entity_type']][p['field_name']][0]+' '+str(p['source'].get('source_title') or '') for p in doc['proposals']]])
                if term not in haystack.casefold():continue
            cache['summary_mode']=True
            detail=Review.detail(db,row) if derived else None
            cache['summary_mode']=False
            if params.get('flag') and params['flag'] not in detail['flags']:continue
            if params.get('risk') and detail['risk_level']!=params['risk']:continue
            matches.append((row,detail))
        if params.get('sort')=='oldest':matches.reverse()
        if params.get('sort')=='priority':
            def rank(pair):
                d=pair[1];reasons=set(d['risk_reasons']);kind=(d.get('collection_context') or {}).get('notice_type')
                return 0 if 'RELATION_CONFLICT' in reasons or 'CONFLICT' in reasons else 1 if 'OVERWRITE_EXISTING' in reasons else 2 if kind=='policy_recognition' else 3 if 'NO_SOURCE' in reasons else 4 if d['risk_level']=='HIGH_RISK' else 6 if d['risk_level']=='LOW_RISK' else 5
            matches.sort(key=rank)
        page=[]
        for row,detail in matches[offset:offset+limit]:
            d=Review.detail(db,row)
            page.append({**d,'history':[],'fields':[{**f,'proposals':[],'conflicts':[],'timeline':[]} for f in d['fields']]})
        return {'items':page,'total':len(matches)}

def statistics(db):
    from app.services.field_review_service import FieldReviewService as Review
    rows=list(db.scalars(select(ReviewQueue).where(ReviewQueue.item_type=='field_candidate')))
    result={key:0 for key in ('pending','approved','rejected','partially_approved','deferred','conflict','no_source','duplicate_suspected','low_risk','high_risk','school_relations')}
    with preload(db,rows) as cache:
        cache["summary_mode"]=True
        for row in rows:
            if row.status in result:result[row.status]+=1
            d=Review.detail(db,row)
            if (d.get('collection_context') or {}).get('kind')=='school_mapping':result['school_relations']+=1
            if row.status not in {'pending','partially_approved'}:continue
            for key,flag in [('conflict','CONFLICT'),('no_source','NO_SOURCE'),('duplicate_suspected','DUPLICATE_SUSPECTED'),('low_risk','LOW_RISK'),('high_risk','HIGH_RISK')]:
                if flag in d['flags'] or key=='conflict' and 'RELATION_CONFLICT' in d['flags']:result[key]+=1
    return result

def source_observations(db):
    cache=db.info.get(CONTEXT_KEY)
    if cache is not None and 'source_observations' in cache:return cache['source_observations']
    observations={}
    for job in db.scalars(select(CrawlerJob).where(CrawlerJob.job_type=='mid_scale_candidate').order_by(CrawlerJob.id)):
        for entry in ((job.metadata_json or {}).get('items') or {}).values():
            result=entry.get('fetch_result')
            if not result:continue
            url=result.get('url') or ((entry.get('input') or {}).get('source') or {}).get('url')
            at=result.get('fetched_at') or ''
            if url and at>=observations.get(url,{}).get('checked_at',''):
                reason=result.get('source_failure_reason')
                state={'timeout':'TIMEOUT','404':'404','403':'BLOCKED','blocked':'BLOCKED','requires_js':'REQUIRES_JS','requires_login':'LOGIN_REQUIRED','ssl_error':'SSL_ERROR'}.get(reason,'UNKNOWN') if reason else 'AVAILABLE' if result.get('status_code')==200 else 'UNKNOWN'
                observations[url]={'status':state,'checked_at':at,'status_code':result.get('status_code')}
    if cache is not None:cache['source_observations']=observations
    return observations
