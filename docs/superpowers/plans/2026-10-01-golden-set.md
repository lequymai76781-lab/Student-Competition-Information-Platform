# Golden Set Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development and dispatching-parallel-agents for disjoint tasks. Explicit user local authorization replaces repetitive approval gates.

**Goal:** Prepare an isolated fast human workbench for the existing100 real sources and20+20 audit samples.
**Architecture:** Immutable real snapshot + independent SQLite annotations; existing admin auth, minimalNext page; pure metrics.
**Tech Stack:** Python/FastAPI/sqlite3, Next/React, pytest/Node/Playwright.
**Spec:** docs/superpowers/specs/2026-10-01-golden-set-design.md

## Global Constraints
No coreclassifier/policyautomation changes, no thresholds applied, no new crawl, no protectedDB/schema/deployment changes. Preserve dirty workspace and prioruser manual experiments. Tests never annotate live100; read-only browser smoke allowed onlive. Use backendvenv Python, E:/node.exe, sharedPlaywright; current Windows sandbox tools require_escalated. No gitcommits/resets.

## Review Focus
- Draft/skip/predictionreveal never fabricated humancompletion; validlabels only.
- Staletabs409 and failedsave preserve localwork; no doublekeyboard submits/IMEcapture.
- Predictionhidden default per sample; exposure monotonic serverrecord, no auto-prefill.
- Typed audit answers and source-linked validity; fake fixtures never contaminate livegold.
- Empty/missingclass data metricsnull, no thresholdsapplied or misleading accuracy fromsubsets.

### Task1 root: Data/store/API
- [ ] Capturehashes; inspectunchanged original100order; createfixedmanifest20policies+20relations fromexistingrealreplay only; no labels.
- [ ] RED/GREEN backend golden_set_service.py,schemas/golden_set.py,routes/golden_set.py andtest_golden_set.py. AtomicSQLite separatestore, optimisticrevision, immutable source, adminonly, exposure, export.
- [ ] Wireapi/router only. Reuse ENV GOLDEN_SET_DIR; validatepathwithinworkspace QA; disabledwhenunset. No settings/models/schema changes needed.
- [ ] Readonlyqueue254 breakdownA-F usingexistingcopy and classifycache only, not newwrites.

### Task2 frontend independent
- [ ] Own frontend/src/app/admin/golden-set/page.tsx, frontend/src/lib/golden-set-api.ts, frontend/tests/golden-set.test.mjs only; adminlinkadditionoptionalcoordinate.
- [ ] ReadNextdocs. RED/GREEN keyboard, noautoannotation, hiddenprediction,explicit20types, optionalsecondary,skip/draft/save-next/progress,errorrecovery,source+metadata,policy20relation20checks, metricsexport.
- [ ] API contractexactlyspec; mainrender remainsfixed aftersave, no fullpagereload. Store/display revision response. Startupjumpfirstunfinished; readonlyannotationload.

### Task3 metrics independent
- [ ] Own backend/app/services/golden_set_metrics.py + tests/test_golden_set_metrics.py only. Pure evaluate_golden_set(items,annotations,policy_audits=None,relation_audits=None)->dict. No classifier changes.
- [ ] RED/GREEN n0null,validprimaryannotated/human provenance only, duplicate/conflictingIDs,accuracyperclassprecisionrecallF1/confusion,4dangerouserrorgroups,blindvs exposed,
thresholds .70/.75/.80/.85/.90/.95 counts wrongauto/policywrong; conservativeperclassrecommendation requires evidence; noactualthresholdmutation.
- [ ] readiness>=100distinct completed +20completepolicy +20completerelation, informationalsafety explicitly not assumedfromtypealone. Unsupportedclasses N/A. ReturnstatusBLOCKED whenmissing.

### Task4 root final
- [ ] Integrate/reviewauthrevisionisolation/metric denominators; appropriatefullbackend/frontend/lint/types/build.
- [ ] Realbrowserwrite flow onlyfixturestore, then startlive8054/3054 withrealmanifest andemptyannotationstore; openvisiblepage read-only,noautolabels.
- [ ] Protectedhash+corehash+original100unchanged; report docs/GOLDEN_SET_CALIBRATION_REPORT_20261001.md andCURRENT_TASK, n0BLOCKED waitforhuman.
