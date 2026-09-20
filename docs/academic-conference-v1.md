# Academic Conference V1 —— 学术会议数据源地图与会议种子库

阶段目标：在不动 Competition 核心架构、不做前端的前提下，证明“学术会议
ConferenceSeries → ConferenceEdition → Source/Provenance → SchoolConference”
这条数据链路真实可行。V1 只做数据模型、来源登记、种子库、少量真实 Edition、
只读 API 与审计。

## 1. 结论摘要

- ConferenceSeries：65（中国 20 / 国际 45），其中 62 个 `verified_official`、
  2 个 `authority_confirmed`、1 个 `pending_verification`（中国新闻史学会学术年会，
  暂只有高校 B 级 + 媒体 C 级来源，进入待补 S/A 来源队列，不删除）。
- ConferenceEdition：32（2026 年 27 / 2025 年 5），全部为真实届次；举办时间与地点
  全部来自官方来源，缺失/冲突字段一律 NULL。
- 来源：S 85 / A 5 / B（高校）5 / C（第三方发现）1；另有 31 条数据源地图登记项。
- SchoolConference：6 条（南开大学、哈尔滨工程大学、哈尔滨工业大学、吉林大学、
  哈尔滨工程大学、国防科技大学），均只用于承办/协办信息，不反向验证会议身份。
- duplicate：0；强制删除：0；第三方/高校来源不验证会议身份。

## 2. 权威层级（与竞赛模块分离）

| 级别 | 含义 | 能否验证会议身份 |
| --- | --- | --- |
| S | 中国科协目录、学会官方会议页、专委会官方页、会议官网、IEEE/ACM/USENIX 等 | 是 |
| A | 国家级学会/协会公告、主办机构/秘书处、正式出版机构 | 是（不单独构成 verified_official） |
| B | 高校/学院/研究院官网 | 否；只能承载高校关系与校内事实 |
| C | 第三方导航、商业平台、聚合站、搜索摘要、媒体转载 | 否；只允许进入发现池 |

EI/SCI/Scopus 声明不直接升级为已收录：数据库使用
`organizer_claimed / publisher_confirmed / database_confirmed / historical_indexed /
unknown` 受控状态，Series 与 Edition 分别维护 `authority_status`。

## 3. 数据源地图

完整条目见 `data/seeds/conference_v1/sources_registry.json`，类别覆盖：

- 中国科协来源：年度重要学术会议指南/目录（S）、科协官网学会活动信息（A）。
- 全国学会/专业委员会来源：CCF、CCF 专委会、CAAI、CAA/CSIG、中国数学会、中国物理学会、
  中国化学会、中国电子学会、中国材料研究学会、中国力学学会、中国天文学会、中国管理现代化
  研究会、CNAIS、中国经济学年会、中国金融学年会等。
- 国际组织来源：IEEE 体系、ACM 各 SIG、USENIX、会议官方独立站、ACL/ISCA、AAAI/IJCAI、
  CVF/ECVA、Internet Society/NDSS。
- 高校补充来源（B）：985/211 高校及学院官网通知。
- 第三方 Discovery（C）：权威媒体转载、商业“EI 会议推荐”平台、社区会议日历仓库。

每个条目记录：名称、类别、source_type、是否可采集、是否有结构化名单、是否需要人工、
authority_level、URL 与备注。

## 4. 种子与导入

- 种子 JSON：`data/seeds/conference_v1/`
  - `series_seed.json`：65 个 Series（含每项官方来源与组织机构）
  - `editions_seed.json`：32 个真实 Edition（日期/地点来自官方页面，未核实保持 NULL）
  - `sources_registry.json`：数据源地图
  - `organizations_catalog.json`：机构注册表（导入时 upsert 到共享 organizations）
  - `discovery_candidates.json`：发现池（V1 暂无需要入库的第三方候选）
- 生成器：`backend/scripts/build_conference_v1_seeds.py`
- 导入器：`backend/scripts/run_conference_v1_seed_import.py`（幂等）
- 治理服务：`backend/app/services/conference_seed_import_service.py`
- 权威规则：`backend/app/services/conference_authority_service.py`
- 只读 API：`backend/app/api/routes/conferences.py`

## 5. 测试与回归

- 全量 pytest：107 个测试函数通过。
- 新增 `backend/tests/test_conference_v1.py`（15 项）覆盖：
  - 高校来源不能验证会议身份；
  - 第三方来源不能验证会议身份；
  - Series 与 Edition 权威状态相互独立；
  - 一个 Series 可有多届 Edition；
  - 一届 deadline 不覆盖另一届；
  - indexing claim ≠ indexed；
  - planned publication ≠ published；
  - 相同缩写不自动合并；
  - 种子重复导入幂等；
  - 未提供截止日期时保持 NULL；
  - 迁移冒烟、API 冒烟、来源证据字段读取、高校关系注册表约束。

## 6. 结束状态

本轮在数据层收口后停止，不扩展会议数量，不开发任何会议前端。下一步（若用户要求）可基于
Edition 生命周期字段接入 CFP/Deadline 提醒、按需刷新与会议详情页数据治理。
