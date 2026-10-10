# 安全与数据一致性修复报告

日期：2026-09-27。依据：用户指定的八类修复，以及 `INDEPENDENT_REVIEW_20260927.md` 的实际复现。保留此前48个文件的开发改动和独立审查报告；本轮没有新增产品功能、抓取数据、正式迁移、生产清理、提交、推送或部署。

## 1. P1是否彻底修复

**本轮确认的私人提交泄露路径已封闭。** R01的根因是新增用户提交进入通用 `ReviewQueue`，旧公开政策队列却没有鉴权。修复在后端读取入口要求管理员权限，覆盖所有状态和分页参数；不是靠前端隐藏。

| 读取/操作入口 | 当前权限 |
| --- | --- |
| `GET /api/v0.2/policies/review-queue` | 管理员；匿名、A、B均401/403 |
| `GET /api/admin/review/{corrections,supplements,feedback,leads,candidate-facts,updates,summary}` | 管理员 |
| `GET /api/users/me/{corrections,supplements}` | 当前有效账号；SQL先按所有者过滤，再分页 |
| `PUT /api/admin/review/{corrections,supplements,feedback}/{id}` | 管理员；普通用户枚举ID不能审核 |
| `POST /api/users/me/{corrections,supplements}` | 后端从身份确定所有者，不接受伪造归属/管理员/终态 |
| `POST /api/beta-feedback` | 既有匿名提交入口；没有公开读取反馈正文的GET |
| 公开统计/覆盖率 | 聚合数量，不序列化私人正文、联系方式或审核意见 |

真实签名Bearer测试覆盖anonymous、A、B、admin，未override认证依赖。A/B只能读取本人记录与审核意见，伪造 `user_id` 参数不改变归属；管理员按管理权限访问。停用账号旧令牌不再有效。500响应不再返回SQL、参数或异常路径，仅返回通用错误和关联ID，详细异常留在服务端日志。

此结论针对已追踪的用户补充、纠错、审核队列与反馈读取路径，不宣称完成全平台安全认证。独立会议候选接口使用另一套爬取模型，不读取本轮私人提交，未扩大本轮改动范围。

## 2. 实际修复的高优先级P2

原审查11项P2中，本轮修复9项：**R02、R03、R04、R05、R07、R08、R09、R10、R11**。另外修复既存的时区偏移、未核验事实公开、自由文本创建已核验目录、停用令牌、500异常细节泄露和手机退出入口问题。R06、R12按scope保留。

## 3. 每类问题的根因与修复

| 问题 | 根因 | 修复结果 |
| --- | --- | --- |
| R01私人队列泄露 | 通用公开队列没有身份要求 | 后端管理员鉴权，所有者查询在SQL层隔离 |
| R02部分审批成功 | 截止更新服务先commit，队列和审计后写 | 服务只flush，审核入口统一commit；异常显式rollback |
| R11终态被覆盖 | 只检查ORM旧快照，随后无条件更新 | 按ID、原状态、原reviewed_at条件更新；竞争失败409 |
| R03开放重定向 | startsWith检查未考虑URL控制字符归一化 | 解析并比较origin；拒绝控制字符、反斜杠、协议相对地址和多层编码歧义；只返回站内path/query/hash |
| R04历史混当前 | 个人模块只收赛事ID，选择最新届并回补历史通知 | 明确透传届次/学校/学院；来源、通知、修订、更新事件按届次读取；缺值unknown/null，无跨届fallback |
| R05/R07时间窗口 | 校内开始依附截止来源；校内与官方阶段混用；关键顺序缺校验 | 分开解析作用域起止，显式空开始不套官方阶段；矛盾窗口不进入可行动推荐 |
| R08/R09审核不可达 | 仅pending过滤；固定第一页；本人历史无界查询 | 未完成/需补证/终态筛选，九个API有界分页，用户两类历史分别翻页，管理员各tab可继续访问 |
| R10账号残留 | 状态不按身份清理，旧请求还能回写 | token变化重新挂载私人组件树；资源快照绑定身份与请求；丢弃旧响应，失败显示空/错误 |
| 时区偏移 | SQLite丢掉偏移，重新读取后把墙上时间当UTC | 中央UTC类型绑定/读取与赋值规范化；存储、API、显示统一约定 |
| 未核验信息成事实 | 多条公开查询只排除demo，未检查审核状态 | 赛事、届次、来源、政策、认定、个人理由与学院筛选使用核验门槛；结构化事实逐项过滤 |

审核事务覆盖事实、纠错/反馈、ReviewQueue、修订、变更事件、通知、管理审计。正常批准/拒绝、重复批准/拒绝、需补证后继续审核、审计故障、真实数据库约束异常、提交边界异常均有回归。失败后新Session读取全部保持原状，重试可成功。补充的 `verified_pending_import` 是核验终态，仍不自动写正式事实。

分页保留兼容的数组响应：`limit=1..100`、`offset>=0`，默认50/0；前端每页显示20条、请求21条判断下一页，排序增加ID保证同时间记录稳定。未完成包含 `pending + needs_more_evidence`，已核验待整理、拒绝、重复等可按状态访问。

身份切换覆盖提交记录、个人首页、个人中心、个人上下文、日历、资料、通知、审核与表单草稿。当前token的401会清会话；A的迟到401不会清掉B。403/网络失败不会保留A的内容。跨标签storage事件、登出、token刷新、迟到成功响应和响应JSON读取阶段的身份变化均被覆盖。

**时间约定：** SQLite存无偏移的UTC值，ORM及API输出明确UTC（Z或+00:00），前端显示Asia/Shanghai，后台datetime-local明确标注北京时间并携带+08:00转换。无时区输入按UTC处理，不依赖服务器/浏览器本地时区。没有用统一加减8小时修补。

已有无时区数据按UTC解释，不猜测修正历史污染；旧JSON若只保存日期，无法凭空恢复时分秒。新变更事件保留完整UTC时间，不声称本轮已经校正正式库全部历史时间。

核验规则保守排除显式pending/reviewing/conflicting等负面状态，即使与verified布尔位冲突；兼容既有默认 `unverified + is_verified=True` 记录。公开“收录”必须recognized、无需人工复核且政策已核验；公开政策解析仍保留可信的明确否定结论。用户自由文本仅保存个人资料，不再自动生成共享的已核验学院/专业。

## 4. 修改文件

本轮实际触及**64个文件**：原阶段48文件中继续修改25个、本轮新触及已有文件26个、本轮新增13个。当前相对HEAD累计diff为**88个文件（62个已跟踪修改＋26个未跟踪文件）**，包含前阶段工作及独立审查报告，不是本轮新写88个文件。无文件删除、依赖包变更或意外数据库/缓存/凭据产物进入diff。

完整本轮文件清单和相对原48文件的变化记录见忽略目录 `.codex-qa/security-fix/final-snapshot.json`；它区分“原阶段文件继续修改”“本轮新触及的已有文件”“本轮新增文件”。主要文件如下：

- 后端权限/审核：`api/deps.py`、`api/routes/admin.py`、`supplements.py`、`policies.py`、`users.py`、`core/exceptions.py`、`services/notification_service.py`。
- 后端时间/届次/可信度：`models/base.py`、`api/routes/competitions.py`；`services/competition_service.py`、`deadline_resolution_service.py`、`edition_status_service.py`、`personal_competition_service.py`、`competition_freshness_service.py`、`home_data_service.py`、`policy_data_service.py`、`policy_resolution_service.py`、`university_service.py`、`user_facing_data_policy.py`；`repositories/competition_repository.py`、`policy_repository.py`、`university_repository.py`。以上路径均在 `backend/app/`。
- 前端页面：`app/login/page.tsx`、`app/admin/review/page.tsx`、`app/competitions/[id]/page.tsx`、`app/my-competitions/page.tsx`、`app/notifications/page.tsx`、`app/onboarding/page.tsx`、`app/settings/profile/page.tsx`，以及calendar/data的时区显示。
- 前端组件/共用逻辑：`components/v09/ContributionHistory.tsx`、`PersonalContext.tsx`、`PersonalHome.tsx`、`PersonalCalendar.tsx`、`NotificationBell.tsx`、`CorrectionForm.tsx`、`FeedbackButton.tsx`、`SessionButton.tsx`、新增 `SessionBoundary.tsx` / `Pagination.tsx`；`components/ActivityFeed.tsx`；`lib/api.ts`、`v09-api.ts`、`format.ts`、新增 `safe-return-path.ts` / `use-private-resource.ts`。以上路径均在 `frontend/src/`。
- 测试与文档：下面第5节列出的回归文件、5个旧测试文件的UTC预期/核验夹具调整、`frontend/package.json` 的test命令、修复计划、本报告、README及CURRENT_TASK。未新增依赖或修改lockfile。

## 5. 新增测试

- `backend/tests/test_review_security_regressions.py`：135项，真实权限、ID枚举、停用身份、所有状态、事务故障、DB错误、并发终态、分页边界。
- `backend/tests/test_edition_time_fact_boundaries.py`：53项，2024/2025/2026、显式错配/缺值、同届来源、校内开始、UTC往返、DST、未核验/矛盾标记、个人自由文本与目录隔离。
- `frontend/tests/api-security.test.mjs`、`security-regression.test.mjs`、`detail-scope.test.mjs`：合计30项；`browser-harness.mjs` 使用已安装的真实React/Edge，覆盖DOM和SSR hydration；Next导航、图标和HTTP边界使用测试替身。
- 旧测试修改仅为UTC契约或明确verified的展示夹具，及把此前允许pending公开的断言改为排除pending。没有放宽生产过滤或绕过测试隔离。

## 6. 修复前失败证据

证据均在 `.codex-qa/security-fix/`，先运行失败测试再修改实现：

| 组 | 修复前真实结果 | 文件 |
| --- | --- | --- |
| 权限/事务/分页初组 | 85 failed、44 passed | `red.txt`、`red-counts.txt` |
| 届次/时区初组 | 22 failed | `edition-time-red.txt` |
| 来源/事实范围补测 | 8 failed、23 passed | `edition-facts-scope-red.txt` |
| 其他公开入口补测 | 4 failed、31 passed | `edition-extra-red.txt` |
| 待审届次/结构化字段 | 7 failed、35 passed | `pending-edition-red.txt` |
| 学院筛选/demo政策 | 2 failed、42 passed | `recognition-filter-red.txt` |
| 矛盾核验标记 | 9 failed、44 passed | `verification-conflict-red.txt` |
| 前端初组 | 13 failed、1 passed | `frontend-red-final.txt` |
| SSR与显式届次纠错 | 修复前失败、修复后通过 | `frontend-hydration-detail-red.txt` / `green.txt` |
| 手机退出 | 真实390px页面按钮不可见 | `frontend-mobile-red.txt` |

这些分轮结果包含重复用例，不能相加为新增缺陷数量。后端中途全套的日期比较/旧夹具失败均已修复并纳入最终449项，未隐藏失败或跳过测试。

## 7. 修复后验证结果

后端449项、前端30项及17项真实端到端全部通过。权限、事务、历史届次、分页、账号切换、时区和未核验信息七组专项均包含在最终套件中。补丁空白检查通过；临时服务已停止，Next开发类型由正常build恢复。

## 8. 后端完整测试

工作目录 `backend`：

```powershell
.\venv\Scripts\python.exe -m pytest -q -o addopts=''
```

**449 passed in 26.61s**，其中原261项＋本轮新增188项。日志：`.codex-qa/security-fix/backend-final.txt`。`TEST_DB_ISOLATION = PASS`：沿用未修改的conftest防误连接、内存fixture及显式临时副本；生产库未作为pytest连接目标。

## 9. 前端验证

工作目录 `frontend`：

```powershell
# 复用本机已有的浏览器自动化运行库，无需新增项目依赖
$env:NODE_PATH='C:\Users\时生\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
npm test
npm run lint
npm run typecheck
npm run build
```

- 正式回归：**30 passed、0 failed**，45.6秒；详见 `frontend/tests/README.md` 的运行前提。
- lint：通过，0警告。
- typecheck：通过。
- build：Next.js 16.3.3正常配置构建通过，18/18静态生成阶段完成；未把测试API地址写入配置。

日志分别为 `frontend-green-final.txt`、`frontend-lint-final.txt`、`frontend-types-final.txt`、`frontend-build-final.txt`。

## 10. 浏览器验证

使用真实Edge、正常Next服务及真实FastAPI，仅连接新建的空白合成数据库。没有复制用户资料或正式记录。测试数据含3个账号、3届赛事、101条补充、102条纠错及已核验/待审核政策。

最终 **17/17通过，0 pageerror**，详见 `browser-results.json` 和 `shots/`：

- anonymous/A/B/admin实际HTTP权限；他人归属参数无效；公开未核验认定/政策排除。
- 2024无日期保持未知，2025只显示2025学校截止，2026不复用旧学校通知；相应来源/修订/事件按届次隔离。
- 浏览器设America/Los_Angeles，2025 UTC跨日仍显示正确上海日期；后台填写北京时间00:00，API保存前日16:00Z。
- 用户两类历史各6页完整访问101/102条；管理员6页访问全部101条补充，需补证记录可拒绝并在终态筛选再次找到。
- 跨标签A→B且503不显示A；管理员→普通用户403不显示审核数据；过期令牌清理；手机退出可见并清除私人内容。
- 控制字符、双重编码、反斜杠返回地址留在站内；正常path/query/hash保留。外部请求全部在测试拦截器中阻断。

首次端到端发现真实SSR会话恢复误跳登录，13通过/3失败；增加renderToString+hydrateRoot回归后修复。第二次的两项失败来自测试脚本对包含option文本的label做精确匹配，修正选择器并用新的合成库重跑后全绿。未把这两项脚本错误误记为业务修复。相关中间证据仍保留。

## 11. 正式数据库前后SHA256

目标：`D:/Python/xuesheng/data/v02.sqlite`。

修复前和全部测试后均为：

```text
9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320
```

只做文件哈希读取，无正式库连接测试、迁移、入库、清理或不可逆数据修改。最终文件清单与哈希保存在 `final-snapshot.json`。

## 12. 是否产生schema变化

**没有DDL/schema迁移。** UTCDateTime改变Python绑定与读取语义，现有时间列仍编译为原DATETIME，专门测试遍历全部时间列验证。未新增表、列、索引或约束；正式库迁移版本保持 `202609060005`。

## 13. 剩余P2

- **R06**：首页按一个代表届次计数，仍可能与按状态匹配其他届次的列表不一致。
- **R12**：列表/统计仍有全量ORM加载成本。本轮没有做无关性能优化。
- 其他既存产品缺口仍单独保留：个人中心默认届次与大厅代表届次的统一、用户补证后重新提交的编辑流程、注册完成后保留返回路径、部分旧客户端请求无超时、首页关键词搜索未保留学校上下文。已核验待整理信息的字段级入库预览仍未实施。
- 历史时间污染、已存在的不实目录记录没有清理；旧日期JSON无法恢复缺失精度。本轮只阻止新的错误读写并过滤公开输出。

没有确认本轮范围内尚未修复的新P0/P1。

## 14. 剩余P3

- **R13**：unknown筛选可能把“没有匹配届次”当成“未知届次”。
- **R14**：重复source_scope查询参数导致Next字符串数组处理异常。
- 旧 `/api/home` 与当前首页数据口径的历史债务保留；本轮仅修复统一UTC引出的类型比较，未重写其生命周期规则。

## 15. 是否建议批准此前48文件改动

**本轮八类安全与数据一致性修复可验收，但仍不建议把此前48文件整体标为“全部审查通过”。** 原P1和本轮选定P2已有实证闭环，R06、R12、R13、R14仍明确留存。此次没有merge/push；是否接受剩余风险应在下一轮验收范围中明确，不能用全绿测试代替未完成的审查项。

## 16. 是否可以进入下一阶段

**可以进入有界的剩余一致性修复与独立复审阶段。** 优先统一R06计数/列表口径与默认届次选择，然后根据目录规模决定R12优化；R13/R14单独小修。暂不扩大抓取、建设会议新页面、清理正式历史数据或开始字段级入库功能，也不据此进行正式部署。

接续入口为 `CURRENT_TASK.md`。本轮具体执行计划见 `SECURITY_FIX_PLAN_20260927.md`；此前独立审查报告保留原始结论与证据，不回写为“当时已通过”。
