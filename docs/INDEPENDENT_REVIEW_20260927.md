# 阶段开发独立审查报告

日期：2026-09-27。审查基线：当前工作区相对 `dbca5eb`，不是上一轮报告中的完成声明。方法：逐域独立阅读全部修改/新增文件、交叉检查调用链、重跑测试与构建、隔离内存诊断、独立数据库副本中的真实浏览器验证。

本轮没有修复业务代码、修改正式测试或改写上一轮文档。允许的诊断脚本、日志、截图和副本仅位于被 Git 忽略的 `.codex-qa/`。唯一新增的非忽略文件是本报告。

## A. 总体结论

**暂不建议批准这批改动。** 实际范围是 **48个文件：36个已跟踪修改、12个新增、0个删除**，不是51个。现有261项后端测试及前端 lint/typecheck/build 均通过，但独立验证发现了测试未覆盖的隐私、状态、审核与日期问题。

本批新增或放大的问题共14项：**P0 0项、P1 1项、P2 11项、P3 2项**。既存问题另外列出，不混算成此次新增回归。普通用户直接调用新增管理员接口会被拒绝，但旧公开审核队列造成另一条匿名读取路径，这是不能批准的明确原因。

改动有实际价值：同届次公开列表筛选、排序后分页、学校选择、错误与空结果分离、补充待审入口已实现。审查结论针对可复现缺陷，不要求推倒重做。

## B. P0 问题

本次检查未确认 P0：没有发现本轮新增的管理员身份伪造、生产库删除/迁移、凭据提交或大规模正式数据损坏。这个结论限定于已执行的检查，不等于整个平台已完成安全认证。

## C. P1 问题

### R01：匿名用户可以读取未审核提交及审核意见【新增泄露面】

位置：[users.py:360](D:/Python/xuesheng/backend/app/api/routes/users.py:360)、[supplements.py:33](D:/Python/xuesheng/backend/app/api/routes/supplements.py:33)；漏口在 [policies.py:101](D:/Python/xuesheng/backend/app/api/routes/policies.py:101) 和 [policy_repository.py:126](D:/Python/xuesheng/backend/app/repositories/policy_repository.py:126)。

本轮将用户纠错/补充送入通用 `ReviewQueue`。既存 `GET /api/v0.2/policies/review-queue` 没有鉴权，也不限制队列类型/所有者。真实令牌提交后，匿名 GET 返回200，包含 `PRIVATE_PENDING_CORRECTION`、`PRIVATE_PENDING_SUPPLEMENT`；请求 `?status=verified_pending_import` 还能读到 `PRIVATE_REVIEW_NOTE`。分页和状态参数使该接口可以继续枚举。

影响：未公开的用户描述、来源地址及审核意见对匿名访问者可见。`/users/me/*` 的所有者过滤没有封闭这一旁路。旧接口公开是既存行为，但用户内容进入公开查询是本次引入。

最小修复：让队列接口要求管理员权限；如需保留公开政策队列，则显式白名单允许的公开类型，并在所有状态下排除用户提交及私人审核意见。加入匿名/其他用户对全部队列状态的反向测试。

## D. P2 问题

### R02：审批返回失败，事实却已提交，重试也无法恢复【放大既存事务问题】

位置：[admin.py:124](D:/Python/xuesheng/backend/app/api/routes/admin.py:124)、[notification_service.py:214](D:/Python/xuesheng/backend/app/services/notification_service.py:214)；队列同步在 [admin.py:133](D:/Python/xuesheng/backend/app/api/routes/admin.py:133)，终态重试限制在第98行。

对审计写入注入故障后，API返回500；回滚并用新 Session 读取，纠错已 `approved`、队列仍 `pending`，截止已更改，修订/事件/通知各1条，新增管理审计0条。重试返回409。提前提交原本存在，本轮新增队列同步和终态锁定使不一致扩大且无法正常重试。

最小修复：更新服务只 flush，由审批入口统一提交事实、修订、队列、通知和审计；故障注入测试检查回滚后的全部表，而非仅状态码。

### R03：登录返回地址可绕过同站限制【新增】

位置：[login/page.tsx:23](D:/Python/xuesheng/frontend/src/app/login/page.tsx:23)。

`/login?next=%2F%09%2Fevil.example` 中的制表符通过 `startsWith` 检查；URL解析时被移除，变成异源 `http://evil.example/`。真实浏览器登录后确认发起外部导航。本次在浏览器请求拦截器中直接返回诊断页面，**没有访问外站**。

影响：可信登录入口可被用于登录后钓鱼跳转；本次未发现令牌通过该跳转自动泄露。最小修复：用当前 origin 解析 URL，再比较解析后的 origin，只传内部 pathname/search/hash；覆盖制表符、换行、回车、反斜杠及正常内部地址。

### R04：指定历史届次时仍展示当前届的个人截止【本轮届次入口与旧个人模块错配】

位置：[competitions/[id]/page.tsx:95](D:/Python/xuesheng/frontend/src/app/competitions/[id]/page.tsx:95)、[PersonalContext.tsx:16](D:/Python/xuesheng/frontend/src/components/v09/PersonalContext.tsx:16)、[personal_competition_service.py:141](D:/Python/xuesheng/backend/app/services/personal_competition_service.py:141)。

详情已支持 `edition_id`，个人上下文却只接收赛事ID。浏览器选中2025已结束届次，仍显示“当前正在报名”“你的截止：2026/10/07”。该个人模块还将2025学校通知回退为2026的关联理由；大厅同范围筛选返回0，个人中心却显示学校有通知。

旧个人中心最大年份/历史通知回退是既存逻辑；本轮提供指定届次详情而未同步约束个人模块，产生同页冲突。最小修复：个人上下文一起接收明确届次和学校范围，或在无法对应时隐藏个人截止；历史通知标明历史，不用作当前届次依据。

### R05：校内报名开始时间丢失或与官方窗口混用【新增】

位置：[deadline_resolution_service.py:95](D:/Python/xuesheng/backend/app/services/deadline_resolution_service.py:95)、[edition_status_service.py:29](D:/Python/xuesheng/backend/app/services/edition_status_service.py:29)。

开始时间通过“选中的截止来源 notice_id”反查。固定当前09-27：已核验学校通知09-30开始、校内截止缺失、官方10-17截止，解析结果开始时间为 null、状态却为报名中。另一输入为校内09-29截止、官方10-02才开始，两个不同阶段被拼成矛盾窗口，返回 unknown，校内选拔从可参加列表消失。

最小修复：按作用域分别解析开始和截止及其证据，校内开始缺失不自动套入另一阶段的官方开始；需要能区分“明确无校内开始值”和“未提供覆盖参数”。

### R06：首页报名计数与报名列表不一致【新增回归】

位置：[stats_repository.py:52](D:/Python/xuesheng/backend/app/repositories/stats_repository.py:52)。

同一赛事2026届正在报名、7天后截止，2027届明天开始。未筛选列表选择动作更近的2027届，于是统计报名中为0；`edition_status=registration_open` 却返回2026届1条。作品提交计数也有同类风险。

最小修复：按各状态列表同样的届次匹配规则计数并按赛事去重，不能从一个未筛选代表届次推导全部状态计数。

### R07：报名开始晚于比赛结束仍进入近期可参加列表【新增规则遗漏】

位置：[edition_status_service.py:32](D:/Python/xuesheng/backend/app/services/edition_status_service.py:32)。

当前09-27、比赛09-28结束、报名09-30开始/10-17截止，输出 `registration_upcoming`，行动节点为09-30。已有校验只处理报名开始/截止，以及已经过去的比赛结束，未检查跨阶段明显矛盾。

最小修复：可行动判断前检查关键时间顺序，冲突返回未知并保留原事实供审核，不自行修改日期。这是异常数据条件下的错误推荐，因此列P2。

### R08：“需要更多证据”的纠错消失于审核界面【新增回归】

位置：[admin/review/page.tsx:46](D:/Python/xuesheng/frontend/src/app/admin/review/page.tsx:46)。

HEAD 查询全部纠错，本轮改成仅 `pending`。浏览器把一条纠错标为需更多证据后，页面显示暂无待审；API按该状态查询仍能查到，但页面没有状态筛选，用户也没有补证后重新送审入口。上一轮将其写作既存缺口不准确，本次 diff 已确认查询过滤是新引入。

最小修复：保留未完成状态的可达审核入口，支持待审/需补证筛选或重新审核；补证编辑可分后续实现，但不能让记录失去入口。

### R09：补充审核超过50条会出现无法触达的待审记录【新增】

位置：[supplements.py:49](D:/Python/xuesheng/backend/app/api/routes/supplements.py:49)、[v09-api.ts:264](D:/Python/xuesheng/frontend/src/lib/v09-api.ts:264)、[admin/review/page.tsx:145](D:/Python/xuesheng/frontend/src/app/admin/review/page.tsx:145)。

副本构造51条：最新50条均已核验待整理，最早1条 pending。接口默认只返回最新50条且包含已核验记录，前端无 offset/翻页；浏览器看不到最早待审项，也无下一页控件。手动请求 offset=50 能取到。

最小修复：接通分页，并区分待审核与待整理状态；51条以上的边界测试不能只检查返回长度。

### R10：账号切换失败后保留前账号私人提交【新增】

位置：[ContributionHistory.tsx:18](D:/Python/xuesheng/frontend/src/components/v09/ContributionHistory.tsx:18)。

账号A加载记录后，在另一标签切换到B并让B的列表请求503，真实浏览器继续显示A的描述，同时提示加载失败。另一用户的后端本人接口返回空，说明这是客户端状态没有按身份隔离，并非该接口的IDOR。代码也未防旧请求晚到覆盖新身份结果。

最小修复：会话改变时清空列表/加载/错误状态，以请求代次或取消机制丢弃旧会话响应；覆盖切换失败和乱序响应。

### R11：并发审核可覆盖已拒绝终态【新增】

位置：[supplements.py:61](D:/Python/xuesheng/backend/app/api/routes/supplements.py:61)。

两个独立 Session 先读同一 pending，A拒绝并提交，B持旧快照执行核验通过，双方均成功，最终 `verified_pending_import`。这是确定的交错执行复现，不是并发HTTP压力测试。

最小修复：按预期状态/版本做条件 UPDATE，冲突返回409；同事务同步反馈、队列和审计。再读一次普通 SELECT 不能消除竞态。

### R12：页面大小不限制加载量，统计又重复全量加载【新增性能代价】

位置：[competition_service.py:91](D:/Python/xuesheng/backend/app/services/competition_service.py:91)、[competition_service.py:117](D:/Python/xuesheng/backend/app/services/competition_service.py:117)、[stats_repository.py:52](D:/Python/xuesheng/backend/app/repositories/stats_repository.py:52)。

`limit=1` 仍加载全部匹配赛事及关系后切片。独立内存实验每赛事仅一个届次，200/2000/5000赛事分别加载400/4000/10000个ORM对象，用时0.042/0.300/0.871秒，SQL为8/29/71条。真实关系更多，首页又发多个不同状态请求，加上 stats 再完整序列化一次。

最小修复：先使用等价数据库条件缩小候选及必要字段，统计不构建完整卡片，复用请求内计算；优化必须保持同届次、排序后分页语义。当前176条目录未出现性能事故，不能把合成数据耗时当作生产SLA，但增长成本已实证。

## E. P3 问题

**R13：unknown 状态过滤会返回原本已知状态的赛事。** [competition_service.py:189](D:/Python/xuesheng/backend/app/services/competition_service.py:189) 过滤后无匹配届次返回 None，后续 `status(None)` 又变成 unknown。只有一个已核验报名中fixture，查询 unknown 返回该赛事，届次和截止被清空。应区分“真实未知届次”与“没有匹配届次”。当前UI无此选项，列P3。

**R14：重复查询参数导致页面异常。** [competitions/page.tsx:41](D:/Python/xuesheng/frontend/src/app/competitions/page.tsx:41) 对 Next 的字符串数组调用 startsWith。浏览器访问 `?source_scope=official_current&source_scope=university_notice` 出现错误页，服务端记录 `startsWith is not a function`。应规范化或拒绝重复参数；普通表单不产生重复参数，列P3。

## F. 不必要改动与提交卫生

- 原始范围48个文件全部核对。没有删除、生产迁移、包依赖变更；没有新数据库、缓存、构建产物、.env、调试文件或备份进入待提交列表。
- 36个已跟踪文件为622行增加、348行删除；忽略空白只减少少量变化，不存在整文件格式化掩盖逻辑的情况。
- 6个新前端文件、2个新后端实现、2个新测试、2个新文档均有对应主流程用途。共享会话hook涉及多个旧组件，属于必要性可解释的小范围整理，但带来R10，不能以“lint修复”免于行为验证。
- 删除未用的error参数、未用导入等属于非必要但低风险整理；可分开提交，不构成拒绝整批的独立理由。新的接口类型替代 any 有收益，未发现大规模 schema 复制。
- `api.ts` 仍保留现已不可达的空统计 fallback，仓储旧状态过滤、旧 `/api/home`、个人中心与新服务存在多套口径；这是维护负担，不应再复制新版本解决。
- 新运行时代码没有增加开发机器文件绝对路径；默认127.0.0.1:8001是本地后端默认地址。README 中 D:/Python/... 启动示例是既存路径，不是本轮新增依赖。测试里的2025/2027与示例网址仅在隔离fixture使用，没有混入正式数据。
- 本次 `next dev` 自动临时改变 `next-env.d.ts`，已通过正常 `next build` 恢复。结束前比对原48个文件哈希，全部相同。

## G. 测试覆盖盲区

新增29项测试确实经 FastAPI TestClient、SQLAlchemy和SQLite执行，不是只对函数内部实现作断言。但贡献测试通过 `_current_user` override 返回固定用户，绕过真实令牌解析，并在同一用户对象上切换管理员位；这能验证角色判断，不能覆盖所有认证/跨用户路径。本次额外诊断保留真实令牌验证，浏览器使用真实登录。

| 已有新增测试组 | 实际覆盖 | 未覆盖或本次新证据 |
| --- | --- | --- |
| 过期、未来开始、官方截止优先 | 当前列表/详情/统计、原状态不被改写 | 校内独立开始与跨阶段窗口R05 |
| 缺日期、未核验、取消/结束 | 不进入行动列表，4组参数 | 比赛结束早于报名开始R07 |
| 学校截止及未核验通知 | 指定学校关闭、未核验不覆盖截止 | 开始来源独立缺失、个人模块跨届 |
| 年份、状态、来源同届匹配 | 公开大厅多届筛选和选择 | 登录详情R04、unknown过滤R13 |
| 排序与分页 | 3条新数据的首/次页，limit=1 | 第50/51条审核R09、末页/同截止稳定性、大规模加载 |
| 统计两组 | 单一有效届次的过期和未来开始 | 多有效届次与列表集合一致性R06 |
| 补充待审、普通用户拒绝 | 本人列表、一个管理员GET403、专用/通用反馈隔离 | 匿名旧队列R01、真实多用户、跨标签R10 |
| URL参数3组/未登录 | javascript、file、无效网址422、匿名POST401 | 控制字符返回地址R03、空白/超长等更多边界 |
| 届次归属与成功审批 | 错配422、指定届次更新、修订、二次审批409 | 中途故障R02、并发R11、时区重新读取 |
| 缺来源/届次/日期3组 | 422且保持pending | 成功写入+08及生命周期需补证R08 |

单独的临时诊断不是正式回归，退出0表示观察已完成，不代表被测功能正确。没有把诊断脚本加入正式测试目录。未做完整全站模糊测试、长时负载测试或PostgreSQL执行验证。

## H. 安全问题

本轮明确新增风险为R01匿名数据泄露、R03开放重定向、R10客户端跨身份残留。新管理接口后端确有管理员依赖；真实普通用户 GET/PUT 管理补充及PUT纠错均403，伪造 `is_admin/user_id/status` 不改变权限、归属或pending状态，另一个用户的本人列表为空。

`javascript:`、`data:`、`file:`、含账号密码和损坏IPv6网址，以及超长标题/正文/网址均返回422。新增文本用React文本节点渲染，未发现新增 dangerouslySetInnerHTML/eval；数据库查询使用绑定表达式，没有确认新增SQL注入、路径遍历或XSS。新补充只存URL不主动抓取，未产生对应SSRF执行面。请求采用Bearer头而非自动附带的登录cookie，没有发现此新增流程的传统cookie-CSRF路径；这不等于完成全站安全证明。

另外两项**既存P2**：

- [deps.py:29](D:/Python/xuesheng/backend/app/api/deps.py:29) 不校验 `is_active`。将账户停用后旧令牌仍可读取本人纠错，实测200；HEAD已如此。
- [exceptions.py:18](D:/Python/xuesheng/backend/app/core/exceptions.py:18) 将 `str(exc)` 放进500响应，可能含数据库语句、参数或路径。此行未在本轮更改；确认的是错误文本外发机制，没有声称获取到真实密码或密钥。应在生产响应中只返回通用错误及关联ID，详细异常留受控日志。

## I. 数据完整性问题

R02/R11分别破坏审批原子性与状态竞争保护。另确认**既存P2时区缺陷**：[competition_freshness_service.py:115](D:/Python/xuesheng/backend/app/services/competition_freshness_service.py:115) 原样赋值日期，SQLite普通 DateTime 丢弃偏移，而读取代码将naive视作UTC。

真实审批API成功输入 `2026-10-06T23:59:59+08:00`，应存UTC15:59:59，却在新Session读到naive23:59:59，晚8小时。日期探针还确认相同记录入库前已截止、重新加载后却报名中。当前后台UI先调用 toISOString，走该UI时为UTC，不能因此假定所有API/采集写入都安全。

最小修复是在写入边界统一UTC，采用持久化后重读的+08测试；不建议本次自动批量重写历史数据，历史日期来源与时区需要另行核实。

## J. 前端用户体验与完整链路

本次真实浏览器使用390×844手机和1440×1000桌面视口，访问副本API。正常首页、搜索、学校选择、卡片带届次进入详情、来源目标、真实登录、补充提交及记录即时刷新可用；超长赛事/学校名称、无届次/无官网夹具未造成横向溢出。这里没有用测试通过替代错误场景结论。

| 步骤 | 复核结果 |
| --- | --- |
| 首页近期赛事 | 正常展示；R05/R06/R07仍影响日期或计数 |
| 搜索/筛选/学校学院 | 正常筛选可用；顶部HomeSearch只提交keyword，丢已选学校，既存P2 |
| 同届次详情 | 卡片带edition_id正确；登录个人截止仍跨届R04 |
| 通知/认定/官方来源 | 类型结构分开；历史通知回退、未核验认定展示见L |
| 登录返回 | 正常内部返回可用；控制字符绕过见R03；注册链接未带next，注册后不能沿原补充链返回 |
| 纠错/补充提交 | 正常待审及即时刷新可用；跨账号失败残留R10 |
| 审核结果 | API和个人记录能返回意见；需补证记录与50条边界阻断管理流程R08/R09 |
| loading/error/empty | 相应组件存在，重复参数进入错误边界；没有声称每种网络延迟都已完整验收 |

**既存P2会话恢复缺口**：[v09-api.ts:90](D:/Python/xuesheng/frontend/src/lib/v09-api.ts:90) 没有请求超时和401会话处理。浏览器使用失效令牌提交后显示“请先登录”，输入保留，但仍渲染已登录表单，没有重新登录链接。手机打开菜单，退出按钮可见数量为0，原因是 [SessionButton.tsx:12](D:/Python/xuesheng/frontend/src/components/v09/SessionButton.tsx:12) 等处 `hidden sm:inline-flex`。这使新提交入口继承了难以恢复的旧登录问题；长时挂起仅根据无超时实现判断，没有做无限等待实验。

截图在 `.codex-qa/independent-audit/shots/`。其中 Next 开发指示器仅为本次本地dev环境，不是新增产品控件。

## K. 性能问题

R12的规模实验结果：

| 赛事/届次数 | 返回卡片 | 实际加载ORM对象 | SQL数 | 本机耗时 |
| --- | --- | --- | --- | --- |
| 200/200 | 1 | 400 | 8 | 0.042秒 |
| 2000/2000 | 1 | 4000 | 29 | 0.300秒 |
| 5000/5000 | 1 | 10000 | 71 | 0.871秒 |

当前主要是无限候选加载加 selectinload 分批，并非每条卡片一次查询的简单N+1。统计接口既有的全量线索、通知聚合也未改善；前端整校目录逐页顺序获取，目录增长会增加请求。未发现本轮有必要为“架构漂亮”引入大改，但应给列表候选规模和首页请求量设可测预算。没有做生产压测，也没有用合成数据数字推断真实容量上限。

## L. 数据可信度问题

补充、候选、正式赛事在新提交入口的写入上仍分离，`verified_pending_import` 没有创建正式赛事；连续重复提交5次产生5条，第6次429。重复提交目前没有幂等保护，但没有把“可能重复”夸大为生产数据损坏。

另确认两项**既存P2**：

1. [competition_repository.py:284](D:/Python/xuesheng/backend/app/repositories/competition_repository.py:284) 的认定查询仅排除demo，没有按认定状态、人工审核或政策核验过滤；[competitions/[id]/page.tsx:198](D:/Python/xuesheng/frontend/src/app/competitions/[id]/page.tsx:198) 将结果放入“以下内容只陈述…收录事实”区域，未依据这些状态加审核提示。副本中 `insufficient_evidence + needs_manual_review=true + policy.is_verified=false` 的记录也公开返回并显示分级。测试夹具标题自带“待核验”文字不等于产品执行了状态隔离。应过滤未核实记录或作为明确独立的待核验线索展示，不能包装成收录事实。
2. [users.py:84](D:/Python/xuesheng/backend/app/api/routes/users.py:84) 的个人资料接口允许普通用户创建 `is_verified=True` 学院，第102行创建专业。真实普通令牌提交后，匿名目录可读该新学院。该路径HEAD已经存在，不能归责于新补充接口，但它不符合“用户提供新学校/专业信息必须审核”的全局边界。应保存个人自由文本或进入候选，不能自动认定为已核实目录。

既存个人中心用任意历史届次通知作当前理由见R04；旧 `/api/home` 在 [home_data_service.py:316](D:/Python/xuesheng/backend/app/services/home_data_service.py:316) 仍用保存状态，未来才开始的赛事进入其open列表。当前公开首页使用新 `/competitions` 接口，不能把旧API差异误报为当前首页必现，列为P3口径债务。

没有发现本次新增AI编造历史或向正式库注入验收假数据；这不代表已联网核实所有既有赛事事实。

## M. 当前改动是否建议批准

**不批准当前48文件版本。** R01单独足以阻止批准；R03、R02、R04及审核入口问题进一步说明，不能依据261项测试通过宣称所有核心和异常链路已闭环。审查只新增本报告后，工作区可见文件数应为49；不要把审查产物算回上一轮的改动数量。

## N. 最小修复清单

批准前优先完成以下有边界的修复，不需要重做数据库或界面：

1. 封闭公开审核队列对用户提交和审核意见的匿名读取（R01），真实令牌覆盖本人、他人、匿名及各审核状态。
2. 规范化并同源校验登录返回URL（R03），隔离跨会话列表状态和旧请求（R10）。
3. 让一次审批统一事务，并用预期状态/版本拒绝并发覆盖（R02/R11）；加入故障与交错执行回归。
4. 统一详情及个人模块的目标届次/学校，独立解析校内开始和截止（R04/R05）；覆盖校内早于官方的阶段。
5. 补齐需更多证据入口和审核分页（R08/R09），用51条真实API/UI边界验证。
6. 修正计数集合、冲突日期、unknown过滤和重复参数（R06/R07/R13/R14），这些均可小范围完成。

R12可按当前规模设上线前性能预算并分步优化；不要求在本次修复中大规模重写查询。既存时区/未核验目录/停用账号等应作为独立明确任务处理，至少在开放真实用户投稿前完成数据边界整改，且不要直接清理或重写生产历史数据。

## O. 批准后进入下一阶段前仍需处理的事项

本次未批准，因此不是放行清单。未来修复后仍应处理：通用补充正式入库的字段预览、事实来源与审计；既存日期时区迁移策略；个人中心与旧首页API统一；过期登录/手机退出；端到端回归纳入可重复执行的正式测试。会议前端和扩大数据采集不是本轮审查补丁的必要内容。

## P. 真实文件路径、行号与覆盖范围

上文每项均链接到当前源码行号；行号基于未修改的审查基线。以下48个文件全部纳入阅读，未发现删除文件。相邻未改动的鉴权、模型、来源仓储、Next本地实现也被读取用于验证调用链，未扩大修改范围。

**后端实现14个**：`backend/app/api/router.py`、`backend/app/api/routes/{admin,competitions,users,supplements}.py`、`backend/app/core/exceptions.py`、`backend/app/repositories/{competition_repository,stats_repository}.py`、`backend/app/schemas/{competition,v1}.py`、`backend/app/services/{competition_service,deadline_resolution_service,edition_status_service,personal_competition_service}.py`。

**测试4个**：`backend/tests/{test_core_user_journey,test_contribution_workflow,test_deadline_resolution_service,test_v1_notifications_product}.py`。

**前端26个**：`frontend/src/app/page.tsx`、`frontend/src/app/competitions/page.tsx`、`frontend/src/app/competitions/[id]/{page,not-found}.tsx`、`frontend/src/app/contribute/page.tsx`、`frontend/src/app/admin/page.tsx`、`frontend/src/app/admin/review/page.tsx`、`frontend/src/app/{error,loading}.tsx`、`frontend/src/app/login/page.tsx`、`frontend/src/app/my-competitions/page.tsx`；`frontend/src/components/{AppShell,CompetitionCard,SchoolSelector,StatusBadge}.tsx`；`frontend/src/components/v09/{CorrectionForm,ContributionHistory,NotificationBell,PersonalContext,PersonalHome,ProfileForm,SessionButton}.tsx`；`frontend/src/lib/{api,types,v09-api,use-session}.ts`。

**文档4个**：`README.md`、`docs/CURRENT_TASK.md`、`docs/CORE_USER_JOURNEY_20260927.md`、`docs/STAGE_DEVELOPMENT_REPORT_20260927.md`。完整逐文件字节哈希在 `.codex-qa/independent-audit/before.json`，可对照是否被本轮改写。

## Q. 实际运行的检查与测试命令

以下均已实际执行；PowerShell中含 `if ($LASTEXITCODE -ne 0)` 的检查链会在失败时停止后续命令。没有执行正式迁移、导入、抓取、Git提交或推送。

```powershell
# 仓库范围、历史与格式检查，工作目录 D:\Python\xuesheng
git status --short
git diff --stat
git log -3 --oneline
git diff --name-only -z
git ls-files --others --exclude-standard -z
git -c core.safecrlf=false diff --numstat
git -c core.safecrlf=false diff --numstat --ignore-all-space
git -c core.safecrlf=false diff --check
backend\venv\Scripts\python.exe .codex-qa/independent-audit/snapshot.py before

# backend 工作目录；沿用正式测试隔离
.\venv\Scripts\python.exe -m pytest -q -o addopts=''

# frontend 工作目录
npm run lint
npm run typecheck
npm run build

# 根目录：临时独立诊断，不属于正式测试代码
backend\venv\Scripts\python.exe .codex-qa/audit-security/probe_security.py
backend\venv\Scripts\python.exe .codex-qa/audit-edition/probe.py
node .codex-qa/audit-frontend/frontend-state-repro.cjs
backend\venv\Scripts\python.exe .codex-qa/independent-audit/performance.py
backend\venv\Scripts\python.exe .codex-qa/independent-audit/setup_browser.py
node .codex-qa/independent-audit/browser.mjs
backend\venv\Scripts\python.exe .codex-qa/independent-audit/seed_queue.py
node .codex-qa/independent-audit/admin-browser.mjs
backend\venv\Scripts\python.exe .codex-qa/independent-audit/snapshot.py after
```

浏览器服务实际命令为 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8018` 和 `npm run dev -- --hostname 127.0.0.1 --port 3018`。进程环境显式设置 `ENVIRONMENT=test`、`DATABASE_URL=sqlite:///D:/Python/xuesheng/.codex-qa/independent-audit/browser-v2.sqlite`，前端API为8018，CORS仅本地3018。没有修改.env；测试后停止这两个服务并重新正常build。

## R. 测试结果及证据限制

| 项目 | 结果 |
| --- | --- |
| 全量后端 | 261 passed，18.92秒 |
| lint | 通过，0警告 |
| typecheck | 通过 |
| 正常配置build | 通过，检查开始与恢复阶段均通过 |
| 补丁空白检查 | 通过 |
| 安全内存探针 | 退出0；确认泄露、部分提交、+08偏移、交错覆盖，同时确认403/归属/URL校验 |
| 日期内存探针 | 退出0；确认R05/R06/R07/R13及既存时区/个人模块差异 |
| 前端脚本探针 | 退出0；初步观察后由真实浏览器复核重定向、重复参数、跨账号残留 |
| 浏览器 | 12项主链观察、3项后台/手机观察完成；含正常及有缺陷结果，不称15项全部通过 |
| 性能 | 3个独立内存规模；不是生产压测 |

新浏览器夹具第一次因缺 `observed_at` 必填字段失败，事务回滚；只修正本轮临时夹具后用新的 `browser-v2.sqlite` 副本完成验证，没有改模型放宽约束。临时诊断中的合成学院、政策和审核意见都明确为审查数据，不应当作正式事实。

证据：`.codex-qa/audit-security/observations.txt`、`.codex-qa/audit-edition/probe-results.jsonl`、`.codex-qa/independent-audit/{browser-results,admin-browser-results,performance,before,after}.json` 和 `shots/`。浏览器会话文件含本地临时凭据，仅保存在忽略目录，不应加入Git或对外分享。

## S. 生产数据库是否发生变化

**没有变化。** 开始及结束对正式 `data/v02.sqlite` 文件计算SHA256，均为：

`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`

正式测试沿用 `conftest.py` 的 test环境、内存engine、sqlite连接防护及可恢复 dependency override。本次诊断只连接内存库或独立副本；复制正式库和计算哈希只是文件读取，没有通过测试建立正式数据库连接。没有绕过隔离保护，没有清理任何历史生产污染记录。

原48个审查对象逐文件哈希保持一致，未因发现问题自动修复业务代码。临时服务器已停止，Next生成类型已恢复，未新增依赖、迁移或部署变更。审查结论与修复建议仅记录在本报告。
