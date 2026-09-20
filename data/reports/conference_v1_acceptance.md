# Academic Conference V1 验收报告

- 生成时间：2026-09-06T04:54:28+00:00
- 落库：data/v02.sqlite

## A. 数据源地图

| 名称 | 类别 | 类型 | 可采集 | 结构化名单 | 需人工 | 权威级 |
| --- | --- | --- | --- | --- | --- | --- |
| 中国科协年度重要学术会议指南/目录 | 中国科协来源 | cast_official_directory | 是 | 按年发布目录/附件（PDF/Excel/HTML 因年而异） | 是 | S |
| 中国科协官网学会学术活动信息 | 中国科协来源 | association_official_notice | 是 | 否 | 是 | A |
| 中国计算机学会（CCF） | 全国学会来源 | national_society_official_meeting_page | 是 | CNCC/HPC China 等官方页面为 HTML；部分新闻页结构不稳定 | 是 | S |
| CCF 专业委员会会议专题页 | 专业委员会来源 | subcommittee_official | 是 | 否 | 是 | S |
| 中国人工智能学会（CAAI） | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国自动化学会（CAA）/ 中国自动化大会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国图象图形学学会（CSIG） | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国数学会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国物理学会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国化学会 | 全国学会来源 | national_society_official_meeting_page | 是 | 年会页面集中管理分会信息 | 是 | S |
| 中国电子学会（CIE） | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国材料研究学会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国力学学会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国天文学会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国管理现代化研究会 | 全国学会来源 | national_society_official_meeting_page | 是 | 否 | 是 | S |
| 中国系统工程学会信息系统工程专业委员会（CNAIS） | 专业委员会来源 | subcommittee_official | 是 | 否 | 是 | S |
| 中国经济学年会（秘书处/中国经济学教育科研网） | 全国学会来源 | organizer_official | 是 | 否 | 是 | A |
| 中国金融学年会（理事会/中国金融研究网） | 全国学会来源 | organizer_official | 是 | 否 | 是 | A |
| 中国新闻史学会 | 全国学会来源 | university_official | 否 | 否 | 是 | B |
| IEEE / IEEE Computer Society / IEEE RAS / IEEE SPS | 国际组织来源 | international_professional_org | 是 | conference calendar 结构较好；每届独立站 | 否 | S |
| ACM 及各 SIG | 国际组织来源 | international_professional_org | 是 | SIG 会议页面较稳定；每届独立站 | 否 | S |
| USENIX Association | 国际组织来源 | international_professional_org | 是 | 会议/CFP 页面结构良好 | 否 | S |
| 会议官方独立站（NeurIPS/ICML/ICLR/ECCV/NDSS 等） | 国际组织来源 | conference_official_site | 是 | 否 | 否 | S |
| Association for Computational Linguistics / ISCA(语音) | 国际组织来源 | international_professional_org | 是 | 否 | 否 | S |
| AAAI / IJCAI | 国际组织来源 | international_professional_org | 是 | 否 | 否 | S |
| The CVF / ECVA（视觉会议体系） | 国际组织来源 | international_professional_org | 是 | 否 | 否 | S |
| Internet Society / NDSS Symposium | 国际组织来源 | conference_official_site | 是 | 否 | 否 | S |
| 985/211 高校及学院官网会议通知 | 高校补充来源 | university_official | 是 | 否 | 是 | B |
| 权威媒体转载（人民网/新华社/科学网等） | 第三方Discovery来源 | third_party_directory | 是 | 否 | 是 | C |
| 商业会议平台 / EI 会议推荐站 | 第三方Discovery来源 | commercial_conference_platform | 是 | 是 | 是 | C |
| 社区会议日历（CCFDDL / AI Conference Deadlines 等） | 第三方Discovery来源 | conference_aggregator | 是 | 是 | 否 | C |

## B. ConferenceSeries

- 总数：65
- 中国会议：20
- 国际会议：45
- 按学科：
  - 计算机科学（Computer Science）：35
  - 人工智能（Artificial Intelligence）：10
  - 数据科学（Data Science）：3
  - 工程技术（Engineering）：8
  - 新闻传播学（Journalism & Communication）：1
  - 管理科学（Management Science）：2
  - 经济学（Economics）：2
  - 自然科学（Natural Sciences）：4
- 有官方来源（S/A）：64
- 无官方来源：1
- duplicate：0
- pending：1
- authority_status：{'authority_confirmed': 2, 'pending_verification': 1, 'verified_official': 62}

## C. ConferenceEdition

- 总数：32
- 2026：27
- 2025：5
- 有CFP：3
- 有 paper deadline：1
- 有 registration deadline：1
- 有举办时间：32
- 有地点：32
- authority_status：{'authority_confirmed': 3, 'verified_official': 29}
- indexing_claim_status 分布：{'unknown': 32}
- publication_status 分布：{'unknown': 32}

## D. 来源质量

- Level 1 / S：85
- Level 2 / A：5
- 高校 secondary（B）：5
- 第三方 discovery（C）：1
- 数据源地图登记条目：31

## E. 风险与人工复核

- Series risk_flags：{'official_site_missing': 1}
- Edition risk_flags：无
- Candidate risk_flags：无
- Discovery candidates 总量：0
- 无强制删除：风险项仅进入 review/pending。

## Provenance 与关系

- conference_sources：96
- conference_organizations links：79
- school_conferences：6
- indexing 受控状态：organizer_claimed / publisher_confirmed / database_confirmed / historical_indexed / unknown
- publication 受控状态：planned / confirmed / published / indexed / unknown
- 官网/第三方声明仅按 organizer_claimed 保存，不升级为 database_confirmed/indexed。

## 完成标准

- source_map_done：PASS
- conference_series_models_usable：PASS
- conference_edition_models_usable：PASS
- school_conference_usable：PASS
- series_seed_count_in_range：PASS
- real_editions_target_met：PASS
- real_editions_total：32
- source_provenance_traceable：PASS
- ei_claim_not_shown_as_confirmed：PASS
- university_source_does_not_verify_identity：PASS
- no_frontend_built：PASS
- no_low_quality_bulk_import：PASS
- tests_passed：PASS

## 测试与回归

- 全量后端测试：107 个测试函数通过（pytest exit 0）；其中 Academic Conference V1 新增 tests/test_conference_v1.py 15 项，覆盖 10 条指定行为 + 迁移/API/来源证据冒烟。
- 迁移：202609060001_v1_conference_foundation 已执行；alembic_version = 202609060001。
- 编译检查：python -m compileall app scripts tests 通过。

## 产物

- 种子：data/seeds/conference_v1/{series_seed.json, editions_seed.json, sources_registry.json, organizations_catalog.json, discovery_candidates.json}
- 服务：backend/app/services/conference_seed_import_service.py
- 只读 API：/api/conferences/*（series/editions/sources/school-relations/candidates/vocabulary）
- 导入脚本：backend/scripts/run_conference_v1_seed_import.py（幂等）
