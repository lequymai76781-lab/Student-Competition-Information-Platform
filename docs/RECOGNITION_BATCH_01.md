# RECOGNITION_BATCH_01

日期：2026-09-14（Asia/Shanghai）

本批次只处理高校正式竞赛目录、正式分类文件、创新学分/奖励制度和管理办法附件。普通报名通知、获奖新闻、校园活动及搜索结果不构成 Recognition。导入前数据库已备份到 `data/backups/v02_before_recognition_batch_01.sqlite`。

# 1. 目标高校

目标不是随机扩校，而是复用上一批遗留高校，并补入有机会公开核验正式目录的 985/211 样本。10 所学校覆盖北京、江苏、湖北、广东、四川，含 1 所 985、10 所 211。

| 高校 | 地区/类型 | 制度入口 | 结果 |
|---|---|---|---|
| 南京航空航天大学 | 江苏，211 | 教务部竞赛分级分类认定栏目 | success |
| 中国地质大学（武汉） | 湖北，211 | 2026 学科竞赛目录公告及附件 | completed_with_gaps |
| 华南师范大学 | 广东，211 | 学院本科生学科竞赛级别认定表 | success |
| 西南财经大学 | 四川，211 | 2026 学生竞赛认定目录 | success |
| 武汉理工大学 | 湖北，211 | 本科生学科竞赛组织实施细则 | success |
| 北京交通大学 | 北京，211 | 2025 本科生学科竞赛项目列表 | success |
| 北京科技大学 | 北京，211 | 教务处竞赛制度入口 | completed_with_gaps |
| 华中农业大学 | 湖北，211 | 2025 创新创业“111”赛事目录 | completed_with_gaps |
| 西南交通大学 | 四川，211 | 2025 推免 A 类学科竞赛目录 | success |
| 武汉大学 | 湖北，985/211 | 复用既有 2025 学院综合测评政策 | success |

结构化目标清单见 `data/seeds/recognition_batch_01_targets.json`；逐校访问结论见 `data/reports/recognition_batch_01_access.json`。总计 success 7、completed_with_gaps 3、blocked 0。

# 2. 发现的正式文件

本批新核验并留存 7 份正式文件，其中 5 份含可安全匹配的竞赛目录并进入 Recognition，2 份只作支持证据。

| 高校 | 正式文件 | 用途 | 入库 |
|---|---|---|---:|
| 西南财经大学 | 《西南财经大学学生竞赛认定目录（2026版）》 | 当前目录 | 9 |
| 南京航空航天大学 | 《南京航空航天大学大学生竞赛级别认定表（2024年度）》 | 历史分类目录 | 8 |
| 南京航空航天大学 | 2024 年竞赛认定结果调整说明 | 支持文件，不单独生成 Recognition | 0 |
| 北京交通大学 | 《关于公布2025年度本科生学科竞赛项目列表的通知》附件 | 历史分类目录 | 8 |
| 华南师范大学 | 物理与电信工程学院本科生学科竞赛级别认定表 | 学院级历史目录 | 8 |
| 武汉理工大学 | 《本科生学科竞赛组织实施细则（试行）》 | 制度文件，无逐项赛事目录 | 0 |
| 西南交通大学 | 《2025年推荐免试研究生A类学科竞赛目录》 | 历史推荐目录 | 9 |

武汉大学没有重复导入上一批已核验政策。中国地质大学（武汉）和华中农业大学的公告页可访问，但附件链路未获得稳定正文；北京科技大学未找到可公开核验的现行校级完整目录。

# 3. 文件年份

| 高校 | 文件年份 | 发布日期 | 有效性判定 |
|---|---:|---|---|
| 西南财经大学 | 2026 | 2026-07-11 | current_recognition |
| 南京航空航天大学 | 2024 | 2024-08-19 | historical_recognition |
| 北京交通大学 | 2025 | 2025-05-20 | historical_recognition |
| 华南师范大学 | 2018 | 2018-05-23 | historical_recognition；学院范围 |
| 西南交通大学 | 2025 | 2025-06-16 | historical_recognition |

旧目录没有被推断为 2026 年仍有效。`PolicyDocument.year/effective_from/effective_until/is_current` 保存文件有效性，Recognition 使用 `recognized`、`expired`、`uncertain` 分别表达当前、历史和未知；原始 `verified_at` 与批次信息写入 metadata。

# 4. 新增 Recognition

43 条待匹配目录项中，42 条安全匹配并入库，1 条因模糊匹配置信度不足转入 unresolved；另有 5 条预先识别的无安全 canonical 实体目录项一并保留为 unresolved。

| 高校 | 新增 | Current | Historical |
|---|---:|---:|---:|
| 西南财经大学 | 9 | 9 | 0 |
| 南京航空航天大学 | 8 | 0 | 8 |
| 北京交通大学 | 8 | 0 | 8 |
| 华南师范大学 | 8 | 0 | 8 |
| 西南交通大学 | 9 | 0 | 9 |
| 合计 | 42 | 9 | 33 |

全库 Recognition 从 102 增至 144；当前有效 111、历史 33、未知 0。Recognition 覆盖高校从 2 所增至 7 所，其中当前有效覆盖 3 所、历史覆盖 4 所。

# 5. Recognition Level 分布

级别完全保留学校文件原文，没有跨学校折算。

| 原始学校级别 | 数量 |
|---|---:|
| A+ | 3 |
| A | 6 |
| Ⅰ级甲等 | 7 |
| Ⅰ级乙等 | 1 |
| A/B/C | 7 |
| A/B | 1 |
| 一级 | 6 |
| 二级 | 2 |
| A类 | 9 |

因此若按最终汇报口径只统计完全相同的原始标签：`A类=9`、`B类=0`、`C类=0`、其他原始分类 `=33`。`A/B/C` 是文件中的组合级别，不拆分计入 A、B、C。

# 6. 匹配已有赛事

42 条 Recognition 全部匹配已有 canonical 赛事实体，没有因目录中的年份、届次、简称或历史名称创建重复主体。43 次匹配尝试的方法分布为 exact_name 36、historical_name 4、fuzzy_name 2、exact_alias 1；其中 1 次低置信度 fuzzy 没有落 Recognition。

专项回归确认“中国国际大学生创新大赛”与历史名称“中国‘互联网+’大学生创新创业大赛”仍指向同一主体。全库质量审计的归一化同名主体为 0。

# 7. 新增赛事

新增赛事：0。

本批禁止因目录文字直接扩充主赛事库。主库没有可安全确认的 canonical 实体，或模糊匹配低于安全阈值时，一律进入 unresolved。

# 8. unresolved

共 6 条：

| 高校 | 目录原名 | 原始级别 | 原因 |
|---|---|---|---|
| 西南财经大学 | 全国大学生红色旅游创意策划大赛（简称“红旅大赛”） | A | 主库无可安全确认主体 |
| 南京航空航天大学 | “中航工业杯”国际无人飞行器创新大奖赛 | Ⅰ级甲等 | 主库无可安全确认主体 |
| 北京交通大学 | ACM国际大学生程序设计竞赛 | S/A/C | 模糊匹配置信度 0.848，不强制合并 |
| 北京交通大学 | 全国“电脑鼠走迷宫”竞赛 | A/B/C | 主库无可安全确认主体 |
| 华南师范大学 | 东芝杯·中国师范大学师范专业理科大学生教学技能创新实践大赛 | 一级 | 主库无可安全确认主体 |
| 西南交通大学 | 全国大学生交通运输科技大赛 | A类 | 不能与“北京市大学生交通科技大赛”模糊合并 |

上一批 66 条 unresolved Lead 只按“目录、认定、分类、奖励、学分、管理办法、竞赛等级、竞赛项目”等标题特征复筛，命中 0 条；普通比赛通知没有重新处理。完整清单见 `data/reports/unresolved_recognition_leads.json`。

# 9. Historical Recognition

新增历史 Recognition 33 条，来自 2024 年南京航空航天大学、2025 年北京交通大学、2018 年华南师范大学学院目录和 2025 年西南交通大学目录。

这些记录使用 `recognition_status=expired`，前端标签为“历史认可”；个性化当前认可查询改为只接受 `recognized`，不会把 `expired` 当作当前认可。历史数据仍保留学校、范围、原始级别、文件年份、证据页码和官方 URL。

# 10. Current Recognition

新增当前 Recognition 9 条，全部来自西南财经大学 2026 版正式目录。全库当前 Recognition 为 111 条，覆盖 3 所高校。

数据模型对未知有效性使用 `uncertain`；本批没有把无法确认有效期的文件强行入库，因此新增 Unknown 为 0。Recognition 列表接口已补齐 `uncertain` 查询参数，并有回归测试覆盖。

# 11. Evidence URL

5 份入库目录均保存官方发布页、官方附件 URL、本地原始文件、正文文本、文件 hash、页码和核验时间。

| 高校 | 官方发布/证据 | 本地留存 |
|---|---|---|
| 西南财经大学 | [发布页](https://kj.swufe.edu.cn/info/1073/70322.htm) / [目录 PDF](https://kj.swufe.edu.cn/__local/E/F2/28/4A9B8C8E53BB147C41AF64F55AC_758041F7_304C0.pdf) | `data/raw/policy_documents/recognition_batch_01/swufe-2026-catalog.pdf` |
| 南京航空航天大学 | [认定栏目](https://aao.nuaa.edu.cn/8010/list.htm) / [目录 PDF](https://astro.nuaa.edu.cn/_upload/article/files/22/c7/ba45de0c4bfcb38b7479cf3d266a/8294ea14-1c12-4a42-9010-a9a47b692cf3.pdf) | `data/raw/policy_documents/recognition_batch_01/nuaa-2024-catalog.pdf` |
| 北京交通大学 | [发布页](https://civil.bjtu.edu.cn/cms/item/23766.html) / [目录 PDF](https://civil.bjtu.edu.cn/media/attachments/2025/05/20250522092833_611.pdf) | `data/raw/policy_documents/recognition_batch_01/bjtu-2025-catalog.pdf` |
| 华南师范大学 | [官方 PDF](https://statics.scnu.edu.cn/pics/physics/2020/1220/1608470828120820.pdf) | `data/raw/policy_documents/recognition_batch_01/scnu-2018-catalog.pdf` |
| 西南交通大学 | [发布页](https://ctten.swjtu.edu.cn/info/4411/148101.htm) / [目录 PDF](https://ctten.swjtu.edu.cn/__local/5/49/6B/A3655CEEE769DE4470360DDB0B9_2431A58F_4BECE.pdf?e=.pdf) | `data/raw/policy_documents/recognition_batch_01/swjtu-2025-catalog.pdf` |

搜索结果页、第三方转载和普通通知没有进入证据表。

# 12. 抽检结果

使用固定随机种子从本批 42 条落库 Recognition 中抽取 15 条，逐项核对学校、canonical 赛事、原始级别、证据标题、官方 URL、年份和证据页码。

| 结果 | 数量 |
|---|---:|
| PASS | 15 |
| FAIL | 0 |
| UNCERTAIN | 0 |

专项检查 `notification_or_participation_promoted=0`。第一次抽检曾因 canonical 名称比文件原名多“全国”二字而产生一个校验器假阳性；校验逻辑改为按 seed 原始名称与证据行核对，重跑后 15/15 PASS，数据记录本身未变。

验证结果：后端全量 pytest 167 项通过；Recognition 专项及既有关系/归一化回归通过；TypeScript typecheck 通过；第二次导入所有核心表增量为 0；数据质量审计 11 PASS、2 WARN、0 FAIL。

# 13. 失败高校

没有学校达到 `blocked`。3 所学校为 `completed_with_gaps`：

- 中国地质大学（武汉）：公告页明确存在校级目录，但附件进入验证码，不能获得可核验正文。
- 北京科技大学：教务处入口可访问，但没有找到可公开核验的现行校级完整目录；学院材料没有泛化为校级 Recognition。
- 华中农业大学：2025 “111”赛事目录公告可访问，附件下载链路未获得稳定正文。

没有绕过验证码、访问控制或安全机制，也没有用搜索摘要替代原始文件。

# 14. 403 / fallback

上一批 5 所遗留高校结论：

| 高校 | 恢复结果 | fallback |
|---|---|---|
| 南京航空航天大学 | success | 教务认定栏目 + 官方学院域名目录 PDF |
| 中国地质大学（武汉） | completed_with_gaps | 官方学院页找到校级目录入口；附件验证码阻断 |
| 华南师范大学 | success | 官方静态域名 PDF fallback；按学院级历史目录处理 |
| 西南财经大学 | success | 官方学院发布页 + 2026 目录 PDF |
| 武汉理工大学 | success | 主入口问题不再无限重试，改用公开二级站实施细则 PDF；无名单不生成 Recognition |

西南交通大学也通过官方二级站镜像完成 PDF fallback。状态含义是“本轮核验流程有明确结论”，不等于每所学校都新增 Recognition。

# 15. deadline 修复

异常对象为赛事 id 137、edition id 22：“中国首届‘新域新质’创新大赛”被写成 2026 届，全国报名截止 2026-09-15、校内截止 2026-09-30，形成“校内晚于全国”的审计失败。

根因是年份混淆，并把高校来源中的 B 级字段误映射为全国截止；它不是一个真实的校内截止晚于全国截止案例。2026 官方站使用“2026”名称，不支持“首届 2026”的组合；高校 2026 通知给出的校内与主办方节点也早于原库中的 9 月日期。

修复没有删除异常记录。处理如下：

- 清空 edition 上不可核验的 `registration_deadline`、`official_registration_deadline`、`university_registration_deadline`。
- 清空 relation id 39 上被误映射的校内/全国截止，把旧值和根因保留在 metadata。
- 写入事实修订记录，状态改为 `needs_manual_review` / `unknown`，等待正确届次证据后再补。

修复后 `campus_later_than_national=0`，全库质量审计 FAIL 从 1 降为 0。可参考 [2026 赛事官网](https://www.xyxzds.com/) 和 [高校 2026 通知](https://cm.hust.edu.cn/info/1715/38345.htm)。

# 16. 数据完整度变化

| 指标 | 修改前 | 修改后 | 净变化 |
|---|---:|---:|---:|
| 赛事 | 145 | 145 | 0 |
| PolicyDocument | 2 | 7 | +5 |
| PolicyAttachment | 2 | 7 | +5 |
| Recognition | 102 | 144 | +42 |
| Current Recognition | 102 | 111 | +9 |
| Historical Recognition | 0 | 33 | +33 |
| CompetitionSource | 389 | 431 | +42 |
| 已核验 Source | 365 | 407 | +42 |
| school_competitions | 188 | 227 | +39 |
| Recognition 覆盖高校 | 2 | 7 | +5 |
| detail_ready | 19 | 19 | 0 |
| 有官网赛事 | 36 | 36 | 0 |
| 平均 completeness score | 63.14 | 63.07 | -0.07 |

平均分下降只来自 id 137 在删除三个人工错误 deadline 后由 74 降为 64，其他 144 个赛事分数均未下降。这里选择证据真实性优先，不能为了分数保留无法核验的时间。

第二次运行 competitions、documents、attachments、recognitions、sources、school_competitions 等全部净增 0，幂等通过。正式报告见 `data/reports/recognition_batch_01_import.json`，第二次运行见 `data/reports/recognition_batch_01_idempotency.json`，质量审计见 `data/reports/v09_quality_audit_report.json`。

# 17. BaoyanNews 首页准备度

| 模块 | 当前状态 | 本批后的真实依据 |
|---|---|---|
| 正在报名 | PARTIAL | 15 个 edition 标记 registration_open，其中 11 个有未来可行动 deadline；删除 1 条错误截止后可信度提高但覆盖未扩大 |
| 即将截止 | PARTIAL | 未来 30 日有 13 个 edition 含报名/提交节点，仍不足以覆盖 145 个赛事 |
| 最近更新 | PARTIAL | 431 条来源和 7 份政策都有 created/updated/retrieved/published 字段，但语义化 CompetitionUpdateEvent 仍只有 1 条 |
| 高校认可 | PARTIAL（接近 READY） | 144 条、7 所高校、5 份新目录；但当前有效仍只覆盖 3 所，33 条为历史数据，不能宣称广泛覆盖 |
| 学术会议 | PARTIAL | 本批未改会议数据和 UI；206 个系列、132 个届次的基础库仍在，但学生机会/未来 deadline 与前端入口短板未解决 |

“最近更新”现有字段足以先做查询型快照，不需要重做首页：

- 最近新增：按 `Competition.created_at`、`PolicyDocument.created_at` 分实体取数。
- 最近核验：按 `CompetitionSource.retrieved_at`、`SchoolCompetition.verified_at`、政策 metadata 中的 `verified_at` 取数。
- 最近更新：按来源 `published_at/retrieved_at` 与实体 `updated_at` 的最大值排序，并返回变化来源。

但 `updated_at` 会被质量重算和幂等 upsert 触发，不能单独视为“事实更新”；当前只有 1 条 CompetitionUpdateEvent，也没有 Policy Recognition 的语义事件流。因此可先设计 `UNION ALL` 聚合查询并标明事件类型，真正稳定的“事实更新流”仍需后续增量事件物化。

阶段完成度评估为 **78%**。本轮完成了正式目录发现、文件级证据、有效期语义、级别保真、canonical matching、抽检、幂等与 deadline 修复闭环；尚未达到 80% 以上，原因是当前 Recognition 只覆盖 3 所、可靠未来时间覆盖仍低、会议前端仍不可达、语义更新事件不足。
