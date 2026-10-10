# 审核吞吐与高校关系闭环 Implementation Plan

> 使用测试驱动执行；独立文件按 dispatching-parallel-agents 技能分工，主流程负责集成和最终验证。用户已明确连续开发授权，不增加普通权限确认。

**Goal:** 在隔离副本验证 254 条真实候选的安全审核、吞吐计时与学校关系入库。

**Architecture:** 复用 ReviewQueue JSON、AdminAuditLog 与既有正式关系/政策表；server-side 队列、跨候选原子批量、独立计时事件、普通通知与政策分开批准。

**Tech Stack:** SQLAlchemy / FastAPI / SQLite / Next.js / Playwright。

**Spec:** `docs/superpowers/specs/2026-09-28-review-throughput-design.md`。

## Global Constraints

正式库和原 254 候选库 SHA256 起止一致。无 schema 迁移、不扩采、不自动批量批准生产事实；全部真实审核实验使用副本。保留前阶段未提交改动，不 commit/push/deploy。人工操作与自动化计时分开。

## Review Focus

- 19/20 项失败或锁失效：整批回滚，审计不能半成功；客户端保留选择。
- 候选预览后出现新的冲突或其他人改正式值：409，不能通过刷新内部 token 绕过。
- 多来源相同关系并发批准：不产生重复正式关系，不丢来源。
- 历史政策、研究生政策、未知年份和普通报名：不升级为当前全校本科认定。
- 计时跨候选/账号/重载/核验：不误归因、不以 API 延迟等同阅读时间；失败不会算完成。

## Tasks

- [x] 1. 读取范围、保存 `.codex-qa/review-throughput/before.json` 正式/候选/代码基线；核对既有模型和写保护。用户同意后续一组人工计时。
- [x] 2. 关系服务 RED→GREEN：新增 `backend/tests/test_school_relation_review.py`，覆盖通知/政策批准拒绝、语义拒绝转换、届次、同关系来源去重、冲突、审计回滚与鉴权；新增独立 service/schema，复用现有表。
- [x] 3. 计时 RED→GREEN：新增 `backend/tests/test_review_telemetry.py`，覆盖同人会话事件、重复开始、失效/未完成、人机模式分离、均值/中位/P90、失败不计完成；新增独立 service/schema，以 AdminAuditLog 存储。
- [x] 4. 风险/批量/查询 RED→GREEN：新增 `backend/tests/test_review_throughput.py`，覆盖风险矩阵、跨目标批量、19/20失败回滚、CAS与并发新冲突、审计、>500候选搜索分页和 SQL 数量；更新 field_review_service/schema/routes，集成关系与计时，并扩展关系正式写保护。
- [x] 5. 前端 RED→GREEN：低/高风险筛选与搜索排序、跨页多选摘要、来源时间线与打开原文、关系独立核验批准表单、统计和计时；API失败保留页面状态。读取本地 Next 文档后实现，不重做整站。
- [ ] 6. 隔离真实数据实验：复制 254 候选到自动化/人工副本，选择真实样本并统计各类实际可用量；UI/API 完整路径计时与 A–E 验证；为用户提供人工计时入口，同时运行完整回归和独立代码复查。
- [ ] 7. 收口：后端完整测试、前端测试、lint/typecheck/build、相关真实浏览器；正式/原候选 SHA 一致；实际样本均值中位P90/产能假设/积压模型；33 项最终报告、当前状态文档、停止扩量。

验证：`backend/venv/Scripts/python.exe -m pytest tests -o addopts='' -q`（cwd backend）；frontend `npm test` / `npm run lint` / `npm run typecheck` / `npm run build`；日志 `.codex-qa/review-throughput/`。

收口记录：自动化真实36条计时+2条政策、合成50条、后端792、前端57、lint/typecheck/build及安全哈希完成。用户最终暂不人工操作，人工样本0；任务6中的人工计时、任务7中的实测人工产能/积压数值未完成，保留未勾选。33项报告已交付，REVIEW_THROUGHPUT = BLOCKED；本轮停止，不扩量。
