# Academic Conference V1.1.1 质量报告

- 参考日期：2026-09-06（日期状态由真实官方日期计算，不预测）
- pytest：131/131 通过

## 一、总体数量

- ConferenceSeries：206（V1.1.1 新增 49）
- ConferenceEdition：132（V1.1.1 新增 49）
- SchoolConference：8
- DiscoveryCandidate：3

## 二、学科分布

| 学科 | Series | Edition |
| --- | ---: | ---: |
| 人工智能（artificial_intelligence） | 15 | 7 |
| 计算机科学（computer_science） | 91 | 52 |
| 数据科学（data_science） | 17 | 12 |
| 经济学（economics） | 2 | 1 |
| 教育学（education） | 15 | 14 |
| 工程技术（engineering） | 18 | 9 |
| 交叉学科（interdisciplinary） | 9 | 2 |
| 新闻传播学（journalism_communication） | 18 | 17 |
| 管理科学（management） | 2 | 0 |
| 自然科学（natural_sciences） | 4 | 3 |
| 体育科学（sports_science） | 15 | 15 |

## 三、来源与核验状态

- Source：S=272 / A=8 / B=7 / C=1 / 共 288
- Series 核验状态：{"authority_confirmed": 3, "pending_verification": 1, "verified_official": 202}
- Edition 核验状态：{"authority_confirmed": 5, "verified_official": 127}
- DiscoveryCandidate 状态：{"pending": 2, "rejected": 1}

## 四、recognition 证据

- recognition 记录数：36（涉及 36 个 Series）
- 直接 source_url 比例：36/36 = 100.00%；带 evidence 比例 100.00%

## 五、学生价值与学生机会

- Student Value Series 覆盖率：10/206 = 4.85%（Series 级标签 0 个；覆盖学生机会 Edition 的 Series 10 个）
- Student Opportunity Edition 覆盖率：10/132 = 7.58%
- Edition 机会标签分布：{"doctoral_consortium": 2, "poster": 3, "student_forum": 2, "undergraduate_friendly": 1}

## 六、Edition 关键字段覆盖

- paper_deadline：2 个 Edition
- poster：3 个 Edition
- student track：6 个 Edition
- registration_deadline：4 个 Edition
- 全库 NULL/unknown 统计（共 132 个 Edition）：

| 字段 | 空/NULL 数 | 已填数 |
| --- | ---: | ---: |
| paper_deadline | 130 | 2 |
| poster_deadline | 131 | 1 |
| registration_deadline | 128 | 4 |
| registration_url | 131 | 1 |
| call_for_papers_url | 129 | 3 |
| participation_details | 126 | 6 |
| paper_details | 132 | 0 |
| student_value_tags(语义空) | 123 | 9 |
| edition_status unknown/empty | 0 | - |

## 七、2026 可行动会议

- 定义：存在真实 2026 Edition，且具备 paper_deadline/poster_deadline/registration_deadline/workshop_deadline 或官方学生机会标签中的至少一项；open=官方截止日期仍未来；upcoming=无未来截止但会期未结束；closed=会期已结束；unknown=有官方信息但无可用日期。状态由 2026-09-06 计算，不预测。
- actionable 2026 Edition 共 11 个（涉及 11 个 Series）
- 状态分布：{"closed": 4, "open": 2, "upcoming": 5}

| 状态 | Edition 数 |
| --- | ---: |
| open | 2 |
| upcoming | 5 |
| closed | 4 |
| unknown | 0 |

### 明细

| Series | Edition | 状态 |
| --- | --- | --- |
| AEJMC Annual Conference | AEJMC 2026 Annual Conference | closed |
| ECER | ECER 2026 Tampere | closed |
| Learning Analytics and Knowledge (LAK) | LAK'26 | closed |
| SCMS Annual Conference | SCMS 2026 Annual Conference | closed |
| NCA Annual Convention | NCA 112th Annual Convention | open |
| NeurIPS | NeurIPS 2026 | open |
| EASM European Sport Management Conference | EASM 2026（第 34 届） | upcoming |
| European Communication Conference (ECC) | ECC 2026（第 11 届） | upcoming |
| IEEE BigData | IEEE BigData 2026 | upcoming |
| SPLASH/OOPSLA | SPLASH 2026（含 OOPSLA） | upcoming |
| UIST | UIST 2026 | upcoming |

## 八、修复与遗留

### 本轮修复

- CCF 2022 分级证据回填：为缺 source_url/evidence 的 recognition 行补 CCF 官方目录公告 URL 与 evidence，标记 legacy；36/36 条 recognition 现均带证据（PRCV 保留 pending_evidence）
- 新增 v111_series.py：49 个新 Series，全部为官方学会/会议站核实的新闻传播（15）、体育科学（13）、教育（11）、数据科学（10）
- 新增 editions_v111.py：49 个真实 Edition，均带 S/A 官网来源与会期；4 个 Edition 写入官方学生事实（ECC poster & mentoring、EASM student/PhD seminar、ECER ERC、IEEE BigData Undergraduate & REU Consortium）
- org_catalog.py：新增约 45 个国际学会/组委会组织（总数 151），全部 Series 组织引用在目录内
- builder 新增 recognition evidence 校验、primary/secondary discipline 校验、SchoolConference 证据校验
- conference_authority_service.py：新增 student opportunity tags、actionable 判定与 Edition 日期状态计算（open/upcoming/closed/unknown）
- 只读 API 扩展：Series/Edition 支持 primary_discipline、has_submission、has_student_track、has_poster、has_registration、actionable 过滤，不改变默认返回
- 新增 test_conference_v111.py：10 项行为测试全部通过

### 遗留风险

- 少量官网对自动访问受限（BEA/SCMS/IRE/ECSS 等），日期经官方站内检索片段核对并已写入 source notes，未升级为‘全页直读’的 fully_verified
- SC26 会期仍因官网模板问题保持 NULL；第 14 届全国体育科学大会等既有差异维持 notes 隔离
- Edition 学生机会字段仍偏少：多数 2026 Edition 官方页未写明面向学生的 deadline/学生分轨，按要求保持 NULL/unknown
- student_value_tags 语义补全需要逐 Edition 官方页再采集；Series 级无标签（防止无证据传播）
- 数据库 JSON 列在种子导入时会写入字面量 'null'（SQLAlchemy JSON 行为），报告按语义空值统计；后续可统一清理为 SQL NULL（不改 schema）

## 九、V1.2 建议

- 建议进入 V1.2：True
- 按 CCF 官方目录逐会议行核对 recognition（legacy -> fully_verified）
- 官网恢复后可逐条回补 BEA/SCMS/IRE/ECSS 等 Edition 的深层官方页与日期
- 为已核实的高校承办 Edition（如 ICDM 2026 东北大学）补充校方通知后建 SchoolConference
- 继续为 2026/2027 Edition 采集官方学生 deadline/student registration/volunteer/travel grant 证据
- 清理 JSON 列的 'null' 字面量（不改 schema）
