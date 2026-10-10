"""Conservative automation of typed school policy relations, never competition facts.

Only persisted source documents are accepted. The caller owns commit/rollback.
Heuristic classification or a matching name alone never grants recognition.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path

PROJECT_ROOT=Path(__file__).resolve().parents[3]
RAW_ROOT=PROJECT_ROOT / "data" / "raw"
from urllib.parse import urlsplit
from fastapi import HTTPException
from sqlalchemy import select
from app.database.review_guard import reviewed_write
from app.models import (AdminAuditLog, College, PolicyAttachment, PolicyDocument, University,
    CompetitionPolicyRecognition as Recognition, ReviewQueue)


def _utc(value):
    if value is None: return None
    if isinstance(value, str): value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value):
    return _utc(value).isoformat() if value else None


def _host(url):
    try:
        parsed = urlsplit(url or '')
        if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password: return None
        return parsed.hostname.lower().rstrip('.') if parsed.hostname else None
    except ValueError: return None


def _official(db, document):
    school = db.get(University, document.university_id)
    domains = set()
    for value in [getattr(school, 'official_domain', None), _host(getattr(school, 'official_website', None))]:
        if value: domains.add(value.lower().strip().rstrip('.'))
    if document.college_id:
        college = db.get(College, document.college_id)
        if college and college.university_id == document.university_id and college.is_verified:
            for value in [college.official_domain, _host(college.official_website)]:
                if value: domains.add(value.lower().strip().rstrip('.'))
    def allowed(url):
        host = _host(url)
        return bool(host and any(host == d or host.endswith('.' + d) for d in domains))
    # A document cannot whitelist its own asserted official_domain.
    return allowed(document.source_url) and (not document.attachment_url or allowed(document.attachment_url))


def _classification(document):
    from app.services.hierarchical_source_classifier import classify_source_document
    return classify_source_document({'title': document.title, 'content_preview': (document.content_text or '')[:3500],
        'content_text': document.content_text or '', 'source_url': document.source_url,
        'section': (document.metadata_json or {}).get('section'), 'document_format': document.parser_type,
        'publisher': document.publisher, 'attachment_titles': [document.original_filename] if document.original_filename else []}, has_valuable_relation=True)


def _dimensions(classification):
    from app.services.source_document_classifier import RECOGNITION_TYPES
    return sorted({RECOGNITION_TYPES[t] for t in [classification['document_type'], *classification.get('secondary_types', [])] if t in RECOGNITION_TYPES})


def _student_scope(document):
    meta=document.metadata_json or {}
    prepared=meta.get('relation_scope') or {}
    analysis=meta.get('policy_automation') or {}
    body=document.content_text or ''
    # Automatically inferred scopes are tied to the exact evidence version.
    cached=prepared.get('student_scope') if not analysis or analysis.get('source_sha256')==sha256(body.encode()).hexdigest() else None
    clauses=[document.title]
    clauses.extend(sentence for sentence in re.split(r'[。；;\n，,]',body)
        if re.search(r'适用|面向|对象为|对象是|本科[生学生]{1,3}.*(?:加分|认定)|研究生.*(?:加分|认定)',sentence)
        and not re.search(r'不适用|不包括|除外|不含|不面向',sentence))
    text=' '.join(clauses)
    if re.search(r'全校学生|全体学生|所有在校学生|本科生[和及、与]+研究生',text):inferred='all'
    else:
        under=bool(re.search(r'本科(?:生|学生)',text));post=bool(re.search(r'研究生|硕士生|博士生',text))
        if under and post:return None
        inferred='undergraduate' if under else 'postgraduate' if post else None
    if cached in {'undergraduate','postgraduate','all'}:
        return cached if not inferred or cached==inferred else None
    return inferred


def _entry_dimensions(entry, dimensions):
    context=' '.join([entry.get('section_heading') or '', *map(str,(entry.get('benefit_context') or {}).values())])
    patterns={
        'postgraduate_recommendation_recognition':r'推免|保研|推荐免试',
        'comprehensive_evaluation_recognition':r'综测|综合测评|综合素质测评|素质综合测评',
        'innovation_credit_recognition':r'创新学分|第二课堂|创新创业学分',
        'award_recognition':r'奖励|奖金|奖学金',
        'policy_recognition':r'学科竞赛认定|竞赛分类|正式认定',
    }
    explicit={key for key,pattern in patterns.items() if re.search(pattern,context)}
    if explicit:
        selected=sorted(explicit.intersection(dimensions))
        if selected and explicit.issubset(dimensions):return selected, []
        return dimensions, ['benefit_scope_unclear: 条目用途与文件分类不一致']
    if len(dimensions)>1:
        return dimensions, ['benefit_scope_unclear: 多维政策条目缺少明确的用途依据']
    return dimensions, []


def _gate(db, document, classification, now):
    from app.services.source_document_classifier import POLICY_TYPES
    from app.services.document_calibration_policy import POLICY_AUTO_ENABLED
    reasons=[];meta=document.metadata_json or {};text=document.content_text or ''
    if classification['document_type'] not in POLICY_TYPES:
        reasons.append('not_formal_policy: 文档类型或正式政策语义不明确')
    elif not classification.get('hierarchy_version') and classification.get('requires_human_confirmation'):
        reasons.append('classification_calibration: 文档类型仍待人工确认')
    from app.services.policy_safety_classifier import POLICY_DECISION_THRESHOLD
    assessment = classification.get('policy_assessment') or {}
    policy_score = assessment.get('policy_confidence', classification.get('policy_confidence', 0))
    if (not assessment.get('is_policy', classification.get('is_policy', False))
            or not isinstance(policy_score, (int, float)) or policy_score < POLICY_DECISION_THRESHOLD
            or classification.get('primary_type') != 'policy'):
        reasons.append('policy_safety: 独立政策安全判定未通过，需核对政策属性与正向证据')
    if not POLICY_AUTO_ENABLED:
        reasons.append('policy_calibration: 人工校准未支持自动正式关系，需逐项确认')
    if classification.get('risk_level') == 'HIGH_RISK':
        reasons.append('high_risk_document: 修订、更正或延期需人工确认')
    if not _official(db, document): reasons.append('official_source: 不是可确认的本校官方来源或附件')
    if not document.publisher or not document.publisher.strip(): reasons.append('publisher_missing: 缺少发布机构')
    if not document.is_verified or document.verification_status not in {'official_domain_verified','verified_manual','verified_official','verified_multi_source','authority_confirmed','school_confirmed'}:
        reasons.append('source_unverified: 缺少既有官方来源验证记录')
    if not text.strip(): reasons.append('missing_content: 缺少可读取的政策正文')
    elif len(re.sub(r'\s+', '', text)) < 35 or not (re.search(r'目录|名单|办法|细则|认定|加分|学分|奖励', text) or (re.search(r'(?:竞赛|赛事)名称',text) and re.search(r'目录|名录|名单|认定',document.title))):
        reasons.append('policy_semantics_unclear: 正文不足以确认完整政策或名单')
    if meta.get('needs_ocr') or 'ocr' in (document.parser_type or '').lower(): reasons.append('ocr: 文本可靠性需要人工确认')
    if meta.get('attachment_missing'): reasons.append('attachment_missing: 政策附件缺失')
    if document.attachment_url and not meta.get('attachment_missing'):
        attachment = db.scalar(select(PolicyAttachment).where(PolicyAttachment.policy_document_id==document.id, PolicyAttachment.source_url==document.attachment_url))
        text_parser = any(k in (document.parser_type or '').lower() for k in ['pdf', 'fitz', 'doc', 'excel', 'xls', 'ooxml'])
        if (attachment and (attachment.parse_status!='parsed' or not attachment.text_content or attachment.error_message)) or (not text_parser and not (attachment and attachment.text_content and attachment.parse_status=='parsed')):
            reasons.append('attachment_missing: 未保存可核对的附件文本层')
    if not document.effective_from or not document.is_current:
        reasons.append('validity_unclear: 缺少政策生效依据或当前有效状态')
    if document.effective_from and _utc(document.effective_from)>now: reasons.append('not_effective: 政策尚未生效')
    if document.effective_until and _utc(document.effective_until)<now: reasons.append('expired: 政策已经失效')
    if re.search(r'征求意见|草案|拟认定|拟修订',document.title): reasons.append('draft_policy: 草案不是生效文件')
    scope=meta.get('relation_scope') or {}
    if scope.get('revoked') or meta.get('superseded_by'): reasons.append('superseded: 已存在废止或替代依据')
    school=db.get(University,document.university_id)
    if document.scope_type not in {'university','college','major'} or (document.scope_type=='college' and not document.college_id) or (document.scope_type=='major' and not document.major_id):
        reasons.append('scope_unclear: 政策适用范围身份不完整')
    if document.scope_type=='university' and '学院' in (document.title+' '+(document.publisher or '')).replace(getattr(school,'name',''), ''):
        reasons.append('scope_unclear: 学院政策不能扩大为全校政策')
    if document.scope_type=='university' and re.search(r'(?:仅限|仅适用|适用于|面向)[^。；\n]{0,35}(?:学院|本院)[^。；\n]{0,15}(?:学生|本科生|研究生)',text.replace(getattr(school,'name',''),'')):
        reasons.append('scope_unclear: 正文将适用对象限制在学院范围')
    if document.scope_type!='major' and re.search(r'(?:仅限|仅适用|适用于|面向)[^。；\n]{0,45}专业[^。；\n]{0,15}(?:学生|本科生|研究生)',text):
        reasons.append('scope_unclear: 正文将适用对象限制在专业范围')
    if document.college_id:
        college=db.get(College,document.college_id)
        if not college or college.university_id != document.university_id: reasons.append('scope_unclear: 学院不属于该学校')
    if not _student_scope(document):
        reasons.append('student_scope_unclear: 缺少适用学生范围')
    return list(dict.fromkeys(reasons))


def _evidence_blockers(reasons):
    # Lack of automation authority does not prove that a policy expired or its
    # existing evidence changed. Keep those facts separate in persistence.
    return [r for r in reasons if not r.startswith(('classification_calibration:', 'policy_calibration:', 'policy_safety:'))]


def _version_family(document):
    # Explicit metadata family is descriptive only; never authorizes supersession.
    text=document.title
    text=re.sub(r'20\d{2}\s*年?|第[一二三四五六七八九十\d]+版|修订版|修订|最新版|最新|[（）()\s]','',text)
    return text


def _explicit_replacement(text, title):
    # The cancellation verb must govern this exact old title within one sentence.
    for sentence in re.split(r"[。；;\n]", text):
        if re.search(r'(?:不|未|无|尚未|暂不|不得|并非|无需)[^。；;]{0,6}(?:废止|替代|失效)',sentence):continue
        escaped = re.escape(title)
        if re.search(r"(?:废止|替代)[《\s]*" + escaped + r"[》]?", sentence) or re.search(escaped + r"[》]?\s*(?:同时|即行|予以|自动)?(?:废止|失效)", sentence):
            return True
    return False


def _conflicts(db, document, dimensions):
    peers=list(db.scalars(select(PolicyDocument).where(PolicyDocument.university_id==document.university_id,
        PolicyDocument.id!=document.id,PolicyDocument.scope_type==document.scope_type)))
    result=[]
    for peer in peers:
        if (peer.college_id,peer.major_id)!=(document.college_id,document.major_id): continue
        if (peer.metadata_json or {}).get('superseded_by')==document.id: continue
        if not set(_dimensions(_classification(peer))) & set(dimensions): continue
        if _version_family(peer)!=_version_family(document) and not _explicit_replacement(document.content_text or '',peer.title): continue
        if peer.content_text==document.content_text: continue
        if peer.effective_until and document.effective_from and _utc(peer.effective_until)<_utc(document.effective_from): continue
        if document.effective_until and peer.effective_from and _utc(document.effective_until)<_utc(peer.effective_from): continue
        # Missing effective boundaries are a reason to review, not proof of disjoint versions.
        result.append(peer)
    return result


def _saved_attachment(db, document, now):
    """Read already-collected files only; never fetch or accept a request path."""
    from app.services.policy_list_extractor import parse_policy_file
    meta=document.metadata_json or {}
    attachment=db.scalar(select(PolicyAttachment).where(PolicyAttachment.policy_document_id==document.id,
        PolicyAttachment.source_url==document.attachment_url)) if document.attachment_url else None
    local=meta.get('local_path') or ((attachment.metadata_json or {}).get('local_path') if attachment else None)
    if not local:return None,[],None
    path=Path(local)
    if not path.is_absolute():path=PROJECT_ROOT/path
    path=path.resolve()
    if not path.is_relative_to(RAW_ROOT.resolve()) or not path.is_file():
        return None,['attachment_unavailable: 已保存附件缺失或路径不在原始资料目录'],None
    digest=sha256(path.read_bytes()).hexdigest()
    if attachment and attachment.file_hash and re.fullmatch(r'[a-fA-F0-9]{64}',attachment.file_hash) and digest!=attachment.file_hash.lower():
        return None,['attachment_unavailable: 已保存附件哈希不一致'],None
    parsed=parse_policy_file(path)
    info={'local_path':str(path.relative_to(RAW_ROOT.resolve())),'file_sha256':digest,
        'entry_count':len(parsed['entries']),'parser_type':parsed['parser_type']}
    if parsed['error'] or parsed['needs_ocr'] or not parsed['content_text']:
        return None,['attachment_unavailable: 附件无法可靠读取文本层'],info
    with reviewed_write(db):
        document.content_text=parsed['content_text'];document.parser_type=parsed['parser_type']
        if attachment:
            attachment.text_content=parsed['content_text'];attachment.parse_status='parsed'
            attachment.parsed_at=now;attachment.error_message=None
    return parsed,[],info


def _analysis_item(db, doc):
    from app.services.document_calibration_policy import POLICY_AUTO_ENABLED
    school=db.get(University,doc.university_id)
    meta=doc.metadata_json or {}
    analysis=deepcopy(meta.get('policy_automation'))
    # A later document can retire this document without rerunning its old analysis.
    # Report present validity rather than replaying the cached success counters.
    if analysis:
        if not POLICY_AUTO_ENABLED:
            analysis['historical_automatic_relations'] = analysis.get('automatic_relations', 0)
            analysis['automatic_relations'] = 0
            analysis['recognized_relations'] = analysis.get('human_confirmed_relations', 0)
            analysis['requires_human_confirmation'] = True
            analysis['automation_authorized'] = False
            reason = 'policy_calibration: 人工校准未支持自动正式关系，需逐项确认'
            analysis['blocking_reasons'] = list(dict.fromkeys([*analysis.get('blocking_reasons', []), reason]))
            for entry in analysis.get('entries', []):
                if entry.get('relation_status') == 'AUTO_RECOGNIZED':
                    entry['relation_status'] = 'NEEDS_QUICK_CONFIRM'
                    entry['verification_method'] = None
                    entry['blocking_reasons'] = list(dict.fromkeys([*entry.get('blocking_reasons', []), reason]))
        stale=[]
        if meta.get('policy_version_conflict'):stale.append('policy_version_conflict: 同范围新旧政策未明确替代关系')
        if meta.get('superseded_by'):stale.append('superseded: 已被后续政策替代，仅保留历史依据')
        if analysis.get('source_sha256')!=sha256((doc.content_text or '').encode()).hexdigest():
            stale.append('source_changed: 来源正文已变化，需重新分析')
        if stale:
            analysis['automatic_relations']=analysis['recognized_relations']=analysis['human_confirmed_relations']=0
            analysis['requires_human_confirmation']=any(not r.startswith('superseded:') for r in stale)
            analysis['blocking_reasons']=list(dict.fromkeys([*analysis.get('blocking_reasons',[]),*stale]))
            for entry in analysis.get('entries',[]):
                entry['blocking_reasons']=list(dict.fromkeys([*entry.get('blocking_reasons',[]),*stale]))
                entry['relation_status']='NEEDS_HUMAN_REVIEW' if analysis['requires_human_confirmation'] else 'HISTORICAL'
    return {'id':doc.id,'title':doc.title,'source_url':doc.source_url,'university_id':doc.university_id,
        'school_name':school.name if school else None,'classification':_classification(doc),'analysis':analysis}


class PolicyAutomationService:
    @staticmethod
    def list_policies(db, *, limit=50, offset=0):
        rows=list(db.scalars(select(PolicyDocument).order_by(PolicyDocument.id)))
        return {'items':[_analysis_item(db,p) for p in rows[offset:offset+limit]],'total':len(rows)}

    @staticmethod
    def analyze(db, identity, *, admin, now=None):
        from app.services.document_policy_service import require_admin
        from app.services.policy_list_extractor import analyze_policy_content
        from app.services.policy_competition_matcher import match_policy_competition
        actor=require_admin(db,admin);now=_utc(now or datetime.now(timezone.utc))
        # Reserve SQLite writes before reading mutable policy/version snapshots.
        connection=db.connection()
        if connection.dialect.name=='sqlite' and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        with db.begin_nested():
            doc=db.scalar(select(PolicyDocument).where(PolicyDocument.id==identity).with_for_update().execution_options(populate_existing=True))
            if doc is None:raise HTTPException(404,'政策文档不存在')
            attachment_extraction, attachment_blockers, attachment_info=_saved_attachment(db,doc,now)
            classification=_classification(doc);dimensions=_dimensions(classification)
            blockers=[*_gate(db,doc,classification,now),*attachment_blockers]
            extraction=analyze_policy_content(doc.content_text or '',format='html' if '<table' in (doc.content_text or '').lower() or '<li' in (doc.content_text or '').lower() else 'pdf' if 'pdf' in (doc.parser_type or '') else 'text',title=doc.title) if dimensions else {'entries':[],'extraction_complete':False,'extraction_warnings':[]}
            if dimensions and attachment_extraction is not None:extraction=attachment_extraction
            extracted=extraction['entries']
            if dimensions and not extraction['extraction_complete']:blockers.append('extraction_incomplete: 名单存在无法可靠解析的条目')
            # Unverified new policy evidence has no authority to retire or
            # invalidate a previously verified policy. A calibration hold alone
            # is different: it blocks new automatic relations, not valid history.
            can_affect_versions = bool(classification.get('is_policy')
                and not any(r.startswith('policy_safety:') for r in blockers)
                and not _evidence_blockers(blockers))
            peers=_conflicts(db,doc,dimensions) if dimensions and can_affect_versions else []
            superseded=[]
            unresolved=[]
            for peer in peers:
                # Require an explicit verbatim old title and cancellation statement, not mere newer year.
                explicit=bool(_explicit_replacement(doc.content_text or '',peer.title) and doc.published_at and peer.published_at and _utc(doc.published_at)>_utc(peer.published_at))
                (superseded if explicit and not _evidence_blockers(blockers) else unresolved).append(peer)
            if unresolved:blockers.append('policy_version_conflict: 同范围新旧政策未明确替代关系')
            if not extracted and dimensions:blockers.append('no_extractable_entries: 没有可靠可提取的赛事条目')
            entries=[]
            for extracted_entry in extracted:
                match=match_policy_competition(db,extracted_entry['raw_competition_name'])
                confirmed=((doc.metadata_json or {}).get('human_match_confirmations') or {}).get(extracted_entry['raw_competition_name'])
                if confirmed and confirmed.get('content_sha256')==sha256((doc.content_text or '').encode()).hexdigest():
                    from app.models import Competition
                    target=db.get(Competition,confirmed['competition_id'])
                    if target and target.is_competition and not target.is_demo and target.status=='active':
                        match={**match,'matched_competition_id':target.id,'match_status':'HUMAN_CONFIRMED',
                            'match_confidence':1.0,'match_reason':'human_confirmed','normalized_name':target.name,
                            'human_match_reviewer':confirmed['reviewer'],'human_match_at':confirmed['confirmed_at']}
                entry_dimensions, scope_blockers=_entry_dimensions(extracted_entry,dimensions)
                for dimension in entry_dimensions:
                    reasons=[*blockers,*scope_blockers]
                    if match['match_status'] not in {'AUTO_MATCHED','HUMAN_CONFIRMED'}:reasons.append('ambiguous_match: 赛事名称需人工匹配')
                    entries.append({**extracted_entry,**match,'school_id':doc.university_id,'policy_document_id':doc.id,
                        'recognition_type':dimension,'effective_from':_iso(doc.effective_from),'effective_to':_iso(doc.effective_until),
                        'source_title':doc.title,'source_url':doc.attachment_url or doc.source_url,'publisher':doc.publisher,'published_at':_iso(doc.published_at),
                        'verification_method':('HUMAN_POLICY_MATCH' if match['match_reason']=='human_confirmed' else 'AUTO_POLICY_MATCH') if not reasons else None,
                        'relation_status':('HUMAN_RECOGNIZED' if match['match_reason']=='human_confirmed' else 'AUTO_RECOGNIZED') if not reasons else ('NEEDS_HUMAN_REVIEW' if _evidence_blockers(reasons) else 'NEEDS_QUICK_CONFIRM'),'blocking_reasons':reasons})
            result={'entries':entries,'automatic_relations':sum(not e['blocking_reasons'] and e['match_reason']!='human_confirmed' for e in entries),
                'recognized_relations':sum(not e['blocking_reasons'] for e in entries),
                'human_confirmed_relations':sum(not e['blocking_reasons'] and e['match_reason']=='human_confirmed' for e in entries),
                'requires_human_confirmation':bool(blockers or any(e['blocking_reasons'] for e in entries)),
                'blocking_reasons':blockers,'conflicts':[{'policy_document_id':p.id,'title':p.title} for p in unresolved],
                'superseded_policy_ids':[p.id for p in superseded],'classification':classification,'analyzed_at':now.isoformat(),
                'attachment_replay':attachment_info,'source_sha256':sha256((doc.content_text or '').encode()).hexdigest(),'extraction_complete':extraction['extraction_complete'],'extraction_warnings':extraction['extraction_warnings']}
            with reviewed_write(db):
                for peer in [*unresolved,*superseded]:
                    before={'is_current':peer.is_current,'metadata':deepcopy(peer.metadata_json)}
                    meta=deepcopy(peer.metadata_json or {});peer.is_current=False
                    if peer in superseded:
                        meta['superseded_by']=doc.id
                        peer.verification_status='superseded'
                        meta['supersession_evidence']={'source_url':doc.source_url,'old_title':peer.title,'new_title':doc.title}
                        if doc.effective_from:peer.effective_until=doc.effective_from
                    else:
                        meta['policy_version_conflict']={'other_policy_document_id':doc.id,'detected_at':now.isoformat()}
                        peer.verification_status='needs_review'
                    peer.metadata_json=meta
                    db.add(AdminAuditLog(admin_id=actor,action='policy_version_review',object_type='policy_document',object_id=peer.id,before=before,
                        after={'is_current':False,'superseded_by':meta.get('superseded_by'),'conflict':peer in unresolved},created_at=now))
                meta=deepcopy(doc.metadata_json or {});meta['policy_automation']=result
                evidence_blockers = _evidence_blockers(blockers)
                if evidence_blockers:
                    doc.is_current=False
                    doc.verification_status='needs_review'
                elif not blockers:
                    oldscope=meta.get('relation_scope') or {}
                    text=doc.content_text or ''
                    student=_student_scope(doc)
                    meta['relation_scope']={**oldscope,'scope_type':doc.scope_type,'student_scope':student,
                        'current_validity_confirmed':True,'effective_from':_iso(doc.effective_from),'effective_until':_iso(doc.effective_until)}
                    doc.verification_status='verified_official';doc.is_current=True
                doc.metadata_json=meta
                # If evidence now fails, prior automatic relations must no longer remain public.
                eligible={(e['raw_competition_name'],e['recognition_type'],e['matched_competition_id']) for e in entries if not _evidence_blockers(e['blocking_reasons'])}
                for old in db.scalars(select(Recognition).where(Recognition.policy_document_id==doc.id)):
                    try: prior_evidence=json.loads(old.evidence_text or '{}')
                    except (ValueError,TypeError): continue
                    if not isinstance(prior_evidence,dict) or prior_evidence.get('verification_method') not in {'AUTO_POLICY_MATCH','HUMAN_POLICY_MATCH'}:continue
                    stale=prior_evidence.get('source_sha256')!=result['source_sha256'] or (prior_evidence.get('matched_raw_name'),old.usage_type,old.competition_id) not in eligible
                    if (evidence_blockers or stale) and not old.needs_manual_review:
                        old.needs_manual_review=True
                        db.add(AdminAuditLog(admin_id=actor,action='policy_relation_invalidated',object_type='policy_recognition',object_id=old.id,
                            before={'needs_manual_review':False},after={'needs_manual_review':True,'reason':'evidence_or_policy_changed'},created_at=now))
                for entry in entries:
                    if entry['blocking_reasons']:continue
                    evidence={**entry,'matched_raw_name':entry['raw_competition_name'],'policy_title':doc.title,
                        'policy_url':doc.source_url,'source_publisher':doc.publisher,'rule_version':classification.get('rule_version'),
                        'source_sha256':result['source_sha256'],'school_scope':doc.scope_type,'college_id':doc.college_id,'major_id':doc.major_id}
                    digest=sha256(json.dumps({'document':doc.id,'source_hash':result['source_sha256'],'raw':entry['raw_competition_name'],
                        'competition':entry['matched_competition_id'],'type':entry['recognition_type']},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    existing=db.scalar(select(Recognition).where(Recognition.policy_document_id==doc.id,Recognition.evidence_hash==digest))
                    if existing is None:
                        relation=Recognition(competition_id=entry['matched_competition_id'],policy_document_id=doc.id,university_id=doc.university_id,
                            college_id=doc.college_id,major_id=doc.major_id,year=doc.year,recognition_status='recognized',usage_type=entry['recognition_type'],
                            evidence_text=json.dumps(evidence,ensure_ascii=False),evidence_hash=digest,evidence_section=str(entry.get('locator',''))[:255],
                            confidence=entry['match_confidence'],needs_manual_review=False,is_demo=doc.is_demo)
                        db.add(relation);db.flush()
                        db.add(AdminAuditLog(admin_id=actor,action='human_policy_match' if entry['match_reason']=='human_confirmed' else 'auto_policy_match',object_type='policy_recognition',object_id=relation.id,
                            before=None,after=evidence,created_at=now))
                db.flush()
            # Policy candidates require confirmation but never masquerade as field candidates.
            oldqueue=list(db.scalars(select(ReviewQueue).where(ReviewQueue.item_type=='policy_match',ReviewQueue.policy_document_id==doc.id)))
            bykey={json.loads(row.raw_value or '{}').get('entry_key'):row for row in oldqueue}
            current_keys={sha256((e['raw_competition_name']+'|'+e['recognition_type']).encode()).hexdigest() for e in entries}
            for key, prior in bykey.items():
                if key not in current_keys:prior.status='obsolete_evidence'
            for e in entries:
                key=sha256((e['raw_competition_name']+'|'+e['recognition_type']).encode()).hexdigest()
                pending=bykey.get(key)
                if e['blocking_reasons']:
                    if pending is None:
                        pending=ReviewQueue(item_type='policy_match',policy_document_id=doc.id,university_id=doc.university_id,reason='政策赛事匹配或证据待确认',status='pending')
                        db.add(pending)
                    pending.status='pending'
                    pending.raw_value=json.dumps({'entry_key':key,**e},ensure_ascii=False);pending.source_url=e['source_url']
                elif pending is not None:pending.status='resolved_automatically'
            db.flush()
            return result

    @staticmethod
    def confirm_match(db, identity, raw_name, competition_id, reason, *, admin, now=None):
        from app.services.document_policy_service import require_admin
        from app.models import Competition
        actor=require_admin(db,admin);now=_utc(now or datetime.now(timezone.utc))
        if not reason or not reason.strip():raise HTTPException(422,'请填写匹配确认依据')
        doc=db.get(PolicyDocument,identity)
        if doc is None:raise HTTPException(404,'政策文档不存在')
        analysis=(doc.metadata_json or {}).get('policy_automation') or {}
        entry=next((e for e in analysis.get('entries',[]) if e['raw_competition_name']==raw_name),None)
        if not entry:raise HTTPException(409,'请先分析并选择真实提取的名单条目')
        if analysis.get('source_sha256')!=sha256((doc.content_text or '').encode()).hexdigest():
            raise HTTPException(409,'政策正文已变化，请重新分析')
        target=db.get(Competition,competition_id)
        if not target or not target.is_competition or target.is_demo or target.status!='active':
            raise HTTPException(422,'只能匹配既有正式赛事')
        with db.begin_nested():
            meta=deepcopy(doc.metadata_json or {})
            confirmations=meta.setdefault('human_match_confirmations',{})
            before=confirmations.get(raw_name)
            record={'competition_id':competition_id,'reviewer':actor,'confirmed_at':now.isoformat(),
                'reason':reason.strip(),'content_sha256':analysis['source_sha256']}
            confirmations[raw_name]=record
            with reviewed_write(db):doc.metadata_json=meta;db.flush()
            db.add(AdminAuditLog(admin_id=actor,action='policy_match_confirmed',object_type='policy_document',object_id=doc.id,
                before=before,after={'raw_competition_name':raw_name,**record},created_at=now))
            db.flush()
            return PolicyAutomationService.analyze(db,identity,admin=admin,now=now)
