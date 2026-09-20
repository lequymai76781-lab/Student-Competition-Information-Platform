# Academic Conference V1.1 质量报告

- 阶段：Academic Conference V1.1
- 生成时间：2026-09-06T05:45:27+00:00
- 落库：data/v02.sqlite

## 1. 新增 ConferenceSeries

- 本轮新增：**92**（65 → 157）

## 2. 新增 ConferenceEdition

- 本轮新增：**51**（32 → 83），全部带 S/A 官方来源

## 3. 各学科数量

| 学科 | 代码 | Series | Edition |
| --- | --- | --- | --- |
| 计算机科学 | computer_science | 91 | 52 |
| 人工智能 | artificial_intelligence | 15 | 7 |
| 数据科学 | data_science | 7 | 2 |
| 工程技术 | engineering | 18 | 9 |
| 体育科学 | sports_science | 2 | 2 |
| 新闻传播学 | journalism_communication | 3 | 2 |
| 管理科学 | management | 2 | 0 |
| 经济学 | economics | 2 | 1 |
| 教育学 | education | 4 | 3 |
| 自然科学 | natural_sciences | 4 | 3 |
| 交叉学科 | interdisciplinary | 9 | 2 |

## 4. S/A/B/C 来源数量

- S：204 ｜ A：5 ｜ B：7 ｜ C：1 ｜ 合计：217

## 5. verified / pending / rejected 数量

- Series authority_status：{'authority_confirmed': 2, 'pending_verification': 1, 'verified_official': 154}
- Edition authority_status：{'authority_confirmed': 3, 'verified_official': 80}
- verified_official：234；authority_confirmed：5；pending/unverified：1
- Discovery candidates：{'pending': 2, 'rejected': 1}；rejection reasons：{'unofficial_source_only': 1}

## 6. Student Value Tag 覆盖

- Series 带标签：0；Edition 带标签：5
- Edition 标签分布：{'academic_exchange': 1, 'doctoral_consortium': 1, 'paper_submission': 4, 'poster': 2}
- Series audience：{}；Edition audience：{}
- 说明：只有官网写明学生相关环节才写；Series 级全部为 unknown。

## 7. recognition 覆盖

- 带 recognition 的 Series：36
- 分布：{'CCF-A': 26, 'CCF-B': 9, 'CCF-C': 1}
- 证据策略：只有 CCF/CORE/官方学会分类且带官方依据才写；V1.1 未新增 recognition。

## 8. SchoolConference 数量

- 总数：8（V1.1 新增 2）
- 关系类型：{'co_organizer': 1, 'co_undertaker': 1, 'organizer': 1, 'undertaker': 5}
- 新增第十四届全国体育科学大会承办关系（武汉体育学院、华中师范大学，均已在 universities 表）。

## 9. DiscoveryCandidate 数量

- 总数：3；状态：{'pending': 2, 'rejected': 1}；rejection reasons：{'unofficial_source_only': 1}
- C 级第三方来源只进发现池；rejected 必须带受控 reason。

## 覆盖统计

- 有 Edition 的 Series：83；无 Edition：74
- Edition 有 paper deadline：1
- 有 Student Track 相关标签的 Series：2
- 有学校关系的 Series：6
- 有 recognition 的 Series：36
- Edition indexing_claim_status：{'unknown': 83}

## 10. 数据质量审计发现

### 1. 重复 Series（发现 0）


### 2. 简称冲突（发现 0）


### 3. 第三方冒充官方（发现 1）

```json
[
  {
    "source_id": 70,
    "series_id": 65,
    "edition_id": null,
    "source_type": "third_party_directory",
    "note": "C 级第三方来源被附加到正式 Series/Edition（不允许）",
    "severity": "warning"
  }
]
```

### 4. Edition 年份推断（发现 0）


### 5. 错误城市/国家（发现 0）

```json
[
  {
    "edition": "SC26",
    "finding": "第三方/导航站日期（11 月中旬）与官网模板 bug 冲突，Edition 只写城市与会场、不写日期",
    "action": "已按官网 Attend 区域记录 Chicago / McCormick Place；日期保持 NULL"
  },
  {
    "edition": "CoNEXT 2026",
    "finding": "官方会议页 12-07~10 与 SIGCOMM events/CFP 12-07~11 不一致",
    "action": "Edition 采用官方会议页 12-07~10，notes 记录差异"
  },
  {
    "edition": "第十四届全国体育科学大会",
    "finding": "地方新闻写 11-07~09，学会官网开幕式 11-08",
    "action": "主会期记 11-08~09 并在 notes 说明差异"
  },
  {
    "edition": "SPLASH/ISSTA 2026",
    "finding": "早前摘要记 10-04~09，官方 researchr/splash 页面显示 10-03~09",
    "action": "已按官方页面改为 10-03~09"
  }
]
```
备注：对 2026 主要国际 Edition 与国内 Edition 官网逐条复核；以下差异均以官网为准并留 notes。

### 6. Series/Edition 混淆（发现 6）

```json
[
  {
    "check": "edition_name_without_year",
    "edition_id": 6,
    "name": "AAAI-26",
    "series": 10,
    "severity": "info"
  },
  {
    "check": "edition_name_without_year",
    "edition_id": 26,
    "name": "第二十三届中国金融学年会",
    "series": 64,
    "severity": "info"
  },
  {
    "check": "edition_name_without_year",
    "edition_id": 27,
    "name": "中国化学会第35届学术年会",
    "series": 56,
    "severity": "info"
  },
  {
    "check": "edition_name_without_year",
    "edition_id": 41,
    "name": "SC26",
    "series": 75,
    "severity": "info"
  },
  {
    "check": "edition_name_without_year",
    "edition_id": 79,
    "name": "第十四届全国体育科学大会",
    "series": 152,
    "severity": "info"
  },
  {
    "check": "edition_name_without_year",
    "edition_id": 80,
    "name": "第五届中国基础教育论坛暨中国教育学会第三十七次学术年会",
    "series": 153,
    "severity": "info"
  }
]
```

### 7. 组织机构名称不规范（发现 0）

```json
[
  {
    "note": "V1.1 新增 40 个组织进入 catalog（总数 106），全部 Series 引用的组织均在 catalog 内且名称为规范全称。"
  }
]
```

### 8. recognition 无证据（发现 36）

```json
[
  {
    "series_id": 1,
    "name": "NeurIPS",
    "recognition": {
      "system": "CCF",
      "level": "A",
      "version_year": 2022
    },
    "severity": "warning",
    "note": "V1 写入的 CCF 2022 分级没有逐条 source_url/evidence；分级本身来自公开 CCF 推荐目录，V1.2 需统一回补官方目录页 URL。"
  },
  {
    "series_id": 2,
    "name": "ICML",
    "recognition": {
      "system": "CCF",
      "level": "A",
      "version_year": 2022
    },
    "severity": "warning",
    "note": "V1 写入的 CCF 2022 分级没有逐条 source_url/evidence；分级本身来自公开 CCF 推荐目录，V1.2 需统一回补官方目录页 URL。"
  },
  {
    "series_id": 4,
    "name": "CVPR",
    "recognition": {
      "system": "CCF",
      "level": "A",
      "version_year": 2022
    },
    "severity": "warning",
    "note": "V1 写入的 CCF 2022 分级没有逐条 source_url/evidence；分级本身来自公开 CCF 推荐目录，V1.2 需统一回补官方目录页 URL。"
  },
  {
    "series_id": 5,
    "name": "ICCV",
    "recognition": {
      "system": "CCF",
      "level": "A",
      "version_year": 2022
    },
    "severity": "warning",
    "note": "V1 写入的 CCF 2022 分级没有逐条 source_url/evidence；分级本身来自公开 CCF 推荐目录，V1.2 需统一回补官方目录页 URL。"
  },
  {
    "series_id": 6,
    "name": "ECCV",
    "recognition": {
      "system": "CCF",
      "level": "B",
      "version_year": 2022
    },
    "severity": "warning",
    "note": "V1 写入的 CCF 2022 分级没有逐条 source_url/evidence；分级本身来自公开 CCF 推荐目录，V1.2 需统一回补官方目录页 URL。"
  }
]
```
备注：V1 的 65 个 Series 含 CCF 2022 分级（无 source_url）；V1.1 新增 Series 一律未写 recognition，待 V1.2 以 CCF 官方目录页回补证据。

### 9. Student Track 推断（发现 0）

备注：仅当官网写明学生相关环节/学生可参会才写标签；Series 级标签为 0。

### 10. historical_indexed 误展示（发现 0）

```json
{
  "indexing_claim_status": {
    "unknown": 83
  }
}
```
备注：没有 Edition 使用 historical_indexed 冒充当前收录状态。

## 11. 修复的问题

- org_catalog.py：补齐 40 个缺失组织（ACM SIG*/IEEE ComSoc/EMBS、IFIP、SIAM、IACR、教育/传播/体育学会、国内学会等），引用覆盖 100%
- editions_v11.py：新增 51 个真实 Edition（全部带 S/A 官网来源，2026 国际 44 个 + 2025 国内 7 个，详见数据）
- v11_series.py 与主生成器合并：Series 65 -> 157（新增 92 个，与既有 65 个零重叠）
- SPLASH/ISSTA 2026 会期按官网 researchr/SPLASH 页从 10-04~09 修正为 10-03~09
- SC26 仅记 Chicago/McCormick Place，拒绝第三方导航站日期（官网模板 bug）
- CoNEXT 2026 采用官方会议页 12-07~10，notes 保留 SIGCOMM events/CFP 12-07~11 差异
- 第十四届全国体育科学大会统一为 11-08~09 主会期并在 notes 说明 11-07~09 的分歧来源
- RECOMB 组织与 Edition 来源改指向 recomb.org 官方站（recomb2026 页已打开核验）
- 发现池：新增 3 条真实 C 级候选（2 pending + 1 rejected 带受控 rejection_reason），不进入 Series/Edition

## 12. 仍然存在的风险

- recognition：V1 的 CCF 2022 分级缺少逐条 source_url；V1.1 新增 Series 未写 recognition（宁缺毋滥）。
- SC26 会期仍未写入（官网 Attendee 模板 bug），只能等官方修复后再回补。
- 少数导航站/地方新闻日期与官网不一致，已用 notes 隔离；后续刷新需继续以官网为准。
- student_value_tags 只覆盖 4 个 Edition（splash/issta/uist 官网写明环节、cse_education 官网写明学生收费参会），覆盖偏窄是刻意为之。
- CIES 2026 等无强官网证据的 Edition 未收录；NAACL 2026（ACL 在美国年份停办）与 ICCV 2026（双年）均未建。

## 13. pytest 结果

- 通过 121/121（pytest exit 0）；test_conference_v1.py 15 项保持通过，test_conference_v11.py 新增覆盖 alias 去重、边界、来源优先级、recognition 证据、标签、unknown、幂等、日期校验、Discovery rejected、SchoolConference 边界。

## 14. 修改文件列表

- backend/app/models/architecture.py（ConferenceSeries/Edition 新增 student_value_tags/audience 及 Edition notes）
- backend/app/models/conference.py（DiscoveryCandidate.rejection_reason）
- backend/app/services/conference_authority_service.py（受控词表、recognition 校验与证据规则）
- backend/app/services/conference_seed_import_service.py（新字段导入、Edition 日期校验、alias 幂等合并修复）
- backend/app/services/conference_service.py（只读过滤参数扩展）
- backend/app/api/routes/conferences.py（只读 API 参数兼容扩展）
- backend/app/schemas/conference.py（V1.1 字段只读输出）
- backend/alembic/versions/202609060002_v11_conference_student_value.py
- backend/alembic/versions/202609060003_conference_edition_notes.py
- backend/scripts/conference_v1_seeds/org_catalog.py
- backend/scripts/conference_v1_seeds/editions_v11.py
- backend/scripts/conference_v1_seeds/discovery_candidates.py
- backend/scripts/conference_v1_seeds/v11_series.py（沿用）
- backend/scripts/build_conference_v1_seeds.py
- backend/scripts/report_conference_v11.py
- backend/tests/test_conference_v1.py（迁移 smoke 期望版本更新为 head）
- backend/tests/test_conference_v11.py
- data/seeds/conference_v1/*.json（重新生成）
- data/reports/conference_v11_quality_report.{md,json}

## 15. 是否建议进入 Academic Conference V1.2

- 建议：是
- 建议范围：
  - 以 CCF 官方推荐目录页逐条回补 recognition + source_url 证据（CS/AI/Data 学科）
  - 补 SC26 会期（待官网修复）、CIES 2026 等边缘 Edition
  - 扩展 student_value_tags 官方证据采集（student registration/volunteer/travel grant）
  - 按学科细分子领域标签与检索
- 约束：
  - 不得为达标批量灌入无官网证据 Edition；未核验的 recognition 一律不写。
