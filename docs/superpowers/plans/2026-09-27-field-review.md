# 字段级入库与来源核验实施计划

> **For agentic workers:** Use superpowers:executing-plans for implementation and superpowers:dispatching-parallel-agents for disjoint tasks. User explicitly authorized continuous local implementation; do not add approval gates or commits.

**Goal:** 完成竞赛/届次候选、字段差异、来源核验、部分批准、正式写入和审计闭环。

**Architecture:** 复用 ReviewQueue 文本 JSON 与既有来源/修订/审计表。按文件分工后集成；来源权威不触发自动覆盖。

**Tech Stack:** FastAPI / SQLAlchemy / Pydantic / Next 16 / React / pytest / Node tests / Playwright。

**Spec:** [字段审核设计](D:/Python/xuesheng/docs/FIELD_REVIEW_DESIGN_20260927.md)。

## 全局约束

- 不修改正式库或 schema，测试内存/临时库，前后 SHA256 相同。
- 只支持竞赛本体、明确届次；R12/R13/R14 不顺手修复。
- 保留已有工作区改动；不 push/merge/deploy。
- 来源未核验不得写正式；所有批准字段有来源与审计；部分批准不影响其他字段。

## 审查重点

- 旧预览覆盖新正式值：版本冲突测试。
- 来源伪造/NO_SOURCE：服务端状态和真实管理员校验。
- 同字段跨候选冲突：提供所有值，不自动选择。
- 届次混用：同时校验 competition_id、edition_id、year。
- 批量绕过与事务异常：全批校验和回滚测试。

## 工作项

- [x] 1. 后端审核服务/API完成；核心66项通过，含零字段拒绝与原始来源。
- [x] 2. 前端后台与用户建议值完成；读取Next本地文档，完整前端43项通过。
- [x] 3. users/supplements、旧admin入口、正常路由及SessionLocal保护均已接入；并发转入保持幂等，来源和提交人保留。
- [x] 4. 15类验收及完整后端584项通过，原事务、隐私、通知、并发与UTC用例已迁移到新流程并保留断言。
- [x] 5. 正常应用+真实SessionLocal+合成库的浏览器12项通过；独立复查6项问题已关闭；报告、SHA256和文件清单已保存，停止于闭环完成。

## 执行记录

- 开始：正式库 SHA256 `9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`，已有90文件改动。快照在 `.codex-qa/field-review/before.json`。
- 决定：采用 ReviewQueue JSON，不新建表；自由文本不猜测日期，通过待结构化候选和人工准备完成。
- 授权记录：先前接入被自动审批拒绝后，用户明确批准具体切换并取消核心逻辑暂停限制，继续完成；没有绕过拒绝，也不再请求重复确认。
- 最终结果：后端584、前端43、浏览器12项通过；lint/typecheck/build通过；正式库SHA256不变。新组件与接入118项均包含在完整后端中，不重复累计。
- Ruling：历史直接批准测试改为来源核验后的字段审批，保留原安全和事务断言；已结构化候选仍逐字段处理，零字段材料单独允许拒绝；不改变正式schema。
