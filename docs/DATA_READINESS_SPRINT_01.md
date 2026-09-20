# DATA_READINESS_SPRINT_01

日期：2026-09-14（Asia/Shanghai）

本轮是首页正式开发前的数据收尾，不是 Recognition Batch 02，也没有重跑历史 discovery 批次。统计基准为 2026-09-14 的生产 SQLite 数据；导入前备份为 `data/backups/backup-20260914-120323.sqlite`。结构化导入报告与就绪审计分别位于 `data/reports/data_readiness_sprint_01_import.json`、`data/reports/data_readiness_sprint_01_audit.json`。

# 1. Current Recognition Coverage

当前高校数：**7 所**。

当前 Recognition 数：**223 条**，来自 **7 份**当前有效、已核验的高校文件或明确认定证据。相较 Recognition Batch 01 的 111 条 / 3 校，净增 **112 条 / 4 校**。其中本轮 4 份新证据导入 111 条；上一轮 unresolved 中的“红旅大赛”在独立赛事身份确认后补入 1 条当前 Recognition。

| 高校 | 地区/类型 | Current Recognition | 当前证据文件 |
|---|---|---:|---:|
| 武汉体育学院 | 湖北，体育类 | 97 | 1 |
| 东南大学 | 江苏，985/211 | 60 | 1 |
| 西南交通大学 | 四川，211，交通特色 | 49 | 1 |
| 西南财经大学 | 四川，211，财经类 | 10 | 1 |
| 武汉大学 | 湖北，985/211 | 5 | 1 |
| 华中农业大学 | 湖北，211，农业类 | 1 | 1 |
| 西北工业大学 | 陕西，985/211，航空航天特色 | 1 | 1 |

本轮新增当前证据：

- 西南交通大学《2027 年推荐免试研究生 A 类学科竞赛目录》：49 条；官方公告和 PDF 均已留存并校验 hash。
- 东南大学 2025 竞赛认定名录：官方 2026 通知明确本年度申报继续采用，导入 60 条；XLS 已留存并校验 hash。
- 华中农业大学 2026 “111”赛事目录公告：附件仍受验证码阻断，只导入公告正文明确点名的“中国国际大学生创新大赛”1 条，不推断其余 112 项和级别。
- 西北工业大学 2026 “科云杯”通知：正文明确该赛事为学校认定 A1 类，只导入这一条明确陈述，不把普通校内选拔行为本身当作认定。

门槛判定：**PARTIAL BUT SHIPPABLE**。未达到 10 校理想 READY 目标，但已达到约定的 7 校可上线下限，覆盖 4 省、3 所 985、6 所 211，以及综合、财经、交通、农业、航空航天、体育等学校类型；不再为追数字无限扩校。

# 2. Historical Recognition

Historical Recognition：**38 条，覆盖 4 所高校、4 份历史文件**。

| 高校 | Historical Recognition |
|---|---:|
| 北京交通大学 | 10 |
| 西南交通大学 | 10 |
| 华南师范大学 | 9 |
| 南京航空航天大学 | 9 |

相较上一轮 33 条净增 5 条，来自 5 个经独立证据确认后新建的 canonical competition；这些 Recognition 仍保持 `expired`，没有因赛事身份被确认而改写成当前有效。现有政策 API 可用 `recognition_status=recognized|expired|uncertain` 区分三种状态；新增首页聚合只读取已核验且 `is_current=true` 的 `recognized` 记录，历史目录不会混入首页当前认可区。

# 3. Recognition unresolved

上一轮指定的 6 条 unresolved 已全部逐条处理：**MATCHED 1、UNMATCHED 后独立确认并新建 5、AMBIGUOUS 0、剩余 0**。

| 原始名称 | 结论 | canonical 处理 |
|---|---|---|
| 全国大学生红色旅游创意策划大赛（简称“红旅大赛”） | UNMATCHED → 独立赛事已确认 | 新建“全国大学生红色旅游创意策划大赛” |
| “中航工业杯”国际无人飞行器创新大奖赛 | UNMATCHED → 独立赛事已确认 | 新建；高校来源只记 `school_confirmed`，不冒充 S/A 级主办方证据 |
| ACM国际大学生程序设计竞赛 | MATCHED | 绑定既有 ACM-ICPC canonical 与 alias |
| 全国“电脑鼠走迷宫”竞赛 | UNMATCHED → 独立赛事已确认 | 新建；与其他机器人/电子赛事不模糊合并 |
| 东芝杯·中国师范大学师范专业理科大学生教学技能创新实践大赛 | UNMATCHED → 独立赛事已确认 | 新建并保留历史名称 alias |
| 全国大学生交通运输科技大赛 | UNMATCHED → 独立赛事已确认 | 新建；没有误并入“北京市大学生交通科技大赛” |

5 个新主体均有独立身份来源；没有为了清零 unresolved 强制模糊匹配。赛事总数由 145 增至 150，归一化重复主体仍为 0。

上一轮 3 个 `completed_with_gaps` 的处置：

- 华中农业大学：**部分解决**。官方 HTML 已提供一条可独立核验的当前认定，因此安全导入 1 条；完整附件仍受验证码阻断，剩余目录不入库。
- 中国地质大学（武汉）：**仍未解决**。官方目录公告存在，但附件验证仍触发安全机制；没有绕过验证码，也没有用搜索摘要替代正文。
- 北京科技大学：**仍未解决**。公开入口可访问，但仍未找到可核验的当前校级完整目录；学院材料没有泛化为校级 Recognition。

这些 gap 不再构成首页阻塞任务。

# 4. Deadline Coverage

截至审计时，未来真实可行动 deadline 共 **21 条**，全部带来源 URL 和已核验状态：

- 报名：**20 条**。
- 提交：**1 条**。
- 校内/院内：**14 条**。
- 全国/官方：**7 条**。
- 正在报名：**15 条**，涉及 11 个赛事、14 个可信来源 URL。
- 全部未来 deadline：20 个去重可信来源 URL；最新核验时间 `2026-09-13T14:12:54Z`。

全国/官方节点只有在该届存在 S/A 级已核验来源时才进入首页；高校和学院节点始终保留 `university` / `college` scope、学校/学院名称和校内通知 URL，不会提升为全国 deadline。既有质量审计中的 `campus_later_than_national` 保持 **0**。

本轮同时修复“中国国际大学生创新大赛”2024、2025 历史届次误复制 2026 官方报名截止的问题，历史届次错误值归零，旧值保留在 FactRevision。全量测试还暴露出一个测试清理 helper 会把 2026 截止恢复到同赛事所有年份；已改为只恢复实际修改的 `edition_id`，修复后全量测试不再污染生产数据。

# 5. Actionable Future Deadlines

| 时间窗口 | 可行动节点 |
|---|---:|
| 未来 30 天 | 18 |
| 未来 60 天 | 21 |
| 未来 90 天 | 21 |

“即将截止”的 READY 门槛为 20 条未来已核验报名/提交节点，当前为 21；“正在报名”的 READY 门槛为 10 条 `current_status=registration_open` 且截止仍在未来的节点，当前为 15。赛事开始、结束日期不计入这两个数字，历史日期和典型月份也不会被推算成当前 deadline。

# 6. Recent Updates

可生成：**是**。

真实更新数量：**近 30 天 48 条**，来自 **26 个**去重可信来源 URL；最新一条可展示更新发生于 `2026-09-05T14:47:43Z`。首页稳定取得最近 10 条，不需要新增冗余事件表。

来源：复用 `competition_fact_revisions`。查询规则为：

- 仅接受 `verified_official`、`authority_confirmed`、`school_confirmed`。
- 只允许赛事状态、届次名称、报名/提交截止、比赛日期、官方链接、主办方、参赛/提交要求等用户可理解的事实字段。
- `new_value` 必须非空且与 `old_value` 不同。
- 按 `competition + edition + field` 去重，只保留最新修订。
- 不使用每天自动变化的 `updated_at` 伪造“今天更新”；清空错误值的修订也不进入展示流。

API 项目包含 `update_type`、`entity_type`、`entity_id`、`changed_fields`、赛事/届次、旧值、新值、来源和 `occurred_at`。首版只展示已存在的真实事实变化，不人为补造 NEW/VERIFIED 事件。

# 7. Conference Readiness

会议基础浏览状态：**READY**。本轮只审计，没有扩建会议爬虫。

| 指标 | 数量 |
|---|---:|
| Conference Series | 206 |
| 有官网 Series | 205 |
| Conference Edition | 132 |
| 未来已核验会议 | 38 |
| 首页未来会议可信 URL | 38 |
| 有 CFP URL 的 Edition | 3 |
| Edition 级 submission deadline（全库） | 2 |
| Opportunity deadline（全库） | 4 |
| 未来 submission deadline | 1 |
| 未来 30 / 60 / 90 天截稿 | 1 / 1 / 1 |
| CCF 分类 Series | 36 |

因此首页可以展示“近期学术会议”，不能把会议举办日期冒充投稿截止，也不应在首页主区宣称已有成熟的“会议即将截稿”能力。复杂截稿子模块仍为 PARTIAL，但不阻塞会议基础模块和首页开发。

# 8. Homepage Section Readiness

| 首页模块 | 状态 | 数据量 | 高校覆盖 | 可信来源数 | 最新数据时间 |
|---|---|---:|---:|---:|---|
| 高校认可竞赛 | PARTIAL BUT SHIPPABLE | 223 | 7 校 | 7 份当前证据 | 2026-09-01 |
| 正在报名 | READY | 15（11 个赛事） | 不适用 | 14 URL | 2026-09-13T14:12:54Z |
| 即将截止 | READY | 21 | 14 条校/院节点 | 20 URL | 2026-09-13T14:12:54Z |
| 最近更新 | READY | 48 | 不适用 | 26 URL | 2026-09-05T14:47:43Z |
| 学术会议 | READY（基础浏览） | 38 场未来会议 | 不适用 | 38 URL | 2026-09-06T11:42:55Z |

状态完全由 `HomeDataService` 的固定门槛和真实查询计算。首页开发条件为：高校认可可上线、正在报名 READY、即将截止 READY、最近更新 READY、会议至少 PARTIAL；当前全部满足。

# 9. Home API

新增 `GET /api/home`，复用现有模型、来源和事实修订，不建立重复业务表。响应顶层包含：

- `decision`、`frontend_ready`、`blockers`、`as_of`。
- `current_recognitions`：只取当前、已核验政策证据。
- `open_registrations`：只取仍开放且有未来截止的报名节点。
- `upcoming_deadlines`：分 official / university / college 和 registration / submission。
- `recent_updates`：从真实 FactRevision 派生。
- `conferences`：只取未来、已核验且有官网/证据链接的会议。

每块都有 `status`、`shippable`、`record_count`、`verified_count`、`threshold`、`reason`、`last_updated_at` 和模块指标；默认最多返回 10 条列表项，但 readiness 统计使用全量查询。无数据时返回空 `items=[]` 和 PARTIAL/BLOCKED 元数据，不返回 Mock。

# 10. 数据质量

数据库核心变化：

| 指标 | 修改前 | 修改后 | 净变化 |
|---|---:|---:|---:|
| Competition | 145 | 150 | +5 |
| CompetitionSource | 431 | 547 | +116 |
| PolicyDocument | 7 | 11 | +4 |
| PolicyAttachment | 7 | 9 | +2 |
| Recognition | 144 | 261 | +117 |
| Current Recognition | 111 | 223 | +112 |
| Historical Recognition | 33 | 38 | +5 |
| SchoolCompetition | 227 | 330 | +103 |

原有赛事质量审计：**11 PASS、2 WARN、0 FAIL**。两项既有 WARN 是双轨 track 模型仍并存，以及 1 条全库官方 deadline 缺少届次 S/A 证据；后者被 `/api/home` 严格过滤，不进入首页。

本轮 Data Readiness 审计：**18 PASS、2 WARN、0 FAIL**。两项 WARN 是 Current Recognition 只有 7 校、未来会议投稿 deadline 只有 1 条，均已通过产品边界降级而不阻塞首版。

硬质量检查全部通过：孤儿关系 0、重复赛事实体 0、重复 Recognition 证据键 0、Recognition/文件高校错配 0、核心来源 URL 缺失 0、普通通知/参赛新闻误升 Recognition 0、校内截止晚于全国截止 0、历史届次复制 2026 deadline 0。

# 11. 测试

- Backend 全量：**172 passed**。
- 新增 Home 聚合测试 5 项，覆盖五模块响应、空态、Current/History 过滤、deadline 层级和 S/A 证据约束、Recent Update 去重与 JSON null 排除。
- Recognition 专项、deadline 回归与 Home 测试联合：15 项通过。
- TypeScript：`tsc --noEmit` 通过。
- 原有数据质量审计：11 PASS / 2 WARN / 0 FAIL。
- Data Readiness 审计：18 PASS / 2 WARN / 0 FAIL。
- 幂等：最终复跑 Competition、Source、PolicyDocument、PolicyAttachment、Recognition、Current、Historical、Candidate、SchoolCompetition、FactRevision 全部 `delta=0`。
- 原始文件：西南交通大学 PDF 为 3 页，SHA-256 `ea74c97799cc6c69f185324d4971ce3c904c86e5fb7acd8a9394d8ae96bf8df0`；东南大学 XLS SHA-256 `c65e848be6ee121cabc45931d7a2f589e855f62abb6f1f4c04847e9a13b07019`。

# 12. FRONTEND_READY

**YES**。

原因：高校认可已达到 7 校的高质量可上线下限；开放报名 15 条达到 READY；未来可行动 deadline 21 条达到 READY；最近真实更新 48 条达到 READY；未来已核验会议 38 场达到基础浏览 READY。所有模块都有严格来源边界、空态和 readiness metadata，核心审计无 FAIL。

这不表示数据库已经完美：Recognition 尚未达到 10 校理想覆盖，会议投稿 deadline 也不足以做复杂截稿区。但两者都已有明确的产品降级路径，继续扩数据的边际收益低于进入真实首页开发。

数据基础设施现在冻结为首页第一版基线。当前项目完成度估计为 **86%**：数据与后端聚合已达到首版门槛，剩余主工作是把现有前端首页重构为 BaoyanNews 式“发现机会—判断时效—查看证据—采取行动”的信息路径。

下一步唯一 P0：**开始 BaoyanNews 信息逻辑驱动的首页重构**。
