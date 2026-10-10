# Document Policy Automation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development and dispatching-parallel-agents for independent file sets. User explicitly authorized execution; no repeated approval gates.

**Goal:** Explainable document classification, evidence-backed policy extraction/matching, conservative automatic relationships, and measurable queue noise reduction.
**Architecture:** Pure classification and extraction/matching modules feed a transaction-owned integration service. Existing persisted policy/candidate metadata and audit records carry provenance without schema migration.
**Tech Stack:** Python/FastAPI/SQLAlchemy, existing document parsers, Next/React, pytest and Node/Playwright.
**Spec:** docs/superpowers/specs/2026-10-01-document-policy-design.md

## Global Constraints
- Production and original candidates SHA256 unchanged. No deploy, push, merge, new crawling or destructive operations.
- Preserve all pre-existing uncommitted work; edit only assigned files. No commits that sweep existing changes.
- Use backend/venv/Scripts/python.exe. Sandbox launch currently fails; exec_command require_escalated succeeds and is within user authorization.
- TDD meaningful behavior tests; test fixtures never represent real history or real human labels.
- Confidence is heuristic until human gold calibration. Ordinary notices never imply formal recognition.

## Review Focus
- Spoofed domain suffix / administrator-supplied proof flags cannot grant official policy recognition (Task 3).
- A policy title quoted inside ordinary notice does not classify whole notice as formal policy (Task 1).
- Similar names, negated or excluded rows, child tracks, shared aliases cannot auto-match incorrectly (Task 2).
- Incomplete/new conflicting policy must not leave stale old recognition publicly current (Task 3).
- AUTO_CLASSIFIED does not hide actual pending facts, and correction state survives refresh (Tasks 3/4).

### Task 1: Deterministic classifier (independent)
Files: create backend/app/services/source_document_classifier.py, backend/tests/test_source_document_classifier.py only.
Interface: classify_document(source: dict, *, has_fact_changes=False, has_conflicts=False, has_valuable_relation=False) -> dict. Export DOCUMENT_TYPES (tuple/list), POLICY_TYPES (set), RECOGNITION_TYPES (mapping policy document type -> recognition string), DOCUMENT_TYPE_LABELS (dict).
Source keys title/source_title, content_preview/content_text, publisher, section, attachment_titles.
Output keys: document_type, primary_type, secondary_types, confidence, classification_reason, matched_rules, requires_human_confirmation, informational_only, risk_level, classification_status (AUTO_CLASSIFIED/NEEDS_QUICK_CONFIRM/NEEDS_MANUAL_CLASSIFICATION), rule_version.
- [x] RED tests all user types including registration/organization/selection/recommendation/result/publicity/completion/intro/event/policy/award/postgraduate/comprehensive/credit/repost/extension/correction/rule_update/historical/other.
- [x] Mixed title 校赛获奖名单公示 => publicity primary, result/selection secondary; registration ordinary mentioning scholarship in body never policy. Policy title 学生推免结果公示 is publicity, not a policy directory.
- [x] Title strongest, body opening paragraphs/section/attachment auxiliary only; institution alone cannot classify. Extension/correction/rule_update high risk even secondary. Info-only only completion/intro/event with no fact/conflict/valuable relation and confident classification.
- [x] GREEN implement precedence with explainable rules. Initial thresholds 0.90/0.65, explicitly uncalibrated; conflicting semantics require confirmation. No LLM/network.
- [x] Run targeted test then write .codex-qa/document-policy/task1-report.md with commands, evidence and caveats.

### Task 2: Policy text extraction and competition matcher (independent)
Files: create backend/app/services/policy_list_extractor.py, policy_competition_matcher.py; tests/test_policy_list_extractor.py and test_policy_competition_matcher.py only.
Interfaces: extract_policy_entries(content: str, *, format='text', title='') -> list[dict] with raw_competition_name/evidence_text/locator; parse_policy_file(path) -> dict containing content_text/entries/needs_ocr/error/parser_type; match_policy_competition(db, raw_name: str, *, hints=None) -> dict of normalized_name/match_status/match_confidence/matched_competition_id/match_reason, candidate_ids optional.
- [x] RED HTML tables/lists, numbered lists and delimited competition clauses; retain all names with locator and don't emit headers, exclusion clauses, unrelated prose.
- [x] RED PDF text, DOCX, XLSX and legacy DOC/XLS adapter; OCR needed when no text, do not run OCR or invent names. Existing parser reuse, do not touch requirements unless parent approves necessary missing dependency.
- [x] RED exact full/short/English, verified historical alias, punctuation and edition/year prefix, China-vs-national weak match only if unambiguous evidence; duplicate alias/series/child-track ambiguity => manual or quick confirmation. Unverified alias cannot AUTO_MATCHED.
- [x] GREEN implement read-only matching with formal existing competitions, no creation or official writes. Helpers may expose normalize_policy_name.
- [x] Run targeted tests and report at .codex-qa/document-policy/task2-report.md.

### Task 3: Integration, safe automatic policies, historical replay (root)
Files: document_policy_service.py + routes/document_policy.py + schemas/document_policy.py; existing router, ingestion, field-review detail/queue and policy resolution/user-facing policy hooks; tests and scripts/replay_document_policy.py.
- [x] Tests before production edits: admin authorization, classification audit, info-only no pending fact loss, spoofed domain, policy-current/scope safeguards, all recognition dimensions, repeated replay idempotency, negative ordinary notices, no fact changes, conflicting/newer policy retirement and evidence provenance.
- [x] APIs /api/admin/document-policy GET returns {items,total,statistics,document_types}; PUT /{candidate_id}/classification body {document_type,reason} returns updated item. POST /replay-classification body {} for pending stored evidence; GET /policies returns {items,total}; POST /policies/{id}/analyze body {} persists evaluated candidates/auto relations. No automatic approval endpoints for facts.
- [x] Policy list item contains id,title,source_url,university_id,school_name,classification,analysis. analysis = {entries: [...],automatic_relations: number,requires_human_confirmation: boolean,blocking_reasons: string[],conflicts: []}. Each entry includes raw_competition_name,normalized_name,recognition_type,match_status,match_confidence,matched_competition_id,match_reason,verification_method,relation_status,blocking_reasons,source_title,source_url,effective_from,effective_to.
- [x] Classification item = {id,title,source_url,school_name,competition_name,status,classification}; field detail adds document_classification.
- [x] Source replay 100–200 distinct existing URLs; policy replay entire available real policy pool on isolated DB. Persist metrics separate from functional fixtures. Prepare human-gold 50–100 rows with blank labels if no independent human labels; metric runner rejects unreviewed/nonhuman labels.

### Task 4: Admin frontend (independent API contract above)
Files frontend/src/app/admin/document-policy/page.tsx, frontend/src/components/DocumentClassification.tsx, frontend/src/lib/document-policy-api.ts, frontend/tests/document-policy.test.mjs; minor edits FieldReviewDetail.tsx/SchoolRelationReview.tsx and admin/page.tsx only for integration. Coordinate field-review-api.ts additive type edit with root.
- [x] Read frontend/AGENTS and local Next docs. RED/behavior tests classification view/correction errors, read-only auto state, policy provenance and manual reasons, no automatic effects that POST on mount.
- [x] Show Chinese primary/secondary type, confidence rule score, basis; AUTO_CLASSIFIED requires no type action, explicit 修改分类 sends audited correction.
- [x] New admin list and policies, manual trigger for replay/analyze; display each typed recognition and evidence with safe source links. Never hide sources. Field review embeds component optionally.
- [x] Run targeted frontend tests/typecheck/lint and report at .codex-qa/document-policy/task4-report.md. No new packages unless necessary.

### Task 5: Review and final evidence
- [x] Fresh independent review of policy safety/integration and parser boundaries, address verified issues with tests.
- [x] Full backend pytest, frontend tests, lint/typecheck/build; real browser A-I on isolated fixtures clearly labeled, real history separate.
- [x] Compare original DB hashes/schema and changed file list. Save report docs/DOCUMENT_POLICY_AUTOMATION_REPORT_20261001.md covering user 37 items; PASS only all18 criteria including genuine gold. Otherwise BLOCKED with concrete missing evidence, no simulated substitution. Update CURRENT_TASK.

## Completion boundary

Engineering and isolated verification completed. User acceptance remains DOCUMENT_POLICY_AUTOMATION = BLOCKED: no independent human golden set, uncalibrated thresholds, and only 2/254 actual main-queue tasks removed. Checked implementation tasks do not certify those missing user acceptance conditions.
