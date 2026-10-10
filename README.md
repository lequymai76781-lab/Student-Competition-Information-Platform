# 大学生竞赛决策与情报平台

## 当前状态（2026-09-28）

审核吞吐优化与高校关系闭环的代码及自动化验证已完成：后端792项、前端57项，lint/typecheck/build通过；真实候选36条计时、2条政策闭环与独立合成50条批量验证通过，正式库及原254候选库SHA256不变。用户本轮暂不提供人工操作样本，因此 **REVIEW_THROUGHPUT = BLOCKED**，唯一阻塞为人工吞吐与人力估算未实测；不继续扩量。详见 [33项审核吞吐报告](docs/REVIEW_THROUGHPUT_REPORT_20260928.md)。

前阶段结果：

中规模真实数据扩展与普通本科高校覆盖试点已完成：80 个选定赛事（69 个有结构化提案、11 个仅线索）、30 校（28 校取得正文）；新增 122 条来源、147 条待审记录，独立主候选库共 254 条 pending。后端 647 项、前端 45 项、lint/typecheck/build 及真实浏览器 10 组与 2 项日期断言通过。正式库 SHA256 不变，无迁移。**MID_SCALE_DATA_EXPANSION = PASS**；已停止扩量，暂不建议继续扩大，需先验证人工吞吐、学校关系正式审核与来源访问稳定性。详见 [中规模试点报告](docs/MID_SCALE_DATA_EXPANSION_REPORT_20260928.md)、[来源清单](docs/mid-scale/README.md) 和 [逐校覆盖](docs/mid-scale/SCHOOL_COVERAGE.md)。

上一小批量阶段：24 个赛事、74 条来源、107 条待审候选、252 项字段提案，**REAL_DATA_PILOT = PASS**。该独立候选库保持原样；本轮在另一个隔离副本扩展。

当前阶段已转向核心用户流程：按日期和学校截止筛选赛事 → 同一届次详情和官方依据 → 登录提交纠错/遗漏 → 管理员审核。新增 `/contribute`，所有学校使用同一选择入口，没有面向用户的学校等级划分。

上一阶段已通过最终定向复核：R06已关闭；R12保留为P2性能债务，R13/R14保留为P3。该阶段后端458项、前端30项通过，lint/typecheck/build通过，原48文件可以收口。

字段级入库与来源核验阶段已完成：用户纠错/赛事补充和采集进入候选，管理员核验来源后逐字段批准，正式更新与审计同事务提交；旧写入入口已封堵。完整后端584项、前端43项通过，lint/typecheck/build通过，正常应用真实浏览器12项通过。正式库SHA256不变，未迁移或部署。详见本阶段报告。

本轮没有迁移或修改正式数据库，也未新增真实采集；前两轮采集资料仍仅在独立候选库。正式库原始记录为176个赛事对象、108个届次、196所高校；其中包含存档/重复/非竞赛对象，不能等同于大厅可见数量。会议后端已有独立模块，前端仍待建设。

- [当前状态与实施依据](docs/CORE_USER_JOURNEY_20260927.md)
- [阶段开发报告与验证结果](docs/STAGE_DEVELOPMENT_REPORT_20260927.md)
- [阶段开发独立审查](docs/INDEPENDENT_REVIEW_20260927.md)
- [安全与数据一致性修复报告](docs/SECURITY_DATA_CONSISTENCY_FIX_REPORT_20260927.md)
- [阶段最终定向复核报告](docs/FINAL_TARGETED_REVIEW_20260927.md)
- [字段级入库与来源核验阶段报告](docs/FIELD_INGESTION_SOURCE_REVIEW_REPORT_20260927.md)
- [已完成的旧写入入口切换](docs/FIELD_REVIEW_WRITE_GATE_APPROVAL.md)
- [当前任务与接续入口](docs/CURRENT_TASK.md)

截止纠错经候选、明确届次、来源核验和逐字段批准后写入并保留修订。赛事补充支持同一审核流程；学校等其他实体仍进入原队列，“已核验，待整理入库”不代表正式事实已更新。以下版本章节保留历史数据工程记录，不能作为当前覆盖率或完成度结论。

竞赛和届次正式写入已统一经过人工字段审核；来源优先级仅供判断，不自动覆盖。运行时SessionLocal阻止未经审核的事实写入，尚未适配的历史脚本将明确报错，需要先转为候选。这是应用会话保护，不是外部数据库管理员权限隔离。

## 当前能力

- 竞赛实体、别名、父子赛项和客观标签
- 届次、官方/学校/学院截止时间和官方通知溯源
- `DeadlineResolutionService` 按学院、学校、官方顺序给出实际执行截止，同时保留全部时间
- 高校竞赛雷达复查、通知分类和学校化赛事视图；实际覆盖以当前状态报告为准
- 赛事组织、历史、参赛规则、赛道和字段级事实来源
- 高校/学院政策目录、竞赛收录关系和证据原文
- 字段级事实来源、候选事实、冲突记录和人工复核队列
- 首页“正在报名、作品提交中、即将开始报名、近期截止”时效视图
- 高校目录及可持续运行的政策采集管线
- 武汉体育学院 97 条原始目录逐条保留并完成实体分类

数据库不会因导入脚本被清空。无法确认的信息保持空值，界面统一显示“暂未核实”。

## 技术栈

- 前端：Next.js 16、React、TypeScript、Tailwind CSS
- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic
- 当前本地数据：SQLite `data/v02.sqlite`
- 可选部署：PostgreSQL、Docker Compose

## 本地启动

后端：

```powershell
cd backend
$env:DATABASE_URL="sqlite:///D:/Python/xuesheng/data/v02.sqlite"
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

前端：

```powershell
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

访问 `http://127.0.0.1:3000`，后端 OpenAPI 位于 `http://127.0.0.1:8001/docs`。前端通过 `frontend/.env.local` 的 `NEXT_PUBLIC_API_BASE_URL` 连接后端。

## V0.7 数据工程

先备份数据库，再执行迁移和幂等导入：

```powershell
cd backend
$env:DATABASE_URL="sqlite:///D:/Python/xuesheng/data/v02.sqlite"
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe scripts\run_v07_competition_enrichment.py --quiet
```

V0.7 迁移版本为 `202609010006`。任务可重复执行，不会重复创建线索、事实来源、竞赛或届次。五所 partial 高校的复查数据维护在 `data/seeds/v07_partial_rechecks.json`；仍无法核实的学校继续保留 partial，不用虚假数据换取完成状态。

验收报告输出到 `data/reports/v07_competition_enrichment_acceptance_report.json`，包含 23 个 V0.6 新增赛事审计、截止时间验收、字段补全统计和 10 条详情抽检。

985 政策管线继续独立运行：

```powershell
.\venv\Scripts\python.exe -m scripts.run_985_policy_pipeline
```

## 开源发现来源

已有目录种子来自 [Tomzkl/college-competitions-skill](https://github.com/Tomzkl/college-competitions-skill)：

- 文件：`competition-catalog.md`、`SKILL.md`
- 导入 commit：`98da22d75b23c059c77d69d24a650b48553d7492`
- 许可证：MIT，许可证副本保留在 `references/college-competitions-skill/LICENSE`
- 数据库标记：`source_type=github_seed`、`is_official=false`、`is_verified=false`

V0.4 另采集 [Nemoyuzx/contest-ddl](https://github.com/Nemoyuzx/contest-ddl) 的公开快照，导入 commit 为 `9e490f67a594ec37682d4fc11490a254c661bbe3`，许可证为 MIT。其 147 条竞赛类记录只保存为线索和候选事实，不直接生成官方届次或高校政策关系。

## 测试

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest

cd ..\frontend
npm run lint
npm run typecheck
npm run build
```

V0.7 迁移前数据库备份位于 `data/backups/v02-before-v07-enrichment.sqlite`。

## 数据边界

- `CompetitionLead` 与 `CandidateFact` 是发现层，不自动进入事实层。
- `official_notice` 和已核验 `CompetitionEdition` 才能证明赛事当前届次与日期。
- `registration_notice`、`internal_selection`、`submission_notice` 才能参与学校截止解析；获奖新闻和结果公示不能打开报名状态。
- 搜索引擎、GitHub 和聚合平台只承担信息发现；关键事实优先使用赛事官网、主办方或高校正式通知。
- 未发现学校公开通知只表示当前公开检索没有命中，不表示学校未组织、不认可或无法参加。
- `university_policy` 只证明对应高校/学院文件中的认可，不证明赛事时间。
- 武汉体育学院新闻传播学院目录来自用户提供的正式 PDF 扫描件；本地来源 URI 用于保留文件溯源，不冒充公开网页地址。
- 尚无官方证据的字段保持空值或 `unknown/upcoming`，禁止虚构官网、主办方、报名截止或政策等级。
