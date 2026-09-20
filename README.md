# 大学生竞赛决策与情报平台 V0.7

平台围绕“多来源发现 -> 实体识别 -> 官方核验 -> 事实展示”组织数据。第三方平台、开源目录和社交渠道只进入 `CompetitionLead`；只有赛事官网、主办方通知或高校官方通知能够把候选信息晋升为竞赛事实。

## 当前能力

- 竞赛实体、别名、父子赛项和客观标签
- 届次、官方/学校/学院截止时间和官方通知溯源
- `DeadlineResolutionService` 按学院、学校、官方顺序给出实际执行截止，同时保留全部时间
- 39 所 985 高校竞赛雷达复查、通知分类和学校化赛事视图
- 赛事组织、历史、参赛规则、赛道和字段级事实来源
- 高校/学院政策目录、竞赛收录关系和证据原文
- 字段级事实来源、候选事实、冲突记录和人工复核队列
- 首页“正在报名、作品提交中、即将开始报名、近期截止”时效视图
- 39 所 985 高校目录及可持续运行的政策采集管线
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
