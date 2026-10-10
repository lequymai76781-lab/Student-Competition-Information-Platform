# Hierarchical Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for integration; independent modules delegated under dispatching-parallel-agents. Work uses RED/GREEN tests.

**Goal:** 七类一级分类、独立 Policy 判定和审核解耦，复用真实 100 标签验证。
**Architecture:** 保留旧 classifier；新纯函数层级分类和 policy 判定；服务、界面使用新结果；离线脚本验证。
**Tech Stack:** Python/FastAPI/SQLAlchemy，Next.js/TypeScript，pytest/node:test/Playwright。
**Spec:** docs/superpowers/specs/2026-10-01-hierarchical-classification-design.md

## Global Constraints

不抓取、不扩量、不修改真人标签或原库、不迁移；所有数据结果来自原 100/200/254/59；不按 ID/学校特判；不 commit/reset/stash；不把功能测试当真人验证。

## Review Focus

新闻/转载中的更正始终高风险；未知正文不安全移出；人工细标签不被覆盖；类型自动不批准事实；政策授权不足不误判原政策失效。

## Tasks

- [x] 1. 纯函数 taxonomy + policy safety + hierarchical classifier：先写通用正负例 RED，再实现 GREEN；旧细分类函数不改。
  Files: backend/app/services/document_taxonomy.py, policy_safety_classifier.py, hierarchical_source_classifier.py; tests/test_hierarchical_classifier.py.
  Interface: classify_source_document(source, has_fact_changes=False, has_conflicts=False, has_valuable_relation=False), classify_policy(source).
- [x] 2. 纯指标、bootstrap与真实回放：先验证映射/分母/阈值/配对重采样 RED，再实现；映射原人标，不排除错误。
  Files: backend/app/services/hierarchical_classification_metrics.py; backend/scripts/evaluate_hierarchical_classification.py; tests/test_hierarchical_metrics.py.
- [x] 3. 中文两级界面：先组件测试 RED，再支持一级自动显示/二级可选/七类更正/风险与事实隔离文案。
  Files: frontend/src/components/DocumentClassification.tsx, src/lib/document-policy-api.ts, src/app/admin/document-policy/page.tsx, frontend/tests.
- [x] 4. 服务与政策安全门接入：缓存与人工修正升级、新分类/分流独立；先 test_hierarchical_integration.py RED，再修改 document_policy_service.py/policy_automation_service.py，保留所有证据和写入保护。
- [x] 5. 回放 100/200/254/59，量化分类合并 vs 修规则，选择保守权限并记录样本限制；不改原回放文件。
- [x] 6. 最终全后端、前端测试/lint/typecheck/build、隔离浏览器验证，独立安全复核，原库哈希；完整 30 项报告和 CURRENT_TASK。

实施已完成；质量验收仍 BLOCKED，详见最终报告。最终未开放 result/information/repost 和正式政策关系自动权限；保留信息路由的假设授权机制测试。新增复核修复未验证政策不得影响旧政策版本。
