"""Cross-candidate atomic low-risk approval; no source verification shortcut."""
from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import update
from app.schemas.field_review import FieldBulkReviewIn

def preview(db,payload,*,admin):
    from app.services.field_review_service import FieldReviewService as R,_admin,_input,_error
    _admin(db,admin);payload=_input(FieldBulkReviewIn,payload)
    if len({p.id for p in payload.items})!=len(payload.items):_error('批量候选不能重复')
    details=[]
    for item in payload.items:
        d=R.detail(db,item.id)
        if d['preview_token']!=item.preview_token:_error('批量预览已过期',409)
        if d['risk_level']!='LOW_RISK' or len(set(item.field_names))!=len(item.field_names) or any(n not in d['low_risk_fields'] for n in item.field_names):
            _error('高风险或非新增字段不能进入低风险批量')
        details.append(d)
    return {'items':details,'total':len(details),'field_count':sum(len(p.field_names) for p in payload.items),'transaction':'atomic'}

def execute(db,payload,*,admin):
    from app.services.field_review_service import FieldReviewService as R,_admin,_input,_error,_row,_document,_target,_claim,FIELDS
    from app.database.review_guard import reviewed_write
    _admin(db,admin);payload=_input(FieldBulkReviewIn,payload)
    identity=None
    try:
        if len({p.id for p in payload.items})!=len(payload.items):_error('批量候选不能重复')
        locks,plans,seen={},[],set()
        for item in payload.items:
            identity=item.id
            d=R.detail(db,identity)
            if d['preview_token']!=item.preview_token:_error('批量预览已过期',409)
            if d['risk_level']!='LOW_RISK':_error('高风险候选必须单条人工审核')
            if len(set(item.field_names))!=len(item.field_names):_error('批量字段不能重复')
            row=_row(db,identity);doc=_document(row);target=_target(db,doc)
            if target is None:_error('实体或届次尚未明确')
            target_key=(type(target),target.id)
            locks.setdefault(target_key,(identity,target.updated_at,{name:deepcopy(getattr(target,name)) for name,(_,kind) in FIELDS[doc['entity_type']].items() if kind!='list'}))
            _claim(db,row)
            decisions=[]
            for name in item.field_names:
                key=(*target_key,name)
                if name not in d['bulk_eligible_fields']:_error('批量仅支持已逐来源核验、无冲突且不覆盖正式值的低风险字段')
                if key in seen:_error('同一正式字段的多个候选须合并证据后逐条处理')
                seen.add(key)
                f=next(f for f in d['fields'] if f['field_name']==name)
                decisions.append({'field_name':name,'action':'approve','proposal_id':f['proposals'][0]['id']})
            plans.append((identity,decisions))
        # CAS every target, before any fact write; fresh tokens below only cover our own distinct writes.
        for (model,target_id),(owner_id,version,values) in locks.items():
            identity=owner_id
            conditions=[model.id==target_id,model.updated_at==version]
            conditions.extend(getattr(model,k)==v for k,v in values.items())
            with reviewed_write(db):
                changed=db.execute(update(model).where(*conditions).values(updated_at=version).execution_options(synchronize_session=False))
                if changed.rowcount!=1:_error('正式值已变化，请重新预览整个批量',409)
        results=[]
        for identity,decisions in plans:
            current=R.detail(db,identity)
            if current['risk_level']!='LOW_RISK' or any(d['field_name'] not in current['bulk_eligible_fields'] for d in decisions):
                _error('批量字段的冲突、身份或来源已变化，请重新预览',409)
            results.append(R.review(db,identity,{'preview_token':current['preview_token'],'note':payload.note,'decisions':decisions},admin=admin))
        return {'items':results,'total':len(results),'succeeded':len(results),'failed':0,'pending_ids':[],'transaction':'atomic'}
    except Exception as exc:
        # The caller's outer savepoint rolls back facts, statuses and audits together.
        message=str(exc.detail) if isinstance(exc,HTTPException) else '批量审核失败；本批次全部回滚，可保留选择后重试'
        raise HTTPException(status_code=exc.status_code if isinstance(exc,HTTPException) else 500,
            detail={'message':message,'failed_candidate_id':identity,'succeeded':0,'failed':len(payload.items),
                    'pending_ids':[p.id for p in payload.items],'transaction':'atomic'}) from exc
