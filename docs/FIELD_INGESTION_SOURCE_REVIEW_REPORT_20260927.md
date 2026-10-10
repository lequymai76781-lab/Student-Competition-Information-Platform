# 字段级入库与来源核验阶段报告

日期：2026-09-27。范围：Competition / CompetitionEdition。上一阶段的 PHASE_APPROVAL = PASS 保持有效，R12 / R13 / R14 未重审。

**最终结论：竞赛与届次字段级审核闭环已完成，正常应用及旧入口已接入，可以结束本阶段。** 完整后端584项、前端43项、正常应用真实浏览器12项均通过；lint、typecheck、build通过，正式库SHA256不变。用户已明确批准此前具体切换并取消相关暂停限制，接入按 [切换记录](FIELD_REVIEW_WRITE_GATE_APPROVAL.md) 完成，没有绕过自动审批拒绝。

## 1. 开始前数据审核流程

| 数据入口 / 实体 | 原有流程和缺口 |
| --- | --- |
| 用户纠错 UserCorrectionSubmission | 创建提交及旧 ReviewQueue；截止更正已有管理员审核事务，但没有通用逐字段差异、来源核验和选择机制。 |
| 赛事补充 BetaFeedback / ReviewQueue | 保留提交与审核状态，不能按字段导入为正式竞赛。 |
| CandidateCompetition | 依赖高校与政策，主要承接政策提取；normalize_or_create 可能先创建正式赛事，再形成候选。 |
| PolicyDocument / PolicyAttachment | 保存文件、链接、提取内容和关联证据；文档来源并不等于每个正式字段都有人工核验记录。 |
| CandidateFact / FactIntelligence | 已有候选事实及部分来源记录；仍有权威信息自动补空或创建届次的路径。 |
| crawler_jobs / 调度 | 记录采集运行，不承担审核权限控制；种子、官方资料及若干维护脚本有直接写入路径。 |
| Competition / CompetitionEdition | 旧管理员 POST/PUT 可直接修改；既有来源/修订表只覆盖部分字段，初始值不一定有对应修订。 |
| 学校通知及高校认定/政策关系 | 已有届次、政策、学校关联与证据；本阶段只检查其进入竞赛的边界，不扩展这些实体的审核。 |

因此原有 ReviewQueue 的存在不能证明所有正式值都经过同一审核，也不能补出历史字段缺失的来源或审核人。本轮没有伪造或补写历史来源。

## 2. 本轮新流程

正常应用中的新流程为：候选暂存 → 当前值与候选值比较 → 来源人工核验 → 对每个字段批准/拒绝/暂缓 → 原子写入获批事实 → 来源、修订与审核记录。

新候选、来源核验都不会修改正式值。来源优先级、置信度、AI 或采集方声明的权威性均不能触发自动批准。

**已接入正常应用：** 新审核路由、用户纠错/赛事补充候选转换、旧审批引导、旧赛事增改接口409保护、SessionLocal统一保护，以及人工核验事实的公开展示。采集适配分支在运行时生效，尚未适配的旧脚本直接写正式赛事或届次会明确失败。

## 3. candidate → review → official 完整数据流

1. 新服务接受白名单字段、明确实体/届次及来源；将版本化 JSON 保存在 ReviewQueue.raw_value，item_type 为 field_candidate。
2. 来源适配服务把采集内容转换为候选。无法解析或包含伪造核验元数据的字段保留原始证据与原因，等待整理；不丢弃证据，不写正式值。
3. 管理员读取实时正式值及所有候选来源，获得 preview_token。自由文本候选须先明确目标和字段。
4. 管理员逐项核验来源，服务端记录真实核验人和时间，生成新预览版本。
5. 提交具体字段决定与所选 proposal_id；审核校验权限、来源、字段白名单、届次、候选版本与正式值版本。
6. 只将获批字段写入 Competition / CompetitionEdition，并写入 FactSource、FactRevision、AdminAuditLog、审核历史及必要事件/关联提交状态。
7. 调用方提交同一事务；任何审计、通知或 commit 异常必须回滚。SQLite 的嵌套事务已补充真实外层 BEGIN 防止保存点释放提前提交。

以上流程已通过正常 app.main:app、真实 SessionLocal 和合成数据库验证，没有额外注册路由或覆写数据库依赖。用户原始提交与候选在同一事务创建；历史材料转入先锁原始提交，再查询既有候选，两个并发请求不会创建两个候选。

## 4. 字段级差异实现

返回 field_name、display_name、current_value、candidate_value、changed、change_type、source、source_url、source_type、confidence、verification_state、last_verified_at。字段文字明确标记新增、修改、删除或无变化，界面不只依赖颜色。

标量、日期与结构化数组分别校验；结构化条目采用内容白名单，客户端不得夹带 verified_by 等来源背书。比较时忽略服务端附加的来源元数据，避免重复产生虚假差异。

## 5. 字段级批准实现

每个字段支持 approve / reject / defer。批准必须显式选择候选来源；拒绝保留原值，暂缓留待处理，未提交决定的字段不改变。清空非空字段需要额外确认。新赛事须批准名称，新届次须明确赛事与年份并至少批准一个非空字段。

低风险批量只允许已核验、同来源、同目标实体/届次、无冲突且不覆盖非空正式值；整个批量原子执行。过期预览、重复终态审核和并发正式值变化均拒绝。

零字段自由文本可直接拒绝并保留原材料、来源和审核理由，不需要为了拒绝而虚构字段。此入口拒绝处理已结构化或已完成的候选；有字段时仍逐字段审核。来源原文的变化也会使旧预览失效。

## 6. 来源模型

不新增来源表。候选 JSON 保存 source_type、source_title、source_url、publisher、published_at、collected_at、verified_at、verified_by；正式事实复用既有来源表，完整私有审核证据保留在审核历史及审计中。

| 优先级建议 | 类型 |
| --- | --- |
| 1 | official_website |
| 2 | organizer_notice |
| 3 | government_document |
| 4 | university_notice |
| 5 | university_policy |
| 6 | industry_organization |
| 7 | user_submission / manual_entry |
| 8 | third_party / crawler |
| 9 | ai_assisted |

不存在可追踪来源时为 NO_SOURCE，其余初始 UNVERIFIED。人工核验后是 VERIFIED，正式事实使用 verified_manual，不冒充 verified_official。无线上链接但有明确文档标题与发布者的来源可人工核验，正式 source_url 保持空值，不生成虚假网址。AI 内容始终先进入候选。

## 7. 冲突检测

检测同一候选及其他未结束候选中同目标、同字段的不同值，返回 CONFLICT 并显示来源、候选值及时间。管理员必须明确选择，不按权重自动胜出；其他证据保留。

## 8. 届次隔离

竞赛本体与届次具有不同字段白名单，身份列不作为普通可审核字段。edition 同时校验 competition_id、edition_id 与 year。没有明确年份的采集信息不会自动写入某届。

新届次候选创建后若相同年份正式届次被其他审核创建，再次审核会重新解析该届次并核对预览，将来源归到真实 edition_id，不错误挂到赛事本体。测试和浏览器均验证只修改选定届次。

## 9. 审核日志

记录审核人、时间、候选、批准/拒绝/暂缓决定、修改前后、所选来源与备注。来源核验自身也有审计；被拒绝字段的来源证据保留。内部审核备注及身份标识只应保留在管理员记录中，不进入公开事实/更新说明。

两轮限定独立复查共发现6项问题：执行参数绕过写保护、列表清空未确认、公开更新泄露审核备注、自由文本原始来源未展示、零字段候选无法拒绝、并发转入重复候选。全部完成失败复现、失败测试、根因修复及独立复验，无本轮剩余阻塞发现。接入测试还补齐部分批准队列筛选及人工核验标签。最终结果见第16节。

## 10. 后台界面

新增 `/admin/field-review`，具有状态、冲突、无来源、待核验、实体、赛事、学校、来源类型、提交人及时间筛选。详情展示左右值、变化文字、来源原文、候选来源选项、逐字段决定、删除确认和历史。来源核验后刷新预览并重置过期选择；支持准确届次的正式详情链接和会话切换清理。

旧审核中心已连接字段审核入口及历史记录转入按钮。用户可提交明确建议值，服务端保存为未核验候选；只有说明的材料保留原始来源，管理员整理或直接拒绝。部分批准仍在“未完成”队列可访问，用户历史显示“部分通过，其余待处理”。赛事补充不再显示失效的旧批准按钮；学校等本阶段外实体仍使用原队列。

## 11. API 修改

已注册的管理员路由前缀 `/api/admin/field-reviews`：

- GET `/config`、GET/POST 根路径、GET `/{id}`。
- PUT `/{id}/prepare`，将自由文本结构化但不入正式库。
- POST `/{id}/sources/{proposal_id}/verify`。
- POST `/{id}/review`、POST `/bulk-review`。
- POST `/{id}/reject-unstructured`，仅拒绝零字段待处理材料，不修改正式事实。

上述路由均要求真实管理员。另已接入 POST `/api/admin/field-review-origins/{kind}/{item_id}`，支持历史纠错/赛事补充的并发幂等转入；用户纠错接收 proposed_value，提交返回 field_review_id。旧 POST/PUT competitions 对管理员返回409引导审核，非管理员仍拒绝；旧已关联审核记录不能绕过字段流程批准。历史未关联纠错仍可拒绝或要求补证，但批准必须转入字段审核。

## 12. 数据库是否修改

正式数据库没有修改、清理或导入。测试只对内存库、临时副本或 `.codex-qa/field-review/` 合成库写入；正式库只用于 SHA256 比较及既有只读副本夹具的源文件。测试连接有路径防护，拒绝连接正式 SQLite 文件。

## 13. schema 是否修改

没有新增表、字段或迁移。复用 ReviewQueue、CompetitionFactSource、CompetitionFactRevision、AdminAuditLog 及既有事件/提交实体。没有运行正式迁移，数据库版本保持原值。

## 14. 修改文件

下列为相对于本阶段开始快照的变更；工作区此前已有 90 个变更文件，本报告不将其全数算成本轮改动。

**新增后端组件与测试：**

- `backend/app/api/routes/field_reviews.py`
- `backend/app/api/routes/field_review_origins.py`
- `backend/app/database/review_guard.py`
- `backend/app/schemas/field_review.py`
- `backend/app/services/field_review_service.py`
- `backend/app/services/field_review_origins.py`
- `backend/app/services/competition_field_ingestion_service.py`
- `backend/tests/test_field_review.py`
- `backend/tests/test_field_ingestion.py`
- `backend/tests/test_field_review_integration.py`

**修改的采集适配路径：**

- `backend/app/crawler/normalization/competition_normalizer.py`
- `backend/app/crawler/pipelines/university_policy_pipeline.py`
- `backend/app/services/competition_normalization_service.py`
- `backend/app/services/verified_policy_ingest_service.py`
- `backend/app/services/competition_seed_import_service.py`
- `backend/app/services/competition_edition_seed_service.py`
- `backend/app/services/fact_intelligence_service.py`

正常应用 SessionLocal 已切换，因此这些候选分支在运行时生效。

**旧入口与运行时接入：**

- `backend/app/api/router.py`
- `backend/app/api/routes/users.py`
- `backend/app/api/routes/supplements.py`（该文件在本阶段开始前已存在于工作区）
- `backend/app/api/routes/admin.py`
- `backend/app/api/routes/competitions.py`
- `backend/app/database/session.py`
- `backend/app/schemas/v1.py`
- `backend/app/services/user_facing_data_policy.py`
- `backend/app/services/competition_service.py`

**迁移和增强原有回归：** `backend/tests/test_contribution_workflow.py`、`test_review_security_regressions.py`、`test_v1_notifications_product.py`、`test_edition_time_fact_boundaries.py`。保留隐私、回滚、重试、并发、通知、届次和UTC验证，旧直接批准用例改为来源核验后的字段审批，没有通过删掉断言掩盖行为变化。

**新增前端与测试：**

- `frontend/src/app/admin/field-review/page.tsx`
- `frontend/src/components/FieldReviewCandidateForm.tsx`
- `frontend/src/components/FieldReviewDetail.tsx`
- `frontend/src/lib/field-review-api.ts`
- `frontend/tests/field-review.test.mjs`
- `frontend/tests/field-correction.test.mjs`

**修改前端：**

- `frontend/src/app/admin/review/page.tsx`
- `frontend/src/components/v09/CorrectionForm.tsx`
- `frontend/src/components/v09/ContributionHistory.tsx`
- `frontend/src/lib/v09-api.ts`
- `frontend/src/lib/format.ts`

**文档：** 本报告、`FIELD_REVIEW_DESIGN_20260927.md`、`FIELD_REVIEW_INGESTION_AUDIT_20260927.md`、`FIELD_REVIEW_WRITE_GATE_APPROVAL.md`、`superpowers/plans/2026-09-27-field-review.md`、`CURRENT_TASK.md` 及根目录 README。QA 脚本和日志位于已忽略的 `.codex-qa/field-review/`，不提交测试数据库或合成凭据。

## 15. 新增测试

本阶段后端总用例由458增加至584（净增126），前端由30增加至43（净增13）。新增审核、采集与接入三个后端测试文件共118项全部通过。用户要求的15类验收对应：

| 要求 | 当前证据 |
| --- | --- |
| 1 新字段、2 修改、3 无变化 | 候选及差异测试，结构化比较测试。 |
| 4 批准、5 拒绝、6 部分批准 | 正式值只更新被批准字段；其他字段保持；真实浏览器验证。 |
| 7 多来源冲突、8 无来源 | 本候选/跨候选冲突；未核验和 NO_SOURCE 拒绝批准。 |
| 9 不同届次 | 身份不匹配拒绝、年份隔离、新届次竞争创建。 |
| 10 非管理员 | 独立 HTTP 全路由权限、服务层真实用户身份检查。 |
| 11 重复审核 | 终态和过期预览拒绝，候选与正式值双重版本校验。 |
| 12 rollback | 审计、通知、批量第二项、外层 commit 异常以及成功后外层回滚。 |
| 13 候选不改正式值 | 服务、ORM/Core/SQL/Connection/关系/批量保护测试。 |
| 14 用户进入候选 | 新旧提交接入、来源、来源人、关联状态、部分批准、无字段拒绝、并发幂等和用户真实浏览器链路均通过。 |
| 15 crawler 不直接写 | 真实 SessionLocal 工厂的政策、种子、届次、官方信息采集测试通过；直接写入被阻止，批准上下文才可更新。 |

另测结构化来源伪造、删除确认、审核隐私、低风险批量条件和会话边界。此前6项接入失败均已通过，保留为回归，完整测试没有跳过这些验收。

## 16. 测试结果

| 检查 | 最终结果 | 证据（均在 `.codex-qa/field-review/`） |
| --- | --- | --- |
| 完整后端 | **584 / 584 通过；exit 0，43.12秒** | `backend-integrated-final.log` |
| 核心审核服务/API | 66通过 | `unstructured-reject-green.log` |
| 审核 + 真实采集保护 + 接入 | 118通过，包含 SessionLocal 工厂断言 | `unstructured-reject-components.log` |
| 完整前端 | **43 / 43 通过** | `frontend-integrated-final.log` |
| lint | 通过 | `frontend-lint-integrated.log` |
| typecheck | 通过 | `frontend-typecheck-integrated.log` |
| build | 通过，19 / 19 页面生成 | `frontend-build-integrated.log` |
| git diff --check | 通过 | `diff-check.txt` |
| 独立复查两轮共6项修复 | 原始复现全部通过，无本范围剩余阻塞发现 | 见下述 RED/GREEN 日志及后端新增回归。 |

各定向测试与完整后端重叠，不累计为额外通过数。完整后端命令为 `venv/Scripts/python.exe -m pytest -o addopts='-p no:cacheprovider' -q`（backend目录），未排除任何接入断言。

复现日志包含 `ingestion-execute-params-red.log`、`backend-review-fixes-red.log`、`integration-resume-red.log`、`integration-boundaries-red.log`、`origins-review-red.log`、`unstructured-reject-red.log`、`unstructured-ui-red.log`，相应GREEN日志与最终完整回归保留。前端测试使用当前Codex运行时提供的Playwright：设置 NODE_PATH 为 `C:/Users/时生/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules` 再执行 `npm test`，未为此修改生产依赖。

迁移旧回归时，将“旧接口直接批准”换成“转入 → 整理 → 核验 → 字段批准”，保留原事务故障注入、独立连接并发、失败重试和数据私有性断言；未改造的旧拒绝/需补证接口也新增事务回滚验证。

## 17. 浏览器验证

使用 Edge + Playwright、真实HTTP登录、真实页面和正常 `app.main:app`，端口3048/8048。后端直接使用已接入的 SessionLocal；没有 preview_app、额外路由注册或 get_db 覆盖。数据库为全新合成 `browser-integrated-v3.sqlite`，不包含生产数据。

**12 / 12 通过，pageErrors = []**：匿名禁止及管理员登录；队列/差异/来源展示；核验来源不改正式值；批准主办方、拒绝名称、暂缓简介；公开详情仅出现获批修改；本届截止更新且旧届不变；历史保留字段决定；真实用户纠错表单生成未核验候选；旧审核中心进入字段审核并同步用户历史；自由文本原始来源、幂等转入与零字段拒绝；真实用户赛事补充经人工批准公开；旧POST/PUT直写返回409且正式值不变。

结果在 `.codex-qa/field-review/browser-results.json` 和 `browser-integrated-final.log`，截图包括 `field-diff-before.png`、`field-diff-after.png`、`official-after.png`、`new-manual-official.png`。

另补充独立匿名访问验证：等待URL确认为 `/competitions/2` 且页面H1出现后重新截图，确认无登录token也可查看新赛事；API仍为verified_manual，未批准的简介为空。证据为 `anonymous-manual-public-result.json`、`anonymous-public-check.log`。这修正了候选标题与正式标题相同造成的过早截图，不重复累计到上述12项。

最终浏览器复跑修正了脚本对下拉框标签的精确匹配及Next页面跳转后的等待条件，再以全新合成库完整运行通过；没有为修复脚本而改变产品行为。仅测试进程指定 BACKEND_CORS_ORIGINS，未改变应用策略。临时API及前端服务均已停止。

## 18. 正式数据库 SHA256

正式文件：`D:/Python/xuesheng/data/v02.sqlite`。

开始前：`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`。

测试后：`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`。**前后一致。** 未 push、merge、部署或创建付费资源。

## 19. 当前仍存在的问题

1. **本阶段无剩余阻塞问题。** 原6项接入失败及两轮复查发现均已关闭；本轮未发现未修复的P0/P1。
2. 尚未改成候选的旧 AuthoritySync/Discovery/层级和历史维护脚本会拒绝直接修改两实体。后续需要使用这些工具时逐项适配候选入口；不会自动获得审核权限。本阶段未运行生产采集或维护脚本。
3. 保护范围是应用 Session，不是数据库账号权限隔离；独立 Engine/DBAPI 或外部管理工具不在边界内。
4. 已结构化但没有来源的候选没有原地修改来源功能：可拒绝/暂缓或创建带来源的新候选；自由文本候选可以在 prepare 时补充来源。
5. 上一阶段非阻塞技术债 R12/P2、R13/P3、R14/P3 原样保留；没有将它们作为本阶段不能结束的理由。

## 20. 下一步建议

本阶段可以收口。后续若要使用尚未适配的历史采集工具，优先补充候选适配；是否扩展学校通知、政策或会议审核由下一阶段任务决定。不需要为本轮接入再次确认。

没有开始大规模数据补齐、学术会议扩展或全国高校抓取。本轮停止于 **字段级审核闭环完成**。建议批准本阶段改动。

PHASE_APPROVAL = PASS
