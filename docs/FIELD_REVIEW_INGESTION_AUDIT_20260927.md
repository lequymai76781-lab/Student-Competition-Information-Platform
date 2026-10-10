# 竞赛字段采集入口与保护边界

范围仅 Competition / CompetitionEdition。未连接或修改正式库、未迁移 schema，未重新审计 R12/R13/R14。

## 当前集成状态

独立保护模块、候选转换服务和受保护测试已完成。用户本轮明确批准旧入口统一切换后，`SessionLocal` 已接入 `ReviewGuardedSession`。`.codex-qa/field-review/runtime-session-integration.patch` 记录已应用的两行接入变更；未连接或修改正式数据库。

## 已实现的候选路径

- `CompetitionFieldIngestionService.stage/stage_record`：通过共享字段校验提交 `field_candidate`，不批准、不修改正式字段、不提交事务；同一输入指纹复用既有候选，包括已完成的候选。
- 无效链接、缺失时区、结构化值里的客户端核验标记和不支持字段留在候选原始证据中，并说明待人工整理原因。没有来源时不合成来源或核验人。
- `CompetitionNormalizationService.normalize_or_create`：受保护 Session 中匹配未知赛事时提交候选，不创建正式占位赛事。真实高校政策提取链路保留原 CandidateCompetition，并转入人工审核。
- `CompetitionSeedImportService.import_records`、`CompetitionEditionSeedService.import_json`：受保护 Session 中仅提交候选。赛事和明确年份届次分开；新赛事未批准时，其届次资料保留于原始证据。
- `FactIntelligenceService._promote_official_record`：受保护 Session 中，无论来源自称何种权威等级都只产生候选。自动分类/来源刷新不再修改受保护 Session 中的正式身份和核验字段。
- 以上分支对运行时 SessionLocal 使用的 ReviewGuardedSession 生效；普通隔离测试 Session 保留原有 fixture/历史服务行为。保护测试使用真实 SessionLocal 工厂，只将数据库 bind 替换为隔离测试引擎。

## 独立保护的准确行为

`ReviewGuardedSession` 拒绝未审核的两实体创建、删除、标量事实/核验字段修改；也拦截 ORM 关系引发的届次孤儿删除和归属变更。

覆盖 ORM flush、Session.execute 的 ORM/Core/带别名 DML/文本 SQL、legacy bulk API，以及由该 Session 借出的 Connection.execute/exec_driver_sql。

仅允许派生调度字段 `freshness_status`、`next_check_at`、`last_seen_at`、`updated_at`。原始 SQL 无法证明只修改调度字段，因此涉及保护表的原始写语句统一拒绝。未变更的读取和其他表行为不受该保护影响。

`reviewed_write(db)` 仅供已验证管理员、来源与预览版本的审核服务使用。进入时拒绝已有未审核脏事实；成功退出前 flush；不 commit；异常后权限立即失效。候选产生方不可使用此上下文。

## 仍需明确的入口

统一运行时已启用。尚未转换的 AuthoritySync、Discovery 的部分关系/届次写入、CompetitionIntelligence 层级创建/状态刷新、详情导入/清理及历史专项脚本会失败并提示改用字段候选服务。它们不会自动获得审核权限。本阶段没有扩展学校政策、学校通知或高校认定实体审核。

`crawler_jobs` 是抓取运行记录，并非审核控制器；PolicyCrawlerScheduler 是 CLI 调用的同步封装。`run_v1_prod_ops.py --loop-minutes` 是现有周期循环，刷新调度字段可继续工作。

对 `backend/scripts` 搜索 `create_engine`、`sessionmaker`、直接 `Session(...)` 未发现自建数据库 Session；它们通过 SessionLocal 获取会话。任意独立 Engine、DBAPI 或外部数据库管理连接不属于应用 Session 保护边界，本方案不是数据库权限隔离。

## 测试证据

运行时接入的最新验证：接入前的三个真实工厂测试均按预期失败（工厂未保护、种子创建正式赛事、旧直接写入未被拦截），见 `runtime-factory-red.log`。接入后，包含运行时工厂断言的采集/保护、种子及归一化测试45项通过，见 `runtime-ingestion-green.log`；直接相关的政策管道、发现、权威来源及审核服务回归73项通过，见 `runtime-related-regression-green.log`。这些日志位于 `.codex-qa/field-review/`。以下记录保留独立组件阶段的历史结果。

`.codex-qa/field-review/ingestion-red.log` 及 connection/relationship/alias/raw-evidence 的 RED 日志记录新增保护测试的失败依据。

独立组件阶段的历史聚焦命令（正式库未使用，以下失败数量已由当前完整回归取代）：

```text
backend/venv/Scripts/python.exe -m pytest backend/tests/test_field_ingestion.py backend/tests/test_field_review.py -q -k "not runtime_session_factory"
```

接入前历史结果：91项通过；日志 `.codex-qa/field-review/backend-review-fixes-components-scoped.log`。当时包含工厂断言为91通过、1失败，完整后端549通过、6失败。当前已启用且新增回归通过：审核/真实采集保护/入口集成共118项，完整后端584项全部通过，见 `unstructured-reject-components.log` 和 `backend-integrated-final.log`。不再排除工厂断言。

额外发现的 Connection.execute 执行参数绕过已先复现失败，再修复 compiled_parameters 检查：dict / executemany 不能将 organizer 或主键偷偷加入仅声明 updated_at 的更新；WHERE绑定参数和正常时效更新仍可使用。独立复查原始绕过探针通过。日志 `.codex-qa/field-review/ingestion-execute-params-red.log` 和 `ingestion-execute-params-green.log`。

覆盖真实政策提取到候选（不抓网络）、种子与届次隔离、重复采集、嵌套来源伪造、ORM/Core/SQL/批量/连接/关系旁路、已审核赛事和届次更新、新赛事批准，以及共享审核服务的部分批准、来源核验与事务测试。
