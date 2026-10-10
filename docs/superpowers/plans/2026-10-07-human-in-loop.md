# Human-in-the-loop Implementation Plan

> For agentic workers: use superpowers:executing-plans for root integration and superpowers:dispatching-parallel-agents for independent module tasks; TDD per task.

**Goal:** Blind shadow predictions and immutable human learning examples, with admin-only metrics, replay and batches.
**Architecture:** Separate SQLite sidecar; read-only snapshots and committed human audit evidence; untouched formal database.
**Tech Stack:** Existing Python/FastAPI/SQLAlchemy, SQLite, Next.js/React; no new runtime dependencies.
**Spec:** docs/superpowers/specs/2026-10-07-human-in-loop-design.md

## Global Constraints
Original human labels untouched; no collection, deployment, auto approvals or model promotion. Real and automation stores separate; fail closed on provenance. Follow exact module/API contracts in spec. Existing dirty workspace is authorized; no git mutation. Test artifacts under .codex-qa/human-in-loop-20261007/.

## Review Focus
- Duplicate/parallel completions and correction lineage must not duplicate training samples.
- Browser refresh/logout/candidate switching cannot attach one person's choices to another source.
- Audit-before-session, failed transaction and input changes cannot fabricate ground truth.
- Missing human dimension must remain missing; no empty denominator shown as 100%.
- Prediction failures cannot approve or silently suppress real review tasks; genuine historical replay is distinguished from live samples.

## Tasks
- [ ] 1. Pure shadow predictor/comparison/performance/replay; tests/test_review_learning_metrics.py first RED then GREEN. Owner metrics agent; no service integration edits.
- [ ] 2. Independent append-only learning store and batch/correction contracts; tests/test_review_learning_store.py first RED then GREEN. Owner store agent.
- [ ] 3. Existing frontend blind human review integration + status page/API types; frontend/tests/review-learning.test.mjs first RED then GREEN. Owner frontend agent; no backend edits.
- [ ] 4. Backend config/provenance/committed-audit validation/API and registration; tests/test_review_learning_api.py first RED then GREEN. Root owner. Explicitly test admin-only, stale session, automation exclusion, unchanged candidates/official facts.
- [ ] 5. Real candidate isolated workspace and manifest; actual browser checks separated from real human completions. Root owner. No machine choices recorded as human. Prepare 10+ genuine candidate review entry.
- [ ] 6. Independent final review, full backend/frontend/lint/type/build, hashes, report and handoff. PASS only after at least 10 real human completions otherwise honest BLOCKED.

Verification commands: backend/venv/Scripts/python.exe -m pytest (cwd backend); E:/npm.cmd test, run lint, exec tsc --noEmit, run build (isolated frontend). Expected tests exit0; all11 protected hashes unchanged. No commit steps because preserving user's ongoing dirty workspace and this turn requires no git integration.
