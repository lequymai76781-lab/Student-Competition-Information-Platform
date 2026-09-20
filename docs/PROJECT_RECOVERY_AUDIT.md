# 项目恢复审计报告

审计日期：2026-09-13（Asia/Shanghai）  
审计基线：`data/v02.sqlite`（最后修改 2026-09-07 23:19，7,393,280 bytes）

## 0. 执行摘要

项目不是原型空壳：竞赛事实、高校关系、来源证据、会议系列/届次和 API 均已落库。但产品处于“数据架构较完整、数据完整度与采集召回不足、会议前端未接通”的阶段。

当前真正主线不是重写首页，而是提高高校官网赛事发现的召回率，并保持高精度和来源可追溯。上一轮 V0.8.2 已修复 discovery 主流程缺失 helper，但三校回归 Page Recall 58.3%、Candidate Recall 54.5%、可行动 Lead Precision 50%，未达到 70% 门槛，明确未进入 15 校验收。

本次新增只读、可重复的数据库审计脚本 `backend/scripts/audit_project_recovery.py`，输出 `data/reports/project_recovery_audit.json`；未改数据库、路由或页面。

## 1. 项目当前结构

- `frontend/`：Next.js App Router 页面、组件、API 客户端和少量显式 mock 数据。
- `backend/`：FastAPI API、SQLAlchemy 模型、Alembic 迁移、采集/解析/清洗/服务层、测试与运行脚本。
- `data/`：SQLite 主库、seed、官方原始快照、报告、日志和备份。
- `references/`：三个独立 Git 参考仓库；不是产品主仓库。
- `deploy/`、`docker-compose.yml`：部署配置。
- `docs/`：版本与验收文档。
- `oil-motion-minimal-demo/`：与主产品隔离的交互演示目录，不属于当前核心数据流。

根目录没有 `.git`。因此 `git status`、`git log --oneline -15`、`git diff` 均返回 `fatal: not a git repository`；不能恢复提交历史或可靠区分未提交文件。最近修改时间与版本报告是本次任务恢复的主要证据。

## 2. 技术栈

- 前端：Next.js 16.3.3、React 19.2.8、TypeScript 5.9、Tailwind CSS 3.4、Lucide。
- 后端：Python、FastAPI 0.112、SQLAlchemy 2.0、Pydantic Settings、Alembic。
- 采集解析：httpx、BeautifulSoup、pdfplumber、PyMuPDF、python-docx、openpyxl。
- 当前本地数据库：SQLite；部署配置支持 PostgreSQL。
- 测试：pytest、ESLint、TypeScript、Next build。

README 标题仍为 V0.7，而迁移、报告和代码已推进到 V1.2 Conference / V0.8.2 Discovery，文档版本明显滞后。

## 3. 当前数据库

主要事实表及行数（直接读取当前 SQLite）：

| 表/对象 | 数量 |
|---|---:|
| competitions | 143 |
| competition_editions | 66 |
| competition_sources | 370 |
| competition_fact_sources | 808 |
| competition_leads | 491 |
| candidate_facts | 593 |
| universities | 113 |
| colleges | 34 |
| school_competitions | 172 |
| competition_policy_recognitions | 102 |
| university_competition_edition_relations | 75 |
| conference_series | 206 |
| conference_editions | 132 |
| conference_sources | 289 |
| conference_opportunities | 15 |
| school_conferences | 8 |
| conference_discipline_mappings | 54 |
| review_queue | 28 |

`university_competition_policies` 和旧 `university_policies` 均为 0；当前高校关系主要由 `school_competitions`、`competition_policy_recognitions`、`university_competition_edition_relations` 承载。API/页面若仍把旧表当主事实来源，会造成语义错位。

## 4. 竞赛数据现状

| 指标 | 实际值 |
|---|---:|
| 竞赛总数 / 非演示 | 143 / 143 |
| 有官网 | 34 |
| 有主办方 | 56 |
| 有介绍 | 127 |
| 有首届/创办年份 | 6 |
| 有赛事历史正文 | 0 |
| 有结构化历史时间线 | 5 |
| 官方核验标记 | 100 |
| detail_ready | 19 |
| 精确同名重复 | 0 |
| 届次总数 | 66 |
| 届次有任一报名/提交截止 | 20 |
| 届次有官网/官方通知 URL | 46 |
| 已核验届次 | 65 |

结论：主体标准化与来源分层真实存在，年度届次没有被批量污染为主体；但历史、官网、主办方和时间字段覆盖低。尤其“赛事历史”尚未完成，不能把空值展示为已完成能力。

来源方面，370 条竞赛来源中 346 条标记官方且已核验；273 条是 HTTP(S) URL，其余包含本地来源 URI 等可解释类型。本审计仅验证格式与库内标记，没有对 659 个竞赛/会议 URL 做全量联网存活检测，因此不能宣称无死链。

## 5. 高校覆盖现状

- 高校 113 所，精确同名重复 0，113 所均有官网。
- 985：39 所；211：112 所（含 985），数据库目录覆盖成立。
- “目录里有学校”不等于“该校赛事发现完成”。
- 新架构 `school_competitions` 有 172 条学校—赛事规范关系；旧证据层另有 102 条政策认可与 75 条届次通知关系。
- 上轮 V0.8.1 对 12 所可计算学校的官网对照：Page Recall 13/54=24.1%，Candidate Recall 14/53=26.4%。V0.8.2 三校回归提升到 58.3% / 54.5%，仍未达 70%。
- 武汉理工大学仍因 403 与降级入口不足为 0/3；华中农业大学 2/4；西南财经大学 5/5。
- 武汉体育学院原始目录保留 97 条 `policy_raw_items`，但当前竞赛主体 143 条、学校 113 所、Lead 491 条，平台已不再只靠该目录建库。风险仍在于政策认可事实仅有 2 份 policy document、102 条 recognition，不能把原始目录的存在泛化为全国高校认可结论。

学校名称有唯一约束并保留 aliases；竞赛有 150 条 aliases。精确同名重复为 0，但别名语义冲突仍需人工抽检，不能仅凭唯一约束判断“无同名异写”。

## 6. 学术会议现状

| 指标 | 实际值 |
|---|---:|
| 正式会议系列 | 206 |
| 会议届次 | 132 |
| 来源 | 289（281 官方且核验） |
| 系列有官网 | 205 |
| 届次有会期 | 130 |
| 已核验届次 | 132 |
| 学生机会 | 15，覆盖 11 个届次 |
| 学生机会有 deadline | 4 |
| 学校—会议关系 | 8 |
| 发现候选 | 3（2 pending，1 rejected） |
| 推荐体系记录 | 36（CCF-A 26、B 9、C 1） |

库中会议来自协会/学会、会议官网和正式推荐体系，会议候选层支持 `non_conference` 与 rejection reason，结构上能隔离讲座/论坛/新闻。正式库没有精确同名重复；但尚未做全量语义去重抽检，不能保证简称或中英文异写完全无重复。

字段模型已支持名称、简称、学科、组织、会期、地点、论文截止、录用通知、Camera Ready、CFP、官网、推荐分类、学生机会和来源。薄弱项是：学生机会仅覆盖 8.3% 届次、可行动截止很少，且系列历史只通过首届年份/多届 editions 间接表达，没有独立完整历史叙述。

最严重的产品断层：后端已有完整会议 API，但前端没有 `/conferences` 列表或详情页，导航和统一搜索也没有会议入口。因基础数据的学生机会/截止覆盖仍低，本轮不贸然开发漂亮日历或补假日期。

## 7. 数据源体系

真实数据流如下：

```text
教育部/全国性正式来源、赛事/主办方官网、高校/学院官网、会议/学会官网
  ↓
Crawler + discovery（网页、附件、站内搜索、sitemap、降级入口）
  ↓
Lead / CandidateFact / ConferenceDiscoveryCandidate（发现层）
  ↓ 标准化、实体匹配、来源权威分级、人工复核
Competition / Edition / SchoolCompetition / ConferenceSeries / ConferenceEdition
  ↓
FastAPI /api/*
  ↓
Next.js 服务端取数与页面展示
```

设计原则正确：第三方/GitHub/搜索只进入发现层；赛事存在与国家级事实由赛事官网、主办方或国家级来源确认；高校来源用于证明学校通知、参与或认可，不反向充当全国赛事最高级来源。

不足：`source_name/source_url/source_type/published_at/retrieved_at/is_official/is_verified` 已存在，但不同实体表仍有多套字段与旧/新关系并存，产品层没有统一“来源卡片”规范。`verified_at` 与 `crawled_at/retrieved_at` 命名也尚未跨域统一。

## 8. 当前页面

存在：首页、竞赛列表、竞赛详情、竞赛日历、高校列表/详情、数据工程、登录注册、onboarding、匹配、个人竞赛、通知、设置、后台与审核。

不存在：会议列表、会议详情、会议筛选、会议搜索入口。

首页 10 秒审计：

1. 网站用途：能，标题和说明明确。
2. 最近可参加竞赛：部分能；有报名中、提交中、即将报名、近期截止区域，但受真实日期覆盖限制。
3. 最近会议：不能；完全未展示。
4. 竞赛何时截止：有可靠日期时能；多数竞赛没有日期。
5. 学校是否认可：部分能；可按学校通知/目录筛选，但“通知、参与、认可”语义容易被用户混同。
6. 信息来自哪里：详情页有来源能力，首页卡片不够直观。
7. 如何筛选：竞赛筛选丰富；会议无筛选，统一搜索不存在。

首页虽仍有介绍区，但首屏已包含搜索与“正在报名”入口，不是纯宣传页。当前不应整体重写；优先补足会议产品入口和来源/时间数据后，再做小范围信息排序优化。

## 9. 当前 API

- 竞赛：列表/详情/更新/高校认可，支持关键词、分类、标签、状态、时间窗、高校/学院、来源范围与排序。
- 高校：列表/详情、政策、发现覆盖。
- 会议：series、editions、opportunities、actionable、disciplines、recognitions、organizations、sources、school-relations、candidates 和 summary。
- 其他：stats、tags、auth/users、recommendations、admin/review、health。

竞赛关键词服务能匹配赛事名称、简称、主办方和标签等，但首页搜索实际只跳转 `/competitions`；不能返回会议与高校的统一结果。

## 10. 当前爬虫

存在 HTML/动态/文档 fetcher，PDF/DOCX/XLSX/HTML parser，竞赛与政策 extractor，高校/学院 discovery、标准化、scheduler 和 pipeline。V0.8.2 最近新增/恢复 canonical URL、known entry、站内搜索、sitemap、feed、403/412 状态与 crawl budget。

当前阻塞不在“有没有爬虫”，而在入口召回：学院/新闻网/PDF/分页/旧 CMS 与被阻断站点的 fallback 不足。Match 与 relation 精度较好，不应通过放宽事实晋升规则换取召回数字。

## 11. Mock / 硬编码数据

- `frontend/src/lib/mock-data.ts` 明确包含 4 个演示竞赛、5 所演示高校、演示政策/认可、静态统计与推荐结果；全部标注 `is_demo` 或 `demo_data`。
- 当前生产 API 客户端 `frontend/src/lib/api.ts` 请求失败时返回空数组/零值，不会自动回退到 mock；主页面没有导入 `mock-data.ts`。因此当前 UI 不会伪装出几百条静态数据。
- `backend/scripts/seed_demo_data.py`、`seed_v09_test_users.py` 是显式演示/测试入口；当前主库 `competitions` 与 `universities` 的 demo 行均为 0。
- `backend/app/services/ai/client.py` 是 Mock AI 接口，占位而非真实 AI 能力；当前不应将其宣传为已完成功能。
- `backend/app/tasks/__init__.py` 是后台任务占位包。
- 前端筛选分类数组为硬编码产品词表，且与数据库 category/tag 是否完全一致需校验。

## 12. 最近一次开发任务推断

### 【上一轮任务恢复判断】

最可能正在进行：修复 V0.8.2 高校竞赛 discovery 的三校回归，重点提升华中农业大学和武汉理工大学的页面/候选召回，并准备达到门槛后进入 15 校验收。

证据：

1. 最近修改报告为 `data/reports/v082_discovery_regression_report.md`（2026-09-08）。
2. 最近代码集中于 `university_radar_discovery_service.py`、`test_v082_discovery_helpers.py`、`run_v082_three_school_regression.py`。
3. 报告明确结论为 blocker 已修、Recall 仍不合格、不得进入 15 校 Acceptance。
4. 主库最后修改时间与该轮回归一致；会议 V1.2 报告早一天，且明确写着“不开始 Conference 前端开发”。

完成程度：约 65%。基础 helper、预算、状态和回归测试已完成；三校验收门槛、武汉理工 fallback、华中农业遗漏页和可行动 Lead 精度未完成。百分比是基于验收清单的工程判断，不是提交进度；因主项目无 Git 历史，无法更精确。

## 13. 当前 Bug / 严重问题

1. P0：高校赛事发现召回仍低，目录覆盖数字不能代表真实覆盖质量。
2. P0：竞赛历史几乎为空（0 段正文、5 条时间线），详情页核心价值不足。
3. P0：会议数据已完成后端但前端完全不可达。
4. P1：竞赛时间字段仅覆盖 20/66 届次，首页“现在还能参加什么”天然稀疏。
5. P1：README 停在 V0.7，实际版本和边界说明滞后。
6. P1：旧/新高校关系表并存，统计和文案必须严格区分目录认可、学校通知与参与证据。
7. P1：前端请求失败静默返回空数据，用户无法区分“真实无数据”和“后端不可用”。
8. P2：根项目没有 Git 元数据，无法审计变更、回滚或做可靠交接。

## 14. BaoyanNews 对标分析

对标站点 2026-09-13 的公开首页把搜索、今日新增、今日截止、关注、未截止推荐、日历、最近更新和官方原文放在同一条行动链上。值得借鉴的是“机会流 + 截止节点 + 官方原文”，不是其品牌视觉或账号体系。

| BaoyanNews 功能 | 本项目是否已有 | 是否值得借鉴 | 当前是否开发 |
|---|---|---|---|
| 首页最新信息 | 竞赛部分已有 | 是 | 小范围优化；会议接通后再合并 |
| 搜索 | 仅竞赛搜索 | 是 | 应做跨竞赛/会议/高校的统一搜索，但非当前 P0 |
| 即将截止 | 竞赛已有 | 是 | 保留并强化数据可信度；会议待数据覆盖 |
| 时间日历 | 竞赛已有 | 有条件 | 不扩展会议日历，先补可靠日期 |
| 分类筛选 | 竞赛较完整、会议 API 完整 | 是 | 会议前端尚未开发 |
| 官方来源 | 数据层较强 | 强烈值得 | 统一详情来源卡片和来源等级文案 |
| 最近更新 | 竞赛有排序/首页区域 | 是 | 应明确“新增”和“事实更新”的差异 |
| 收藏/关注 | 已有用户/收藏基础 | 未来有用 | 暂不优先扩展 |
| 用户进度管理 | 已有个人竞赛状态基础 | 有条件 | 暂不优先扩展到会议 |

## 15. 不应该借鉴的部分

- 不照搬视觉、HTML/CSS、品牌文案或“保研申请”领域模型。
- 不以通知总量作为主要成功指标；本项目更重学术/学校认可价值与事实质量。
- 不在时间数据不足时扩建漂亮但失真的会议日历。
- 不优先建设登录墙、关注上限、材料进度、复杂提醒或 AI 定位。
- 不把高校通知当作赛事存在与国家级别的最高权威来源。

## 16. 建议的信息架构

```text
首页：正在报名 / 即将截止 / 最近更新 / 会议机会（仅真实可行动数据）
竞赛库：国家/全国性正式来源 / 学科 / 当前状态 / 高校证据
学术会议：学科 / 即将截稿 / 即将召开 / 推荐体系 / 学生机会
高校：985 / 211 / 目录认可 / 通知与参与证据（明确区分）
统一搜索：竞赛 / 会议 / 高校 / 学科 / 主办组织
数据来源：来源等级、更新时间、覆盖边界、纠错入口
```

此结构与现有路由兼容，可通过增量页面实现，不需要大改已有 URL。

## 17. 当前最重要任务与下一阶段排序

当前唯一主线：完成 V0.8.2 高校赛事 discovery 的三校门槛，优先修复武汉理工大学 403 后的学院/子站/PDF fallback 与华中农业大学栏目/分页漏召回；达到 Page/Candidate Recall 与可行动 Lead Precision 门槛后，再进入 15 校验收。

1. P0：完成三校 discovery 回归，门槛未达前不扩校。
2. P0：为现有 143 个竞赛按优先级补官方官网、主办方、历史与当前届时间；不新增低价值数量。
3. P1：在会议机会/截止覆盖达到可用阈值后，新增最小会议列表与详情页，直接复用现有 API。
4. P1：建立跨竞赛/会议/高校统一搜索设计与来源卡片规范。
5. P2：更新 README 到真实版本，并为主项目恢复 Git 版本管理（需用户确认历史策略）。

## 审计限制

- 根项目无 Git，无法执行有意义的 status/log/diff；没有据此伪造“未提交文件”判断。
- 本轮未全量联网探测外部 URL，死链状态仍需专门的限速、缓存式检查。
- “精确同名重复为 0”不等于语义重复为 0；中英文名、简称、别名需要专项人工抽样。
- 本报告的数量均来自 2026-09-13 对当前 SQLite 的只读查询；历史 Recall/Precision 引用仓库内最近验收报告。
