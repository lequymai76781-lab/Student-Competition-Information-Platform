"""Freeze real Golden Set evidence, using only existing files and read-only SQLite.

No classifier, network, ORM, annotation database, or application write is invoked.
Repeated execution verifies identical artifacts and refuses a changed manifest.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / '.codex-qa/document-policy/replay-verified'
OUT = ROOT / '.codex-qa/golden-set-20261001'
DATASET_ID = 'golden-20261001-v1'
POLICY_IDS = [9, 1, 2, 3, 4, 6, 7, 8, 10, 11, 13, 15, 16, 21, 26, 41, 61, 5, 36, 63]
AUTO_AUDIT_IDS = [1, 3, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34, 37, 40, 43, 46, 49, 54, 59]
POLICY_TYPES = {
    'policy_recognition_document', 'award_policy_document',
    'comprehensive_evaluation_policy_document', 'postgraduate_policy_document',
    'innovation_credit_policy_document',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readonly(path):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    assert connection.execute('PRAGMA query_only').fetchone()[0] == 1
    return connection


def records(connection, sql):
    return [dict(row) for row in connection.execute(sql)]


def loads(value, default=None):
    if not value:
        return {} if default is None else default
    return json.loads(value) if isinstance(value, str) else value


def plain(value):
    """Preserve stored evidence as text; discard non-printing control characters."""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(value or ''))


def source_metadata(row):
    document = loads(row['raw_value'])
    source = {}
    # Original ingestion evidence is not a generated summary. Use only explicit
    # source fields; evidence_notes are never promoted to document body.
    for raw in [row.get('evidence_text'), document.get('description')]:
        try:
            payload = json.loads((raw or '').split('\n', 1)[1])
            original = payload.get('input') or {}
            source.update(original.get('source') or original)
        except (ValueError, IndexError, TypeError, AttributeError):
            pass
    proposals = document.get('proposals') or []
    context = document.get('collection_context') or {}
    source.update(context or (proposals[0].get('source') if proposals else {}) or {})
    return source


def frozen_prediction(classification):
    return {
        'predicted_type': classification['document_type'],
        'predicted_confidence': classification['confidence'],
        'predicted_secondary_types': classification.get('secondary_types', []),
        'matched_rules': classification.get('matched_rules', []),
        'classification_reason': classification.get('classification_reason'),
        'classification_status': classification.get('classification_status'),
        'informational_only': bool(classification.get('informational_only')),
        'risk_level': classification.get('risk_level'),
        'rule_version': classification.get('rule_version'),
    }


def distribution(values):
    return dict(sorted(Counter(values).items(), key=lambda pair: str(pair[0])))


def queue_analysis(original_rows, replay_rows, sources, policies):
    assert [r['id'] for r in original_rows] == [r['id'] for r in replay_rows]
    details = []
    for before, row in zip(original_rows, replay_rows):
        document = loads(row['raw_value'])
        original = loads(before['raw_value'])
        assert original.get('proposals') == document.get('proposals')
        assert original.get('decisions') == document.get('decisions')
        context = document.get('collection_context') or {}
        classification = document['document_classification']
        proposals = document.get('proposals') or []
        flags = context.get('flags') or []
        factors = {
            'classification_needs_human': classification['classification_status'] != 'AUTO_CLASSIFIED',
            'field_proposals': bool(proposals),
            'school_mapping': context.get('kind') == 'school_mapping',
            'conflict_or_uncertainty_flags': bool(flags),
            'policy_document_prediction': classification['document_type'] in POLICY_TYPES,
            'high_risk': classification['risk_level'] == 'HIGH_RISK',
        }
        # Exact combination groups preserve overlap; no additive factor-count claim.
        combination = '|'.join(key for key, value in factors.items() if value) or 'no_listed_factor'
        details.append({
            'candidate_id': row['id'], 'source_url': row['source_url'],
            'original_status': before['status'], 'replay_status': row['status'],
            'predicted_type': classification['document_type'],
            'classification_status': classification['classification_status'],
            'proposal_count': len(proposals),
            'proposal_fields': [p['field_name'] for p in proposals],
            'collection_kind': context.get('kind'), 'flags': flags,
            'informational_only': bool(classification['informational_only']),
            'source_failure_reason': context.get('source_failure_reason'),
            'access_status': context.get('access_status'),
            'participation_evidence': bool(document.get('participation_evidence')),
            'factors': factors, 'factor_combination': combination,
        })
    keys = list(details[0]['factors'])
    pending = [row for row in details if row['replay_status'] == 'pending']
    source_info = [s for s in sources if s['classification']['informational_only']]
    info_urls = {s['source_url'] for s in source_info}
    linked_info_rows = [row for row in details if row['source_url'] in info_urls]
    matrix = {}
    for left in keys:
        matrix[left] = {right: sum(r['factors'][left] and r['factors'][right] for r in pending) for right in keys}
    return {
        'basis': 'Stored 254 candidate rows and their frozen replay classification; no new replay or classification.',
        'original_status_counts': distribution(r['original_status'] for r in details),
        'replay_status_counts': distribution(r['replay_status'] for r in details),
        'total_rows': len(details), 'remaining_pending': len(pending),
        'removed_or_deleted_rows': 0,
        'informational_candidate_ids': [r['candidate_id'] for r in details if r['replay_status'] == 'informational'],
        'classification_status_counts': distribution(r['classification_status'] for r in details),
        'predicted_type_counts': distribution(r['predicted_type'] for r in details),
        'classification_subtask_auto_count': sum(r['classification_status'] == 'AUTO_CLASSIFIED' for r in details),
        'classification_subtask_auto_fraction': sum(r['classification_status'] == 'AUTO_CLASSIFIED' for r in details) / len(details),
        'main_queue_pending_reduction_count': len(details) - len(pending),
        'main_queue_pending_reduction_fraction': (len(details) - len(pending)) / len(details),
        'proposal_count_distribution': distribution(r['proposal_count'] for r in details),
        'proposal_field_counts': distribution(p for r in details for p in r['proposal_fields']),
        'total_proposals': sum(r['proposal_count'] for r in details),
        'rows_with_proposals': sum(bool(r['proposal_count']) for r in details),
        'rows_without_proposals': sum(not r['proposal_count'] for r in details),
        'collection_kind_counts': distribution(r['collection_kind'] or 'no_collection_context' for r in details),
        'zero_proposal_school_mapping_count': sum(not r['proposal_count'] and r['factors']['school_mapping'] for r in details),
        'zero_proposal_non_school_mapping_count': sum(not r['proposal_count'] and not r['factors']['school_mapping'] for r in details),
        'stored_flag_counts': distribution(flag for r in details for flag in r['flags']),
        'pending_factor_counts_overlapping': {key: sum(r['factors'][key] for r in pending) for key in keys},
        'pending_pairwise_factor_overlaps': matrix,
        'pending_exact_mutually_exclusive_factor_combinations': distribution(r['factor_combination'] for r in pending),
        'all_exact_mutually_exclusive_factor_combinations': distribution(r['factor_combination'] for r in details),
        'source_only_informational': {
            'source_replay_denominator': len(sources), 'unique_source_count': len(source_info),
            'linked_candidate_rows': len(linked_info_rows),
            'linked_pending_rows': sum(r['replay_status'] == 'pending' for r in linked_info_rows),
            'linked_informational_rows': sum(r['replay_status'] == 'informational' for r in linked_info_rows),
            'source_ids': [s['source_id'] for s in source_info],
            'linked_candidate_ids': [r['candidate_id'] for r in linked_info_rows],
            'limitation': '13/200 counts deduplicated source-only predictions; 2/254 counts routed candidate rows after proposal, school relation and flag safety guards. These denominators are different.',
        },
        'historical_policy_workload_separate_from_254': {
            'documents': len(policies), 'typed_entries': sum(len(p['entries']) for p in policies),
            'auto_relations': sum(p['automatic_relations'] for p in policies),
            'entry_match_status_counts': distribution(e['match_status'] for p in policies for e in p['entries']),
            'documents_requiring_human': sum(p['requires_human_confirmation'] for p in policies),
            'conflict_document_count': sum(bool(p.get('conflicts')) for p in policies),
            'limitation': 'Separate 76-document policy replay population, not 76 additional members of the original 254 field-candidate queue.',
        },
        'interpretation': [
            'AUTO_CLASSIFIED resolves the document classification subtask only; proposals remain unapproved and undecided.',
            'Zero proposals is not sufficient to remove a candidate: school mapping, flags, policy or unclear classification may still require review.',
            'Flags include edition_uncertain and DUPLICATE_SUSPECTED; they are stored review signals, not verified factual conflicts.',
            'Factor counts overlap; exact factor-combination groups partition all 252 remaining pending rows.',
            'No candidate is removed, no facts approved, no thresholds altered by this analysis.',
        ],
        'candidates': details,
    }


def immutable_write(path, payload):
    if path.exists():
        if path.read_bytes() != payload:
            raise SystemExit(f'Refusing to overwrite changed immutable artifact: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(payload)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def main():
    original_csv = REPLAY / 'golden-to-label.csv'
    inputs = [ROOT / 'data/v02.sqlite', ROOT / '.codex-qa/mid-scale/candidates.sqlite',
              original_csv, REPLAY / 'source-replay.json', REPLAY / 'policy-replay.json',
              REPLAY / 'replay.sqlite', REPLAY / 'policy-replay.sqlite']
    before = {str(p.relative_to(ROOT).as_posix()): digest(p) for p in inputs}
    with original_csv.open(encoding='utf-8-sig', newline='') as stream:
        gold = list(csv.DictReader(stream))
    assert len(gold) == len({r['source_id'] for r in gold}) == 100
    assert all(not r[k] for r in gold for k in ['label', 'label_provenance', 'reviewer', 'reviewed_at'])
    sources = json.loads((REPLAY / 'source-replay.json').read_text(encoding='utf-8'))
    policies = json.loads((REPLAY / 'policy-replay.json').read_text(encoding='utf-8'))
    source_index = {row['source_id']: row for row in sources}
    policy_index = {row['policy_document_id']: row for row in policies}
    with closing(readonly(inputs[1])) as db:
        original_rows = records(db, "SELECT * FROM review_queue WHERE item_type='field_candidate' ORDER BY id")
        candidate_schools = {r['id']: r['name'] for r in records(db, 'SELECT id,name FROM universities')}
    with closing(readonly(REPLAY / 'replay.sqlite')) as db:
        replay_rows = records(db, "SELECT * FROM review_queue WHERE item_type='field_candidate' ORDER BY id")
    with closing(readonly(ROOT / 'data/v02.sqlite')) as db:
        documents = {r['id']: r for r in records(db, 'SELECT * FROM policy_documents ORDER BY id')}
        schools = {r['id']: r['name'] for r in records(db, 'SELECT id,name FROM universities')}
    with closing(readonly(REPLAY / 'policy-replay.sqlite')) as db:
        auto = records(db, "SELECT * FROM admin_audit_logs WHERE action='auto_policy_match' ORDER BY id")
        relations = {r['id']: r for r in records(db, 'SELECT * FROM competition_policy_recognitions')}
        competitions = {r['id']: r for r in records(db, 'SELECT id,name FROM competitions')}
        aliases = records(db, 'SELECT * FROM competition_aliases WHERE is_verified=1')
        pending_policy_entries = db.execute("SELECT COUNT(*) FROM review_queue WHERE item_type='policy_match' AND status='pending'").fetchone()[0]
    row_index = {r['id']: r for r in original_rows}
    items = []
    for row in gold:
        frozen = source_index[row['source_id']]
        assert frozen['source_url'] == row['source_url']
        assert frozen['title'] == row['title']
        assert frozen.get('content_preview', '') == row['content_preview']
        document = documents.get(frozen.get('policy_document_id')) or {}
        metadata = [source_metadata(row_index[i]) for i in frozen.get('candidate_ids', []) if i in row_index]
        def explicit(key):
            return next((s[key] for s in metadata if s.get(key) not in (None, '')), None)
        school_name = schools.get(document.get('university_id'))
        school_name = school_name or explicit('school_name')
        school_name = school_name or next((candidate_schools.get(row_index[i].get('university_id')) for i in frozen.get('candidate_ids', []) if row_index.get(i, {}).get('university_id')), None)
        school_name = school_name or next(((s.get('university_notice') or {}).get('university_name') for s in metadata if (s.get('university_notice') or {}).get('university_name')), None)
        item = {
            'source_id': row['source_id'], 'source_url': row['source_url'], 'title': row['title'],
            'school_name': school_name,
            'publisher': frozen.get('publisher') or document.get('publisher') or explicit('publisher'),
            'published_at': document.get('published_at') or explicit('published_at'),
            'content_preview': plain(row['content_preview']),
            'content_text': plain(document.get('content_text') or row['content_preview']),
            'body_available': bool(frozen['body_available']),
            'origin': frozen['origin'], 'candidate_ids': frozen.get('candidate_ids', []),
            'policy_document_id': frozen.get('policy_document_id'),
            'metadata_provenance': 'Frozen replay source; explicit original policy document fields or original candidate source/collection metadata only.',
            **frozen_prediction(frozen['classification']),
        }
        items.append(item)
    assert sum(i['body_available'] for i in items) == 11
    policy_samples = []
    for identity in POLICY_IDS:
        doc, replay = documents[identity], policy_index[identity]
        assert not doc['is_demo']
        policy_samples.append({
            'audit_id': f'policy:{identity}', 'policy_document_id': identity,
            'title': doc['title'], 'school_name': schools[doc['university_id']],
            'school_id': doc['university_id'], 'publisher': doc['publisher'],
            'published_at': doc['published_at'], 'source_url': doc['source_url'],
            'attachment_url': doc['attachment_url'], 'content_preview': plain(doc['content_text'])[:3500],
            'content_text': plain(doc['content_text']), 'body_available': bool(doc['content_text']),
            'scope_type': doc['scope_type'], 'effective_from': doc['effective_from'],
            'effective_until': doc['effective_until'], 'verification_status': doc['verification_status'],
            'entries': replay['entries'], 'blocking_reasons': replay['blocking_reasons'],
            'requires_human_confirmation': replay['requires_human_confirmation'],
            'automatic_relations': replay['automatic_relations'],
            'extraction_complete': replay.get('extraction_complete'),
            'extraction_warnings': replay.get('extraction_warnings', []),
            'attachment_replay': replay.get('attachment_replay'),
            'source_sha256': replay.get('source_sha256'),
            'conflicts': replay.get('conflicts', []),
            'sampling_reason': 'Purposive coverage of observed document types, ordinary-notice controls, extraction and provenance/scope/validity blockers; policy 9 includes existing automatic relations.',
            **frozen_prediction(replay['classification']),
        })
    relation_samples = []
    auto_index = {r['id']: r for r in auto}
    assert len(auto) == 59
    for identity in AUTO_AUDIT_IDS:
        audit = auto_index[identity]
        entry = loads(audit['after'])
        relation = relations[audit['object_id']]
        doc = documents[entry['policy_document_id']]
        assert not relation['is_demo'] and not doc['is_demo']
        assert relation['competition_id'] == entry['matched_competition_id']
        assert relation['policy_document_id'] == entry['policy_document_id']
        assert relation['usage_type'] == entry['recognition_type']
        assert entry['verification_method'] == 'AUTO_POLICY_MATCH'
        assert entry['relation_status'] == 'AUTO_RECOGNIZED' and entry['match_confidence'] == 1.0
        assert not entry['blocking_reasons']
        competition_name = competitions[relation['competition_id']]['name']
        alias_proof = [a for a in aliases if a['competition_id'] == relation['competition_id'] and a['alias'] == entry['raw_competition_name']]
        assert entry['match_reason'] == 'name' or alias_proof
        relation_samples.append({
            'audit_id': f'relation:{relation["id"]}', 'relation_id': relation['id'],
            'auto_audit_log_id': identity, 'auto_audit_created_at': audit['created_at'],
            'title': doc['title'], 'policy_document_id': doc['id'],
            'school_name': schools[doc['university_id']], 'school_id': doc['university_id'],
            'publisher': entry['publisher'], 'published_at': entry['published_at'],
            'source_url': entry['source_url'], 'policy_url': doc['source_url'],
            'content_preview': plain(doc['content_text'])[:3500],
            'content_text': plain(doc['content_text']), 'entries': [entry],
            'competition_name': competition_name, 'competition_id': relation['competition_id'],
            'raw_competition_name': entry['raw_competition_name'],
            'recognition_type': entry['recognition_type'],
            'match_status': entry['match_status'], 'match_confidence': entry['match_confidence'],
            'match_reason': entry['match_reason'], 'source_sha256': entry['source_sha256'],
            'verification_method': entry['verification_method'], 'locator': entry['locator'],
            'evidence_text': plain(entry['evidence_text']), 'school_scope': entry['school_scope'],
            'effective_from': entry['effective_from'], 'effective_to': entry['effective_to'],
            'alias_evidence': alias_proof if entry['match_reason'] == 'verified_alias' else [],
            'persisted_relation': {k: relation[k] for k in ['id', 'competition_id', 'policy_document_id', 'university_id', 'usage_type', 'recognition_status', 'confidence', 'evidence_hash', 'evidence_section', 'needs_manual_review']},
            'sampling_reason': 'Deterministic spread across the existing 59 audit rows, including the single verified_alias match; one school/document and one recognition dimension only.',
        })
    analysis = queue_analysis(original_rows, replay_rows, sources, policies)
    analysis['historical_policy_workload_separate_from_254']['pending_policy_match_tasks'] = pending_policy_entries
    after = {str(p.relative_to(ROOT).as_posix()): digest(p) for p in inputs}
    assert before == after, 'Source artifacts changed during read-only preparation'
    provenance = {
        'original_csv': original_csv.relative_to(ROOT).as_posix(),
        'original_csv_sha256': before[original_csv.relative_to(ROOT).as_posix()],
        'input_sha256': before,
        'hash_verification': {name: {'before': value, 'after': after[name], 'unchanged': value == after[name]} for name, value in before.items()},
        'original_source_ids_in_order': [r['source_id'] for r in gold],
        'classification_sampling': 'Exactly the original 100 CSV source IDs and order; prior round-robin by predicted type, purposive and not population-representative.',
        'policy_sampling': {'population': 76, 'sample': 20, 'method': 'Fixed purposive coverage of all 9 observed document types, every document-level blocker family, ordinary notices and automatic relation document 9.', 'policy_document_ids': POLICY_IDS},
        'relation_sampling': {'population': 59, 'sample': 20, 'method': 'Fixed spread of auto audit IDs with verified_alias case explicitly included; not random.', 'auto_audit_log_ids': AUTO_AUDIT_IDS, 'population_policy_document_ids': sorted({loads(a['after'])['policy_document_id'] for a in auto}), 'population_recognition_types': distribution(loads(a['after'])['recognition_type'] for a in auto), 'limitation': 'All 59 available automatic relations come from Southeast University policy 9 and policy_recognition. Twenty samples cannot establish cross-school, cross-document or cross-dimension safety.'},
        'missing_metadata_policy': 'Leave missing data null or empty; no title-inferred publisher/date, fabricated summary, new crawl or automatic human labels.',
        'body_available_n': sum(i['body_available'] for i in items),
        'predicted_type_counts': distribution(i['predicted_type'] for i in items),
    }
    manifest = {'dataset_id': DATASET_ID, 'fixture_only': False, 'provenance': provenance,
                'items': items, 'audit_sets': {'policies': policy_samples, 'relations': relation_samples},
                'queue_analysis': {k: v for k, v in analysis.items() if k != 'candidates'}}
    assert len(policy_samples) == len({p['audit_id'] for p in policy_samples}) == 20
    assert len(relation_samples) == len({p['audit_id'] for p in relation_samples}) == 20
    assert [i['source_id'] for i in manifest['items']] == provenance['original_source_ids_in_order']
    forbidden = {'annotation', 'annotations', 'human_primary_type', 'human_secondary_types', 'label', 'label_provenance'}
    def validate_no_labels(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value), 'Human annotation keys must not be present in immutable source data'
            for child in value.values():
                validate_no_labels(child)
        elif isinstance(value, list):
            for child in value:
                validate_no_labels(child)
    validate_no_labels(manifest)
    manifest_bytes = encoded(manifest)
    report = make_report(manifest, analysis, hashlib.sha256(manifest_bytes).hexdigest())
    # Check every existing output before creating any new artifact.
    outputs = [(OUT / 'live/manifest.json', manifest_bytes),
               (OUT / 'queue-analysis.json', encoded(analysis)),
               (OUT / 'data-report.md', report.encode('utf-8'))]
    for path, payload in outputs:
        if path.exists() and path.read_bytes() != payload:
            raise SystemExit(f'Refusing to overwrite changed immutable artifact: {path}')
    for path, payload in outputs:
        immutable_write(path, payload)
    assert {str(p.relative_to(ROOT).as_posix()): digest(p) for p in inputs} == before
    print(json.dumps({'manifest': str(OUT / 'live/manifest.json'), 'items': len(items),
                      'policies': len(policy_samples), 'relations': len(relation_samples),
                      'body_available': provenance['body_available_n'], 'human_labels_created': 0,
                      'protected_and_input_hashes_unchanged': True,
                      'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest()}, ensure_ascii=False))


def make_report(manifest, analysis, manifest_sha256):
    provenance = manifest['provenance']
    pending = analysis['pending_factor_counts_overlapping']
    lines = [
        '# Golden Set 真实数据准备与只读队列分析 — 2026-10-01', '',
        '状态：READY_FOR_HUMAN；真实人工标注与审核均未创建，质量结论 BLOCKED。', '',
        f'- 数据集：`{DATASET_ID}`；manifest SHA-256：`{manifest_sha256}`。',
        '- 分类：严格保留原 CSV 的 100 个唯一 source_id 及顺序，机器预测冻结；未替换、未新增分类样本。',
        f'- 正文可用：{provenance["body_available_n"]}/100；89 条无已存正文，不用标题或 evidence_notes 生成摘要。',
        f'- 缺失学校 / 发布者 / 发布日期：{sum(not i["school_name"] for i in manifest["items"])} / {sum(not i["publisher"] for i in manifest["items"])} / {sum(not i["published_at"] for i in manifest["items"])}。缺失保留 null。',
        '- 附加已存政策全文为纯文本字段；前端必须按文本显示，不能解释为 HTML。', '',
        '## 100 条冻结预测分布（不是人工真值）', '',
        '| 预测类型 | 数量 |', '| --- | ---: |',
    ]
    lines.extend(f'| {key} | {value} |' for key, value in provenance['predicted_type_counts'].items())
    lines += ['', '## 20 份政策与 20 条自动关系', '',
        '- 政策采用目的性抽样，覆盖当前 76 份中的全部 9 个预测类型及每类文档级阻断原因，并保留普通通知/结果/other 对照。不能视为随机代表样本。',
        '- 政策 ID：' + ', '.join(map(str, POLICY_IDS)) + '。',
        '- 关系取既存 59 条 auto_policy_match 审计中的 20 条；保留源文档、条目定位、原始名称、目标赛事、置信度、维度及持久化关系证据。包含唯一 verified_alias 个案，其余为 name 精确匹配。',
        '- 59 条总体及 20 条样本全部来自东南大学政策 9，维度全部为 policy_recognition，置信度均为 1.0。样本不支持跨学校、跨文档、奖励/综测/推免/创新学分维度的安全结论。',
        '- policy:2 原记录为 local-source://；不能装作可联网访问的官方来源，原 URL 与阻断原因原样保留。',
        '- 既存文档中部分正文/日期/范围或完整附件仍不足；审核可明确选择 unsure。', '',
        '## 254 条主队列：分类完成不等于事实审核完成', '',
        f'- 原始 pending=254；既存 replay pending=252、informational=2；没有删除候选。实际主队列减少 2/254={2/254:.2%}。',
        '- informational 候选 ID：66、193。',
        f'- 分类子任务：{analysis["classification_status_counts"]}。AUTO_CLASSIFIED 112/254={112/254:.2%}，不等于 112 条事实通过。',
        f'- 字段 proposal 总数 {analysis["total_proposals"]}，{analysis["rows_with_proposals"]} 条有字段建议；{analysis["rows_without_proposals"]} 条无字段建议。全部 decisions 仍为空。',
        f'- school_mapping 共 {analysis["collection_kind_counts"].get("school_mapping", 0)} 条；零 proposal 且 school_mapping={analysis["zero_proposal_school_mapping_count"]}，零 proposal 且非 school_mapping={analysis["zero_proposal_non_school_mapping_count"]}。',
        f'- 待处理 252 条的重叠因素：{pending}。这些数不能相加。',
        f'- flags：{analysis["stored_flag_counts"]}；edition_uncertain 是届次不确定，DUPLICATE_SUSPECTED 是疑似重复，都不能宣称为已证实事实冲突。',
        f'- 200 条去重来源中 informational_only=13；关联候选 {analysis["source_only_informational"]["linked_candidate_rows"]} 条，其中仍 pending={analysis["source_only_informational"]["linked_pending_rows"]}、informational={analysis["source_only_informational"]["linked_informational_rows"]}。来源预测不带候选的字段/学校关系/flags 安全条件，不能把 13 直接从 254 中减掉。',
        '- 分类、事实建议、学校关系、政策语义与 flags 是不同审核子任务。完整交叉重叠矩阵与逐条 ID 见 queue-analysis.json。', '',
        '### 252 条 pending 的互斥组合（总和严格等于 252）', '',
        '| 因素组合 | 数量 |', '| --- | ---: |',
    ]
    lines.extend(f'| {key.replace("|", " + ")} | {value} |' for key, value in analysis['pending_exact_mutually_exclusive_factor_combinations'].items())
    assert sum(analysis['pending_exact_mutually_exclusive_factor_combinations'].values()) == 252
    lines += ['', '## 单独的历史政策工作量', '',
        '- 76 份政策、513 个解析条目、59 条已有自动关系、454 条 policy_match 待审核任务；76 份仍需人工确认，0 份记录了政策冲突。',
        '- 上述是另一份历史政策 replay 总体，不能混入原 254 条 field_candidate 的分母。59/513 仅反映关系判定覆盖，不能证明准确率。', '',
        '## 原文件未修改证明', '',
        '所有 SQLite 连接使用 mode=ro 与 PRAGMA query_only=ON。未调用 classifier、replay、自动政策服务，未发 HTTP 请求；未创建或修改 annotation/auth DB。', '',
        '| 输入 | 准备前后 SHA-256（相同） |', '| --- | --- |',
    ]
    lines.extend(f'| {name} | `{value}` |' for name, value in provenance['input_sha256'].items())
    lines += ['', '脚本再次运行仅验证完全相同的字节；若任何既存输出内容不同则拒绝覆盖。未标注阶段 accuracy/precision/recall/F1、错误自动放行率及生产阈值建议均不可报告为有效结果。', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
