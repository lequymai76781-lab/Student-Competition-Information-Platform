# 学生竞赛平台 · 底层数据架构审计报告

审计日期：2026-09-04（基于 `data/v02.sqlite`，Alembic head `202609020012`，即 V0.10.1）

审计原则：只读检查，未删除、未覆盖任何现有数据；结论均附代码路径或数据库取证。

---

## 1. 审计方法

审计由三部分交叉完成：

1. **模型与迁移静态检查**：`backend/app/models/*.py` 与 `backend/alembic/versions/*.py` 全量比对，确认模型与线上库无字段漂移（模型与 live schema 差异为空）。
2. **真实数据库取证**：`backend/scripts/audit_architecture_snapshot.py`（本仓库新增的只读审计脚本）对 38 张业务表做行数、字段归属、来源分布、截止时间语义、重复与错误归属取证。
3. **写路径与前端依赖追踪**：定位“高校通知/目录 → 建赛事/建届次/写时间/标核验”的代码路径，以及 API 与前端组件消费的字段。

## 2. 现状快照

### 2.1 数据表与行数（业务表 38 张，去 alembic_version）

| 层 | 表 | 行数 | 说明 |
|---|---|---:|---|
| 赛事主体 | competitions | 143 | 118 普通竞赛 + 21 track + 4 series；`is_competition=True` 136 行 |
| | competition_aliases | 143 | 别名表，规范化字段齐全 |
| | competition_tracks | 1 | 轨道表（仅产业命题赛道 1 行） |
| | tags / competition_tags | 24 / 370 | 标签分类 |
| 届次 | competition_editions | 53 | 2026 年 51 行、2025 年 2 行 |
| 高校关系 | university_competition_edition_relations | 75 | 高校×届次通知关系 |
| | competition_policy_recognitions | 102 | 高校政策文档级“收录/认可”事实 |
| | university_competition_policies | 0 | **遗留空表**（V0.1 学校目录表，已弃用） |
| | university_policies | 0 | 政策文档主表空（真实文档在 policy_documents） |
| | policy_documents / policy_attachments | 2 / 2 | 政策原文 |
| 来源证据 | competition_sources | 236 | 来源主表 |
| | competition_fact_sources | 591 | 字段级来源证据 |
| | competition_fact_revisions | 6 | 字段变更留痕 |
| | competition_update_events | 1 | 用户可见变更事件 |
| 发现池 | competition_leads | 491 | 网页/微信/第三方线索；已匹配 155，未匹配 336 |
| | candidate_competitions | 102 | 政策目录逐行候选 |
| | candidate_facts | 593 | 线索级候选事实 |
| | policy_raw_items | 97 | 政策文档原始行 |
| | university_competition_discovery_reports | 167 | 高校雷达批次报告 |
| 其他 | universities / colleges / majors | 113 / 34 / 10 | 机构基础表 |
| | review_queue | 28 | 人工复核队列 |
| | users / user_profiles 等 | 少量 | 用户功能表 |

### 2.2 数据覆盖（关键缺口）

| 指标 | 数值 |
|---|---:|
| 赛事有 organizer | 49 / 143 |
| 赛事有 official_website | 19 / 143 |
| 赛事有 founded_year | 5 / 143 |
| 赛事有 first_held_year | 4 / 143 |
| 赛事有 history_timeline | 5 / 143 |
| 赛事有 development_history | 0 / 143 |
| 赛事有届次 | 53 个赛事有且仅有 1 届（2025/2026） |
| 只有高校政策目录来源的赛事 | 63 |
| 高校政策“认可”关系 | 102（武汉大学 5、武汉体育学院 97） |
| 高校×届次通知关系 | 75（覆盖约 25 所高校） |
| 线索已匹配正式赛事 | 155 / 491 |
| 线索未匹配 | 336 / 491 |

---

## 3. 当前系统已经具备的四层骨架

用户建议的“赛事/届次/高校关系/来源证据”四层结构，在现有系统中已经**部分存在且命名基本对应**，这是最重要的审计前提。不是从零重建，而是补洞与纠偏：

| 建议层 | 现有物理表 | 差异 |
|---|---|---|
| competitions | `competitions` + `competition_aliases` + `competition_tracks`（部分轨道仍以 competition 行建模） | 主体已存在；需要清理混入的 award/festival/exhibition 实体与文本历史字段 |
| competition_editions | `competition_editions` | 已存在，且已区分 official/university/college 截止字段；但语义执行不一致（见 P5/P6） |
| school_competitions | 拆散在 `competition_policy_recognitions`（政策认可）、`university_competition_edition_relations`（通知/截止）、遗留空表 `university_competition_policies` | **没有统一的“高校×竞赛/某届”目录实体**；学校页面读取的是空表，真实认可与通知没有聚合到学校维度 |
| sources | `competition_sources` + `competition_fact_sources` + `policy_documents` | 存在两级来源表，但权威等级规则执行不一致（见 P7） |
| 发现池 | `competition_leads` + `candidate_competitions` + `candidate_facts` + `review_queue` | 发现池存在；缺少显式 `review_status` 状态机（rejected/duplicate） |
| 组织 | 只有 `universities`/`colleges`；主办方等仍是 competitions 上的**字符串** | 缺失统一组织实体（见 P11） |
| 学科 | `tags`（含 category）、`majors`（discipline_category） | 有雏形，但竞赛的 category 是自由字符串，未与学科体系打通 |
| 会议 | 无 | 完全没有 conference 结构 |

---

## 4. 主要问题清单

### P1. “高校通知被当作官方核验”的晋升路径过宽（最高优先级）

写路径取证：

- `competition_discovery_import_service._upsert_relation`：当高校通知里出现一个“尚不存在届次”时，会**直接创建 `CompetitionEdition`**，并固定写入：
  - `is_verified=True`
  - `verification_status="verified_official"`
- 同一方法随后创建 `UniversityCompetitionEditionRelation`，其模型默认 `verification_status="verified_official"`、`is_verified=True`；
- `_upsert_relation_source` 把高校通知写成 `CompetitionSource(is_official=True, is_verified=True, reliability_tier=2, verification_status="verified_official")`；
- `_link_lead_by_url` 把同 URL 的 lead 也置为 `verified_official`、`needs_review=False`。

真实数据取证：75 条高校关系 **全部** `verification_status='verified_official'`、`is_verified=1`；53 个届次中 **32 个** `verified_official`，且大量届次是从“registration_notice / internal_selection”高校通知创建的。

这与 README 宣称的“只有赛事官网、主办方通知或高校官方通知才能晋升为竞赛事实”部分冲突：高校官方通知作为 B 级来源可以证明“该校正组织参赛 + 校内时间”，但**不能单独证明全国赛事的官方时间、官方报名入口、赛事等级**。系统没有区分“页面本身官方”与“事实由国家级权威来源确认”。

影响：`competition.is_official_verified=True` 的判断（`competition_intelligence_service.refresh_all` 把 `university_official_notice`/`college_official_notice` 列入 official_sources），会让只有高校通知支撑的赛事在列表与详情页显示为“官方已核实”。

### P2. 学校目录发现即建正式赛事，污染主体库

取证：63 个赛事**唯一来源是 `university_policy`（学校目录）**；其中包含：

- “市级新闻奖”“省级新闻奖”“中国新闻奖”（奖项而非可报名的赛事）；
- “全国大学生艺术节”（festival）、中国舞蹈荷花奖（award）、全国大学生创新创业训练计划年会展示（exhibition）等，`entity_type` 已标为 award/festival/exhibition；
- “AIGC应用大赛”等疑似校内/院级活动（`entity_type='unknown'`）。

这些行以 `competition_type='competition'`、`is_competition=True` 进入正式赛事列表/搜索，虽然描述诚实标注“由已验证高校政策首次发现”，但按用户要求，它们应进入发现池（待核验/待分类），确认国家级/行业权威来源后再进入正式库，而不是直接成为正式赛事。

### P3. “赛事历史”仍是文本/JSON，而非结构化届次

- `competition_editions` 只有 53 行且年份只有 2025/2026；
- `founded_year` 5 行、`first_held_year` 4 行、`history_timeline` 5 行、`development_history` 0 行；
- 详情页的“赛事历史”区块实际渲染 `founded_year/first_held_year/frequency/history_timeline/development_history` 这些主体表文本字段；
- 前端已实现“查看其他届次”的能力（按 `editions` 渲染），但数据没有历史届次可展示。

结论：结构层已为届次化做好准备，缺的是**历史届次的数据迁移与持续建设**，以及 `edition_count`、`history_timeline` 等主体字段与届次表的一致性约束（当前 `edition_count` 是人工可写字段，可能与真实届次行数不一致）。

### P4. “高校×赛事目录”实体断链：学校页面读的是空表

取证：

- `university_competition_policies` 0 行，且全仓没有任何 `UniversityCompetitionPolicy(...)` 写入代码；
- `/api/universities/{id}/competition-policies`（`university_repository.list_competition_policies`）只查这张空表；
- 前端 [universities/[id]/page.tsx](D:/Python/xuesheng/frontend/src/app/universities/[id]/page.tsx) 展示“竞赛认可”，对所有学校都会显示“暂无竞赛认可记录”；
- 真实的 102 条认可记录在 `competition_policy_recognitions`（绑定 policy_document），75 条通知关系在 `university_competition_edition_relations`，两者**都没有被学校页面消费**，也没有按“学校×赛事×年度”聚合成目录。

结论：用户要求的 `school_competitions` 层是真实缺口，不是重复建设。

### P5. 高校关系表的语义字段缺失

`UniversityCompetitionEditionRelation` 有内部截止、负责单位等字段，但缺少：

- `recognition_status / school_level / school_category`（该赛事在本校目录中的 A/B/Ⅰ/Ⅱ 类）；
- `credit_policy / award_policy / participation_status`；
- 统一的“主办学院/负责部门”之外，无 `verified_at` 与证据关系的外键；
- notice_type 混入非行动类型：75 条关系里存在 `other`（2）、`training_notice`（1）等不应进入学校截止解析或展示为“报名通知”的记录。

另外，这些关系行的默认核验状态即 `verified_official`（P1），会进一步放大错误归属。

### P6. 截止时间的“校内/全国”语义在旧通用字段上仍可能混写

代码与数据取证：

- `competition_editions` 同时存在 `registration_deadline`（旧通用字段）、`official_registration_deadline`、`university_registration_deadline`；
- `competition_discovery_import_service._apply_relation_deadlines` 在“没有官方时间”时会把校内截止写进旧通用字段 `registration_deadline`（只在 edition.registration_deadline is None 时）；实测 3 条届次的 `registration_deadline` 与 `university_registration_deadline` 完全相等且无官方时间（e13、e24、e29）；
- 实测 1 条届次（e22“中国首届新域新质”创新大赛）的 `university_registration_deadline`（2026-09-30）**晚于** `official_registration_deadline`（2026-09-15），违反“校内截止应早于全国截止”的常识，疑为把全国时间误当成校内时间写入；
- 列表/日历等查询（`competition_repository`）的 availability/deadline 过滤大量基于 `registration_deadline` 与 `current_status`，旧字段一旦混入校内时间，会把“校内截止”展示成“全国报名截止”。

### P7. 来源权威等级规则执行不一致

- `competition_discovery_import_service` 写入来源 `reliability_tier=2`、`is_official=True`；
- `competition_detail_enrichment_service._source_rank` 却把同一类高校来源排在 rank 3（低于官方 1/2）；
- `CompetitionFactSource.source_level` 是后补的 `LEVEL_1..LEVEL_3`，但 `CompetitionSource` 没有该字段，无法在来源主表上直接筛权威等级；
- 来源表没有 `authority_level`（S/A/B/C）字段、没有组织外键，source_type 是字符串枚举，缺少受控词表；
- `competition_intelligence_service.refresh_all` 把高校来源计入 `official_sources`，进一步放大 P1。

### P8. 同一实体存在“两套赛道建模”

- `competitions` 表内以 `competition_type='track'` + `parent_competition_id` 存 21 个“子赛道/子赛项”（如外研社各赛项、中国高校计算机大赛各子赛）；
- 另建了 `competition_tracks` 表（仅 1 行产业命题赛道）；
- `_repair_hierarchy` 只针对“中国国际大学生创新大赛产业命题赛道”这一个 case 写死修复，其他系列/轨道靠 `SERIES_DEFINITIONS` 自动生成。

两套轨道概念并存会造成未来歧义：页面上的“子赛道”进入搜索结果，而 `competition_tracks` 只作为详情页“赛道设置”展示。需要明确“系列→赛项（competition 行）”与“单届赛事内部赛道（track 行）”的边界，并将轨道正式化为一层独立关系。

### P9. 发现池缺少显式状态机与“学校来源”归属

`competition_leads` 已有 `verification_status`、`needs_review`、`matched_competition_id/edition`，但没有：

- 用户建议的 `review_status`（pending/matched/verified/rejected/duplicate）；
- 统一的 `possible_competition_id` 与 `confidence` 分离（现在 matched id 即“已确认”，无“疑似”态）；
- 学校归属字段（目前散落在 `metadata_json.university` 中，无法按学校可靠聚合）；
- 336 条未匹配线索没有“拒绝/重复/待人工”分类，长期淤积在队列里。

### P10. 组织与学科体系缺失（机构字符串重复）

- `competitions.organizer` 有 94 行为空；非空值全是自由字符串，同一机构写法不一（如“教育部”多次出现、全称/简称混用）；
- co_organizers/guiding_organizations/undertakers 是 JSON 字符串数组，未来与会议共享时需要按 organization 归一；
- `tags`（category 字段）、`majors.discipline_category` 已有雏形，但没有统一的 disciplines 受控表；竞赛 category 当前是自由字符串（已出现“学科竞赛”84 行这种非学科标签占位）。

### P11. 没有任何会议结构、没有“会议/竞赛”共享的组织与学科底座

数据库与后端模型中不存在 conference_series/conference_editions/school_conferences，也没有 `organizations` 统一机构表。若现在直接做会议 UI，将无从复用竞赛的来源、发现与组织逻辑。

### P12. 前端受影响面（按页面粒度）

前端当前依赖的响应结构与现有表一致，任何“改表不改 API 响应”的重构都不会破坏前端。前端真正受影响的是**数据口径**而非字段名：

| 页面/组件 | 消费的字段 | 受架构影响点 |
|---|---|---|
| 首页 [page.tsx](D:/Python/xuesheng/frontend/src/app/page.tsx) | 列表截止时间、freshness、edition_status | P6 口径：校内/全国截止是否混用会改变“正在报名/即将截止”展示 |
| 赛事列表 [competitions/page.tsx](D:/Python/xuesheng/frontend/src/app/competitions/page.tsx) | category/tag/competition_type 过滤 | P2：学校目录发现即建库的赛事（奖项/活动）会污染搜索结果 |
| 赛事详情 [competitions/[id]/page.tsx](D:/Python/xuesheng/frontend/src/app/competitions/[id]/page.tsx) | editions、university_notices、sources、fact_sources、recognitions、history_timeline 等 | P3 历史文本 vs 届次；P7 来源等级显示“官方”语义不准确 |
| 高校详情 [universities/[id]/page.tsx](D:/Python/xuesheng/frontend/src/app/universities/[id]/page.tsx) | `/competition-policies`（空表） | P4：学校赛事目录展示断链 |
| 日历 [calendar/page.tsx](D:/Python/xuesheng/frontend/src/app/calendar/page.tsx) | 列表截止时间 | P6 |
| 数据总览 [data/page.tsx](D:/Python/xuesheng/frontend/src/app/data/page.tsx) | stats + discovery coverage | 发现池状态化后需要补充 rejected/duplicate 统计 |
| 管理页 [admin/page.tsx](D:/Python/xuesheng/frontend/src/app/admin/page.tsx) | 列表、统计 | 新增组织/学校目录实体后需要维护界面（不在本轮） |
| 个人中心 v09 组件 | my-competitions、通知 | 依赖列表/详情 API，不受字段级改动影响 |

---

## 5. 字段归属矩阵（旧字段 → 四层目标）

按用户问题 B，当前字段未来应归属到哪一层：

| 字段 | 现状 | 目标归属 | 迁移动作 |
|---|---|---|---|
| name/short_name/english_name/former_names/aliases | competitions | 赛事永久层 | 保留（former_names 建议由 aliases 承载） |
| category/discipline/description/competition_scope/country_or_region/target_participants/competition_format | competitions | 赛事永久层 | 保留并受控化 category |
| organizer/co_organizers/guiding_organizations/undertakers/official_website/official_account | competitions（字符串/JSON） | 赛事永久层 + organizations 组织层 | 新增 organizations 注册表与关系表；字符串保留做 API 兼容 |
| founded_year/first_held_year/frequency | competitions | 赛事永久层 | 保留，历史细节迁往届次 |
| history_timeline/development_history | competitions（JSON/Text） | 赛事永久层文本摘要 + **competition_editions 结构化历史** | 有据可查的年份/届次迁移到 editions；文本仅作摘要保留 |
| edition_count | competitions | 只读派生（COUNT editions） | 迁移脚本改为统计值并加校验；API 保留字段 |
| registration_deadline | competition_editions | 弃用/仅兼容展示字段；不再接受写入 | 新写入只允许 official/university/college 三个语义字段；旧数据清理 |
| official_registration_deadline/官方报名URL/官方通知URL | competition_editions | 届次层（S/A 级来源写入） | 保留；增加“无官方来源不得标 verified_official”约束 |
| university_registration_deadline/college_registration_deadline | competition_editions | 届次层缓存 + 关系层为准 | 继续由 enrichment 从关系层聚合 |
| internal_registration_deadline 等校内字段 | university_competition_edition_relations | 高校关系层 | 保留（正确的层） |
| recognized_level/school A/B/I/II、score、usage_type | competition_policy_recognitions（政策文档级） | 高校关系层（school_competitions 目录实体） | 聚合进新的学校目录实体；不在 competitions 层出现（当前基本没泄漏） |
| is_verified/verification_status/verified_official | competitions/editions/relations/sources | 来源证据层决定，只允许权威来源确认 | 修正晋升规则（P1） |
| reliability_tier/credibility_score/is_official | competition_sources | 来源证据层 | 增加 authority_level S/A/B/C 与组织外键 |
| source_url/raw_title/raw_content | competition_sources/leads | 来源证据层/发现池 | 保留 |
| matched_competition_id/needs_review | competition_leads | 发现池 | 增加 review_status 状态机 |
| entity_type=award/festival/exhibition 的行 | competitions | 发现池/分类实体 | 标记为非可报名实体，从正式赛事查询隔离 |

---

## 6. 211 数据评估（问题 C、D）

### C. 现有 211 数据能保留多少？

几乎全部可保留，按角色重新挂靠：

- 39 所 985（全部入库）+ 73 所非 985 211（全部入库）本身是 **universities** 基础数据，无争议，100% 保留；
- 491 条 lead（约 336 条未匹配）：是**发现层证据**，100% 保留并进入 pending/review 队列，不删除；
- 75 条高校×届次关系：是**高校关系层证据**，100% 保留（修正 notice_type 与核验状态标记即可，如 training_notice/other 应降级展示）；
- 63 个“仅高校目录来源”的赛事行：主体名称与别名大概率真实，但当前把它们当“正式赛事”展示是错误归属。建议迁移到发现池/待核验态（保留 id 与证据，避免删除）；其中约 102 条武汉体育学院目录行对应的 recognition 关系全部保留在政策层；
- 已被官方来源支持的 24 个 github_seed 赛事行（如大创、挑战杯等）保留为正式赛事，同时保留 C 级来源标记。

估算：约 63 个“目录发现型”实体需要从正式库降级/标记为未确认（不是删除），211 高校相关的发现、通知、认可证据数据预计可保留 95% 以上；少量 noise（获奖新闻、活动新闻、讲座、团队招募）应从“可报名赛事/关系”口径中剔除，但仍作为发现证据保留。

### D. 可能存在重复或错误归属的数据

1. **同一通知多 URL**：实测中国矿业大学同一“全国大学生英语竞赛报名通知”存 3 条 URL（/82/cb/c1016...、/c21789...、/c554a...），石河子大学同一校赛通知 2 条 URL 等；leads 表以 `(source_url, raw_title)` 去重，同文异链成为“重复线索”。
2. **同赛事多校建多届**：按设计一届赛事只有一个 edition，但不同学校通知会触发同一年 edition 的多次 upsert；若规范化名称/别名失败，会创建平行赛事。当前主库没有完全同名重复（143 行、别名无撞名），但 336 条未匹配线索中很可能存在“主库没有但多校都通知过”的实体，需要实体解析去重后再入库。
3. **“赛道即赛事”双轨**：21 行 track 与 1 行 competition_tracks 并存（P8），同一赛道可能以两种身份出现。
4. **奖项/活动被当作赛事**：award/festival/exhibition/unknown 共 7 行以上进入 competitions 且部分 `is_competition=True`。
5. **校内截止写进全国截止**：P6 的 3+1 条（e13/e24/e29 通用字段=校内；e22 校内晚于官方）。
6. **高校关系默认 verified_official**（P1）导致“高校通知证明全国事实”的错误归属在统计口径上被放大。

---

## 7. 兼容与不破坏策略

1. **只加不减**：新增表/列全部可空或带默认值；不 drop、不改名、不修改现有列类型。
2. **API 契约冻结**：现有 response schema 的字段名与结构不删除；主体表的新建关系用“新表 + 兼容旧列”表达，例如 organizer 字符串保留，组织外键只作为新增列。
3. **迁移脚本幂等**：所有回填都先查重（唯一键 + upsert），可重复执行；迁移前自动备份 SQLite。
4. **前端不动**：本轮不改任何前端页面；前端字段兼容通过保持 Pydantic schema 与 API 响应不变实现。
5. **展示降级而非删除**：需要“降级”的数据（目录发现型赛事、错误核验状态）通过状态字段与查询过滤实现，先不物理删除。
6. **分阶段切换**：新建 school_competitions/组织/会议表后，仍以旧 API 作为页面数据源，新层先内部写入，待验证后再切换高校页面查询源。

---

## 8. 审计结论摘要

- 系统已实现竞赛主体、届次、高校关系、来源、发现池的大部分物理结构；最大问题不是“缺表”，而是**语义与晋升规则**：学校级来源被当作官方核验、目录发现即建正式赛事、旧的通用截止字段仍在混用、学校目录页面读的是空表。
- 按用户问题 A 回答：当前最大的数据架构问题 = **“高校通知/目录 → 赛事事实”的晋升边界没有严格执行**，即发现层（学校/第三方）与事实层（赛事官方）混在同一张正式表与同一套核验标记里，导致赛事主体、届次、高校关系三层本应隔离的信息互相污染。
- 立即行动（本轮落地）：建立统一组织表与赛事-组织关系、为发现池增加 review_status 状态机、新增会议基础表（无数据不展示）、提供 63 个目录发现型实体的降级清单与回填脚本、全部以幂等增量迁移完成。
