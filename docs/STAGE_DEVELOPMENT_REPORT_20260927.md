# 学生竞赛平台阶段开发报告

日期：2026-09-27。范围：恢复真实上下文，审查现状，跑通一条竞赛用户流程；整个竞赛与会议平台仍未全部完成。起始 Git 为干净 `main`，HEAD `dbca5eb`；本轮修改保留在工作区，未提交、推送或部署。

## 1. 开始前项目状态

FastAPI/SQLAlchemy/Alembic 与 Next.js 前后端已存在，首页、赛事大厅、详情调用真实 API；采集、候选事实、来源、审核、账号及通知已有基础。测试数据库隔离已完成，本轮保留其实现。

正式 SQLite 迁移版本 `202609060005`。只读原始计数：176个赛事对象、108个届次、600条来源、949条字段来源、78条事实修订；196所高校、355个学院、330条学校赛事映射（58校/134赛事）、375条认定、141条届次通知（90校）、76份政策（28校）、35个附件。原始赛事对象含存档/重复/非竞赛记录，不等于大厅可见数量；收录学校也不等于每校已有充分通知/政策覆盖。

会议已有独立模型及 API：206系列、132届次、289来源、15机会、54专业映射、8学校关系，前端尚无会议浏览。采集层有65任务、543线索、498候选赛事、593候选事实，这些不等于正式核实数据。详见 `CORE_USER_JOURNEY_20260927.md` 的 A–F 状态报告。

## 2. 本轮确定的主要问题

- 保存的报名状态已过时：15条报名中记录有4条截止已过，还有缺日期记录；实际截止排序晚于分页。
- 筛选命中和展示可能不是同届次；学校截止状态未贯穿详情各区域。
- 学校选择只取985及前100所，部分查询写死年份。
- API失败被吞成空结果或404，无法分清没有数据与服务不可用。
- 详情日期标签混淆，有届次时结构化历史被遮住，学校通知与来源展示不清楚。
- 新学校/赛事无通用补充入口，缺少提交反馈和完整个人记录；截止审批猜最新届次。
- README、当前任务文档已落后于代码；后台许多模块仍为占位入口。

## 3. 实际完成内容

新增只读日期状态服务，综合报名开始、官方/学校/学院有效截止、作品截止和终止状态。未核验或缺可行动日期的记录不进入报名推荐；不因读取修改正式库状态。年份、状态、来源同时匹配同一届次，先精确筛选排序再分页；首页报名计数、公共列表和详情统一当前日期口径。

学校选择取得完整目录，切换学校清除旧学院。列表30条分页并保留筛选；卡片和首页简表携带届次ID。详情区分官方与校内截止，展示通知日期、来源、认定依据、结构化历史及历届记录；有核实字段来源的历史正文保留展示，没有联合主办时不显示该栏。资料缺失时说明缺口，不生成历史。

新增 `/contribute`、导航及页脚入口，支持未收录赛事、学校/专业、通知、认定及历史资料。登录后返回原页面；提交中禁用按钮、失败保留输入、成功显示编号并刷新个人记录。补充可审核为需更多证据、拒绝、重复、已核验待整理入库；专用记录不会混入通用反馈审核。

截止纠错必须明确目标届次、来源URL和新截止，审批只更新该届，保留事实修订、更新事件和管理员审计。其他类型的审核通过仍需人工维护正式事实，界面明确这一限制。

## 4. 修改文件列表

共48个产品、测试及文档文件。新增文件注明“新增”。

后端实现：

- `backend/app/api/router.py`
- `backend/app/api/routes/admin.py`
- `backend/app/api/routes/competitions.py`
- `backend/app/api/routes/users.py`
- `backend/app/api/routes/supplements.py`（新增）
- `backend/app/core/exceptions.py`
- `backend/app/repositories/competition_repository.py`
- `backend/app/repositories/stats_repository.py`
- `backend/app/schemas/competition.py`
- `backend/app/schemas/v1.py`
- `backend/app/services/competition_service.py`
- `backend/app/services/deadline_resolution_service.py`
- `backend/app/services/edition_status_service.py`（新增）
- `backend/app/services/personal_competition_service.py`

测试：

- `backend/tests/test_core_user_journey.py`（新增19项）
- `backend/tests/test_contribution_workflow.py`（新增10项）
- `backend/tests/test_deadline_resolution_service.py`
- `backend/tests/test_v1_notifications_product.py`

前端页面：

- `frontend/src/app/page.tsx`
- `frontend/src/app/competitions/page.tsx`
- `frontend/src/app/competitions/[id]/page.tsx`
- `frontend/src/app/competitions/[id]/not-found.tsx`（新增）
- `frontend/src/app/contribute/page.tsx`（新增）
- `frontend/src/app/admin/page.tsx`
- `frontend/src/app/admin/review/page.tsx`
- `frontend/src/app/error.tsx`
- `frontend/src/app/loading.tsx`（新增）
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/my-competitions/page.tsx`

前端组件与接口：

- `frontend/src/components/AppShell.tsx`
- `frontend/src/components/CompetitionCard.tsx`
- `frontend/src/components/SchoolSelector.tsx`（新增）
- `frontend/src/components/StatusBadge.tsx`
- `frontend/src/components/v09/CorrectionForm.tsx`
- `frontend/src/components/v09/ContributionHistory.tsx`（新增）
- `frontend/src/components/v09/NotificationBell.tsx`
- `frontend/src/components/v09/PersonalContext.tsx`
- `frontend/src/components/v09/PersonalHome.tsx`
- `frontend/src/components/v09/ProfileForm.tsx`
- `frontend/src/components/v09/SessionButton.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/lib/v09-api.ts`
- `frontend/src/lib/use-session.ts`（新增）

文档：`README.md`、`docs/CURRENT_TASK.md`、`docs/CORE_USER_JOURNEY_20260927.md`（新增）、本报告（新增）。登录相关组件的小改动用于共享会话状态及修复已有 lint 问题，没有重做个人中心。

## 5. 数据库是否修改

正式数据库内容及 schema 均未修改，没有新增迁移。补充复用 `beta_feedback` 保存用户归属、`review_queue` 存审核信息；纠错继续使用 `user_correction_submissions` 并同步审核队列。只有内存/临时测试库和 `.codex-qa` 下独立副本有验收写入。

## 6. API 是否修改

新增：`POST/GET /api/users/me/supplements`、`GET /api/admin/review/supplements`、`PUT /api/admin/review/supplements/{id}`。

增强：`GET /api/competitions` 动态状态、同届次范围筛选、排序后分页；`GET /api/competitions/{id}` 支持 `edition_id`；列表新增 `current_edition_id`、`registration_closing_soon`；`GET /api/stats` 报名计数按当前日期计算。学校范围缺必需学校/学院参数返回422。

用户纠错及审批校验届次归属、来源格式和审批对象，同步队列并返回审核意见。补充要求登录、限制提交速率，审核要求管理员。修复校验异常序列化，使非法URL返回422而非500。URL格式校验不等于网页真实性核验，管理员仍需对照来源内容。

## 7. 前端是否修改

是。保留现有视觉体系，完善首页、搜索筛选、详情、登录返回、补充和审核页。学校选择没有面向用户的985/211/一本/二本等级。新增加载占位、真实404、可重试错误、空结果及提交反馈。1440px桌面、390px手机实测无横向溢出；未宣称做过完整无障碍审计或全部浏览器兼容验收。

## 8. 新增/修改测试

新增29项后端回归：过期状态、未来报名开始、未核验/终止状态、官方日期优先、校内截止、同届次来源/年份、冲突筛选、排序后分页、动态统计；登录和管理员权限、非法来源、提交只待审、跟踪审核、错误届次拒绝、只更新指定届次并保留修订、禁止从通用反馈绕过补充审核。

调整两处旧 fixture 为已核验学校通知，截止通知测试显式指定届次。未修改数据库隔离、安全连接或 fixture 基础设施。关键问题先用失败回归复现，再修复到通过。

## 9. 测试结果

| 验证 | 结果 |
| --- | --- |
| 后端 `python -m pytest -q -o addopts=''` | 261 passed，15.18秒；起始基线232项 |
| 前端 `npm run lint` | 通过，0警告 |
| 前端 `npm run typecheck` | 通过 |
| 前端 `npm run build` | 通过，Next.js 16.3.3 |
| 浏览器主流程 | 13项通过，桌面/手机，无捕获到的页面脚本异常 |
| API中断 | 1项通过，错误页与重试入口存在，不误报空结果 |
| 服务恢复/手机视口/首页届次链接 | 4项通过 |
| 独立只读代码审查 | 3项P2问题已修复并验证 |
| `git diff --check` | 按仓库现有换行设置通过 |

浏览器覆盖搜索、普通高校筛选、学校截止、历史依据、真实404、两页无重复、登录返回、503失败保留输入再成功、个人记录即时刷新、指定届次截止更新、补充审核状态及手机导航。官方链接检查了渲染和目标URL，本轮未逐一联网核验官网内容。构建时曾暴露 Next 内部控制流被错误捕获，已移除该捕获并通过构建。

证据在被忽略的 `.codex-qa/core-browser-results.json`、`core-error-results.json`、`core-recovered-results.json`、`core-20260927-shots/`。验收赛事/学校明确标注“验收专用”，只在副本存在；凭据和数据库副本不进入 Git。服务端曾出现 Node `Gzip` 监听器数量警告，未导致本轮功能失败；尚未进行长时性能或压力验证，不宣称解决框架级资源问题。

## 10. 生产数据库安全检查

正式 `data/v02.sqlite` 起始和验收后 SHA256 一致：

`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`

初始结构/计数查询使用只读连接；自动化测试沿用内存/临时库及防误连接机制；浏览器 API 明确配置 `ENVIRONMENT=test` 和 `.codex-qa/core-20260927.sqlite`。没有正式迁移、抓取、导入、清理或生产服务器操作。正式库50条历史已批准纠错保持原样。测试隔离实现没有被重复重构。

## 11. 当前用户完整操作链路

首页查看当前报名/即将开始/提交节点 → 搜索与方向/标签/状态筛选 → 选择学校及学院 → 按有效截止分页 → 进入同一届次 → 查看主办方、日期、历届及有来源历史 → 查看本校通知和认定 → 打开官方依据 → 登录后纠错或提交未收录信息 → 查看待审状态及审核意见。

管理员在 `/admin/review` 核对来源并确认届次/日期后，截止纠错更新该届并保留修订和审计。一般补充进入核验/待整理阶段，不直接变正式事实。该链已在副本中实际写入并复查返回值。

## 12. 仍未完成事项

- 数据完整度仍低：176个原始赛事对象中主办方94、官网43、创办年份8、结构化历史5、历史正文0、detail_ready19；108个届次仅19个有报名截止。没有生成资料填缺口，可行动结果自然有限。
- 通用补充尚无覆盖全部实体/字段的正式入库编辑器；截止以外的纠错通过后仍需人工维护。补交证据、已处理记录及审核分页仍需增强。
- 后台赛事、学校、通知、政策、任务和会议的全面维护未完成；会议前端未完成。
- 个性化模块的历史通知回退、届次选择与公共大厅仍有既存差异；截止更新内部提交与外部审核审计需后续统一事务。
- 当前应用层精确筛选适合小目录，扩量需查询优化；普通高校覆盖不等于全国覆盖，没有启动大抓取。

数据补全流程：按缺失字段选小批赛事 → 收集官方/主办方/学校材料、URL和日期 → 用户入口或候选事实保存证据 → 人工确认实体、届次、字段及冲突 → 预览差异后写入，保留字段来源/修订/审核人 → 详情抽检并保留未确认项。新增入口已完成提交及审核；通用字段预览/写入仍是下一阶段，流程设计不能算作已实现。

## 13. 下一阶段优先级

P0：完成已核验补充的字段维护、入库预览及事务性审计，先支持官网/主办方/历史节点；小批高价值赛事逐字段补证据。

P1：完善审核工作台、补交证据和政策/通知维护；统一个人中心与大厅届次规则；以可暂停、去重、可追踪批次扩大有限普通高校样本。

P2：基于现有独立会议 API 建列表、详情、CFP及目录来源页，不做巨量会议抓取。

## 14. 是否需要用户决定

本阶段没有需要用户决定的阻塞项。没有数据删除、不可逆迁移或部署配置修改。代码留在当前工作区供审查；以后涉及批量正式写入、核心规则变化或部署时，再针对具体改动确认。
