"""Replay only local existing sources into an explicitly isolated DB copy.

No HTTP fetch, no production migration, and no generated human labels.
"""
from pathlib import Path
import sys,json,sqlite3,hashlib,csv,argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from app.models import PolicyDocument,ReviewQueue,User,CompetitionPolicyRecognition,AdminAuditLog
from app.database.review_guard import ReviewGuardedSession
from app.services.document_policy_service import DocumentPolicyService,PolicyAutomationService,candidate_document,candidate_source
from app.services.source_document_classifier import classify_document,POLICY_TYPES,DOCUMENT_TYPES
from app.services.document_policy_evaluation import evaluate_classification

def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'.codex-qa/document-policy/replay'));args=parser.parse_args()
 out=Path(args.output).resolve();allowed=(ROOT/'.codex-qa/document-policy').resolve()
 if not out.is_relative_to(allowed):raise SystemExit('Output must stay within document-policy experiment directory')
 out.mkdir(parents=True,exist_ok=True);target=out/'replay.sqlite'
 if target.exists():raise SystemExit('Refusing to overwrite an existing replay database; choose a fresh --output')
 protected=[ROOT/'data/v02.sqlite',ROOT/'.codex-qa/mid-scale/candidates.sqlite']
 before={str(p.relative_to(ROOT)):digest(p) for p in protected}
 with sqlite3.connect(protected[1].as_uri()+'?mode=ro',uri=True) as src:
  src.execute('pragma query_only=ON')
  with sqlite3.connect(target) as dst:src.backup(dst)
 policy_target=out/'policy-replay.sqlite'
 with sqlite3.connect(protected[0].as_uri()+'?mode=ro',uri=True) as src:
  src.execute('pragma query_only=ON')
  with sqlite3.connect(policy_target) as dst:src.backup(dst)
 engine=create_engine('sqlite:///'+target.as_posix())
 policy_engine=create_engine('sqlite:///'+policy_target.as_posix())
 with Session(policy_engine) as seed:
  policy_actor=User(username='document_policy_replay',email='document-policy-replay@local.test',hashed_password='disabled-replay-login',is_admin=True,is_active=True)
  seed.add(policy_actor);seed.commit();policy_actor_id=policy_actor.id
 policy_session=ReviewGuardedSession(policy_engine)
 policy_actor=policy_session.get(User,policy_actor_id)
 sources={};policy_results=[];errors=[]
 with Session(engine) as db:
  actor=User(username='document_policy_replay',email='document-policy-replay@local.test',hashed_password='disabled-replay-login',is_admin=True,is_active=True);db.add(actor);db.commit();actor_id=actor.id
 with ReviewGuardedSession(engine) as db:
  actor=db.get(User,actor_id)
  rows=list(db.scalars(select(ReviewQueue).where(ReviewQueue.item_type=='field_candidate').order_by(ReviewQueue.id)))
  before_queue=Counter(r.status for r in rows)
  for row in rows:
   doc=candidate_document(row);source=candidate_source(doc,row);url=source.get('source_url')
   if url and url.startswith(('http://','https://')):
    sources.setdefault(url,{'source_id':hashlib.sha256(url.encode()).hexdigest()[:16],'source_url':url,'title':source.get('title'),
       'content_preview':source.get('content_preview') or source.get('content_text') or '', 'publisher':source.get('publisher'),
       'candidate_ids':[],'origin':'existing_field_candidate','body_available':bool(source.get('content_preview') or source.get('content_text'))})['candidate_ids'].append(row.id)
  policies=list(policy_session.scalars(select(PolicyDocument).order_by(PolicyDocument.id)))
  for doc in policies:
   url=doc.source_url
   if url and url.startswith(('http://','https://')):
    sources.setdefault(url,{'source_id':hashlib.sha256(url.encode()).hexdigest()[:16],'source_url':url,'title':doc.title,
       'content_preview':(doc.content_text or '')[:3500],'publisher':doc.publisher,'candidate_ids':[],
       'policy_document_id':doc.id,'origin':'existing_policy_document','body_available':bool(doc.content_text)})
  for source in sources.values():source['classification']=classify_document(source)
  # Spread the bounded replay over observed predicted types, without fabricating absent types.
  buckets=defaultdict(list)
  for source in sources.values():buckets[source['classification']['document_type']].append(source)
  selected=[]
  while len(selected)<200 and any(buckets.values()):
   for kind in sorted(buckets):
    if buckets[kind] and len(selected)<200:selected.append(buckets[kind].pop(0))
  dump(out/'source-replay.json',selected)
  source_counts=Counter(s['classification']['classification_status'] for s in selected)
  source_types=Counter(s['classification']['document_type'] for s in selected)
  DocumentPolicyService.replay(db,admin=actor);db.commit()
  for identity in [p.id for p in policies]:
   try:
    result=PolicyAutomationService.analyze(policy_session,identity,admin=policy_actor);policy_session.commit()
    policy_results.append({'policy_document_id':identity,**result})
   except Exception as exc:
    policy_session.rollback();errors.append({'policy_document_id':identity,'error':str(exc)})
  dump(out/'policy-replay.json',policy_results)
  after_queue=Counter(db.scalars(select(ReviewQueue.status).where(ReviewQueue.item_type=='field_candidate')))
  field_docs=[candidate_document(r) for r in db.scalars(select(ReviewQueue).where(ReviewQueue.item_type=='field_candidate'))]
  classification_counts=Counter(d['document_classification']['classification_status'] for d in field_docs)
  entries=[e for p in policy_results for e in p['entries']]
  auto=list(policy_session.scalars(select(AdminAuditLog).where(AdminAuditLog.action=='auto_policy_match')))
  dimension_counts=Counter((a.after or {}).get('recognition_type') for a in auto)
  pending_policy=policy_session.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.item_type=='policy_match',ReviewQueue.status=='pending'))
  # Keep blank human truth. Predictions are deliberately not shown in the label file.
  gold=selected[:100]
  columns=['source_id','source_url','title','content_preview','label','label_provenance','reviewer','reviewed_at','notes']
  with (out/'golden-to-label.csv').open('w',encoding='utf-8-sig',newline='') as f:
   writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
   for row in gold:writer.writerow({key:row.get(key,'') for key in columns})
  labels_path=out/'human-labels.csv'
  labels=list(csv.DictReader(labels_path.open(encoding='utf-8-sig'))) if labels_path.exists() else []
  metrics=evaluate_classification(labels,{s['source_id']:s['classification']['document_type'] for s in selected})
  dump(out/'classification-metrics.json',metrics)
  summary={'at':datetime.now(timezone.utc).isoformat(),'real_source_pool':len(sources),'real_source_replay_n':len(selected),
   'sampling':'round-robin across predicted document types; purposive, not random or independent gold',
   'document_type_counts':dict(source_types),'classification_status_counts':dict(source_counts),
   'informational_only_source_n':sum(s['classification']['informational_only'] for s in selected),
   'source_policy_document_n':sum(s['classification']['document_type'] in POLICY_TYPES for s in selected),
   'multilabel_n':sum(bool(s['classification']['secondary_types']) for s in selected),
   'body_available_n':sum(s['body_available'] for s in selected),
   'policy_documents_n':len(policies),'policy_replay_n':len(policy_results),'extracted_entries_n':len({(p['policy_document_id'],e['raw_competition_name'],str(e.get('locator'))) for p in policy_results for e in p['entries']}),
   'typed_entries_n':len(entries),'policy_match_counts':dict(Counter(e['match_status'] for e in entries)),
   'automatic_relations_created_n':len(auto),'recognition_type_counts':dict(dimension_counts),
   'policy_needs_human_n':sum(p['requires_human_confirmation'] for p in policy_results),'policy_pending_entry_tasks':pending_policy,
   'policy_conflict_documents_n':sum(bool(p['conflicts']) for p in policy_results),
   'original_field_queue':dict(before_queue),'after_field_queue':dict(after_queue),'candidate_classification_counts':dict(classification_counts),
   'participation_evidence_candidates':sum(bool(d.get('participation_evidence')) for d in field_docs),
   'classification_task_reduction_fraction':classification_counts['AUTO_CLASSIFIED']/len(field_docs) if field_docs else None,
   'remaining_field_review_tasks':sum(after_queue[k] for k in ['pending','partially_approved','deferred']),
   'actual_main_queue_reduction_fraction':(before_queue['pending']-after_queue['pending'])/before_queue['pending'] if before_queue['pending'] else None,
   'policy_relation_judgment_reduction_fraction':len(auto)/(len(auto)+pending_policy) if len(auto)+pending_policy else None,
   'golden_prepared_n':len(gold),'human_gold_n':metrics['human_n'],'errors':errors,'protected_databases':{p:{'before':h,'after':digest(ROOT/p),'unchanged':h==digest(ROOT/p)} for p,h in before.items()}}
  assert all(v['unchanged'] for v in summary['protected_databases'].values())
  dump(out/'summary.json',summary)
  print(json.dumps({k:v for k,v in summary.items() if k not in ['protected_databases','document_type_counts','sampling']},ensure_ascii=False,indent=2))
 engine.dispose();policy_session.close();policy_engine.dispose()

if __name__=='__main__':main()
