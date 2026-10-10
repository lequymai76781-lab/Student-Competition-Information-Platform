# 真实 Golden Set 与文档分类器校准报告

2026-10-01 · 人工操作前的准备报告。**DOCUMENT_POLICY_AUTOMATION = BLOCKED**。

专用工作台：[打开 Golden Set 标注页面](http://127.0.0.1:3054/admin/golden-set)。已接入上一轮原样保留的 100 条真实来源，以及 20 份历史政策记录、20 条既存自动关系抽验。当前分类 0/100、政策 0/20、关系 0/20；尚无真实人工质量结论。本轮停在“页面与样本准备好，等待用户人工标注”。

## 29 项验收记录

| # | 项目 | 当前事实与结论 |
| --- | --- | --- |
| 1 | 人工标注数量 | 0；未代选、未代标。自动化测试记录在另一个 fixture 数据集中，评估明确排除。 |
| 2 | 各类型样本数量 | 下表给出原 100 条的冻结预测分布；所有人工类别 n 均为 0。 |
| 3 | overall accuracy | N/A，分母 n=0。不能把机器与自己一致当作准确率。 |
| 4 | 每类 precision | 全部 N/A，待人工标签。 |
| 5 | 每类 recall | 全部 N/A，待人工标签。 |
| 6 | 每类 F1 | 全部 N/A；无支持类别保留未定义，不填 0% 或 100%。 |
| 7 | confusion matrix | 当前为空；评估页及 JSON 导出随完成的真人标签自动生成。 |
| 8 | policy 危险误判 | 四组均未评估：普通通知→政策、普通新闻→政策、报名→推免政策、结果/获奖新闻→综测政策。当前计数没有人工分母，不能解释为“零误判”。四组可重叠，不相加。 |
| 9 | 最佳全局阈值 | 未推荐、未应用。已支持 0.70/0.75/0.80/0.85/0.90/0.95 的描述性曲线；未标注时只有覆盖量，错误率 N/A。 |
| 10 | 各类推荐阈值 | 未推荐。已提供按预测类别分组的阈值曲线、实际类别支持数，以及盲标子集曲线；小样本不能证明低错误率。 |
| 11 | AUTO_CLASSIFIED 比例 | 冻结 100 条样本为 77%；原 200 来源回放为 105/200=52.5%；254 候选为 112/254≈44.1%。均是机器路由状态，不是准确率。 |
| 12 | NEEDS_QUICK_CONFIRM 比例 | 固定样本 9%；200 来源为 14/200=7%；254 候选为 14/254≈5.5%。 |
| 13 | NEEDS_MANUAL_CLASSIFICATION 比例 | 固定样本 14%；200 来源为 81/200=40.5%；254 候选为 128/254≈50.4%。 |
| 14 | informational_only 准确性 | N/A。需要主/次类型检查及明确的“无重要变更”人工核验；只标成新闻不能证明没有延期、更正或规则变化。未核验、否、不确定或高风险标签都会阻止就绪。 |
| 15 | 政策文件抽验 | 准备 20，人工完成 0。覆盖 76 条历史记录的全部 9 种预测类型和 12 类阻断因素，含普通通知对照。76 条历史记录不等于 76 份已确认有效政策。 |
| 16 | 自动认可关系抽验 | 准备 20/59，人工完成 0；核对学校、赛事、来源、认可维度和名称匹配。 |
| 17 | 59 条是否仍可自动 | 暂无人工依据支持正式自动策略；59 条仍仅存在于上一轮隔离回放。任一明确否定会在评估中建议暂停自动正式确认并降为 NEEDS_QUICK_CONFIRM；本实验不执行关系写入或改变策略。 |
| 18 | 审核队列降噪 | 原始 254 pending，冻结回放 252 pending + 2 informational，减少约 0.79%，没有删除条目。本轮未重跑或移出候选。 |
| 19 | 原 254 中需要人工数量 | 当前路由保留 252；其中 244 有明确的分类/事实/关系/政策/风险因素，另 8 条无这些列举因素，需人工判断历史队列残留原因。尚不能宣称“不可再减少的真实最低人工数”。 |
| 20 | 人工工作量减少百分比 | 真实耗时节省未知；0.79% 只是队列数量变化。44.1% 只代表文档分类子任务自动完成，不能作为总人工量节省。 |
| 21 | 分类器最大风险 | 规则分数尚非校准概率；普通通知/新闻误当政策可能放大为认可关系错误。正文、来源定位、政策时效与类别覆盖不足进一步限制判断。 |
| 22 | 自动化安全边界 | 不改分类规则、阈值、自动权限；不抓取；不写正式数据；不重新执行大规模历史自动关系。实验只写独立标注及事件库。 |
| 23 | 修改文件 | 见下方文件范围；仅专用标注页、独立存储接口、纯评估、准备脚本与相应测试/文档，以及路由和管理入口接入。 |
| 24 | 新增测试 | 后端 52 项（评估 41、存储/API 11），前端 12 项；涵盖盲标、草稿/跳过、版本冲突、身份、暴露记录、错误分母、独立存储、抽验和快捷键。 |
| 25 | 后端结果 | 全套 992 项通过，退出码 0。 |
| 26 | 前端结果 | 全套 77 项通过；lint、TypeScript、生产构建均退出码 0。首次测试缺 NODE_PATH、首次隔离构建漏复制 PostCSS 配置的问题均已纠正后复验，原失败日志保留。 |
| 27 | 浏览器验证 | 真实 Edge + 前后端：功能夹具验证 7 组交互路径通过；真实页面只读核验 100+20+20、无预选/曝光/提交、无页面错误。已检查渲染截图。 |
| 28 | 正式数据库 SHA256 | 开始/结束一致，完整值见下表；原候选库、原吞吐实验库、原 CSV、分类器和政策自动化核心文件也一致。 |
| 29 | 下一阶段建议 | 用户先完成盲标分类，再做政策和关系抽验；从评估页导出结果。样本齐备后分析危险误判和阈值曲线，再独立验证候选阈值。本轮不扩大采集或 AUTO 权限。 |

## 固定分类样本

严格保留原 CSV 的 source_id、顺序与冻结机器预测。没有以 synthetic 替换或重新抽一批。

| primary_type | 冻结预测 n | 人工 n | precision | recall | F1 |
| --- | ---: | ---: | --- | --- | --- |
| registration_notice | 14 | 0 | N/A | N/A | N/A |
| organization_notice | 14 | 0 | N/A | N/A | N/A |
| selection_notice | 13 | 0 | N/A | N/A | N/A |
| recommendation_notice | 0 | 0 | N/A | N/A | N/A |
| result_notice | 2 | 0 | N/A | N/A | N/A |
| publicity_notice | 5 | 0 | N/A | N/A | N/A |
| completion_news | 2 | 0 | N/A | N/A | N/A |
| competition_intro | 6 | 0 | N/A | N/A | N/A |
| event_news | 5 | 0 | N/A | N/A | N/A |
| policy_recognition_document | 14 | 0 | N/A | N/A | N/A |
| award_policy_document | 1 | 0 | N/A | N/A | N/A |
| postgraduate_policy_document | 3 | 0 | N/A | N/A | N/A |
| comprehensive_evaluation_policy_document | 2 | 0 | N/A | N/A | N/A |
| innovation_credit_policy_document | 1 | 0 | N/A | N/A | N/A |
| repost | 1 | 0 | N/A | N/A | N/A |
| deadline_extension | 2 | 0 | N/A | N/A | N/A |
| correction_notice | 1 | 0 | N/A | N/A | N/A |
| rule_update | 0 | 0 | N/A | N/A | N/A |
| historical_material | 0 | 0 | N/A | N/A | N/A |
| other | 14 | 0 | N/A | N/A | N/A |

仅 11/100 有已存正文，89 条必须人工查看原文或标记无法判断；32 条缺明确学校、25 条缺发布日期，页面如实标为未提供。部分原始 URL 是学校首页或 local-source 标识，不能当作精准可达的政策证据。未为填补缺失材料发起抓取或生成摘要。先完成人工分类、再进入政策/关系抽验，可减少跨任务看到机器输出带来的影响。

本组按上一轮选样保留，不是随机代表性队列样本。推荐通知、规则更新、历史资料在冻结预测中各为 0；最终人工类别可能不同。少量类别只有 1–3 条，即使观察为全对也不能支持稳定阈值或低风险承诺。总体分类准确率与按置信度估计的自动覆盖率，不能直接外推到真实积压。

## 队列为什么只少 2 条

原 254 条包含 392 个字段建议，分布在 164 条候选；90 条无字段建议，其中 49 条仍是学校关系任务，另 41 条是其他来源任务。当前 252 pending 的重叠因素为：分类待人工 142、字段建议 164、school_mapping 49、flags 26、政策预测 11、高风险 29。以上不能相加。

200 个来源有 13 条 informational_only 预测，映射到 16 个候选，但有字段、学校关系或 flags 的 14 个仍须保留；只有候选 66、193 满足信息归档条件。flags 中 edition_uncertain 是届次不确定，DUPLICATE_SUSPECTED 是疑似重复，不等同已确认字段冲突。保守程度是否过高，需要真人结果，当前不能判断。

应分别解释四层工作：文档分类（112 自动、142 待确认）、字段事实（164 条/392 建议）、政策匹配（另一历史回放中 454 条待处理）、冲突或不确定性复核（26 条，存在交叉）。不能把已自动完成的 document_type 描述为仍待分类，也不能据此清空事实或关系审核。本轮提供分层分析，没有重做生产队列或移除任务以改善指标。

## 抽验限制与计算口径

20 份政策采取目的性覆盖抽样，不是总体准确率的无偏估计。20 条关系全部来自东南大学政策 9，59 条总体也均属于该文档的 policy_recognition 维度；包含唯一 verified_alias 个案，其余为名称精确匹配。不能据此证明跨学校、跨政策文件、推免/奖励/综测/创新学分维度自动匹配安全。

只有 status=annotated、有效身份/时间/类型、人类来源标记且无重复冲突的记录进入人工指标。草稿、跳过与功能夹具排除；未定义分母返回 null。保存时记录预测是否已展示；之后才查看预测，不倒改已经保存的盲标历史，后续修订则记为已曝光。该记录只覆盖本工作台内显式曝光，不能证明人工从未在其他页面看过预测。

阈值曲线是冻结 confidence 的比较，不运行分类器、匹配器、实际放行策略或风险门槛；所有阈值保持未应用。评估返回全部人工、盲标子集和逐类曲线，明确误自动分类数与 policy 误自动分类数。最终生产阈值仍需独立验证；本页永不自动授予正式写入权限。

## 数据库与冻结文件

| 文件 | 开始和结束 SHA256 |
| --- | --- |
| 正式 data/v02.sqlite | `9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320` |
| 原候选 candidates.sqlite | `6bffca4c20f6aaa673246cc1768913cedab789fbd30d4364e0a1f4e64f4a95b6` |
| 原 golden-to-label.csv | `afe2bbb560f90616038e661a92962cdd51476ad8f5311636fbb1414893c9864c` |
| 分类器 source_document_classifier.py | `daecbc599d6325d2b3fabe082565cb88171796604e0e1f8c3a50936afc661bb3` |
| policy_automation_service.py | `23ff9ddfdde5c3915b914c107159aecc7d2a8217d295e451760cc77b14c9159b` |

实验 manifest SHA256：`936cc8c9663e151350d2c678ee1bb952fa017e4f4454ea98d3a67e4a6095e9fb`。真实标注仅写 `.codex-qa/golden-set-20261001/live/annotations.sqlite`；8054 的应用库是单独的登录空库，赛事/政策/审核记录数均为 0。没有正式库 schema 迁移、部署或提交。3054/8054 为本次工作台；原有 3050/8050 与 3053/8053 未改用本实验数据。

## 文件和证据

- `backend/app/api/routes/golden_set.py`
- `backend/app/schemas/golden_set.py`
- `backend/app/services/golden_set_metrics.py`
- `backend/app/services/golden_set_service.py`
- `backend/scripts/prepare_golden_set.py`
- `backend/tests/test_golden_set_metrics.py`
- `backend/tests/test_golden_set_service.py`
- `docs/superpowers/plans/2026-10-01-golden-set.md`
- `docs/superpowers/specs/2026-10-01-golden-set-design.md`
- `frontend/src/app/admin/golden-set/page.tsx`
- `frontend/src/lib/golden-set-api.ts`
- `frontend/tests/golden-set.test.mjs`
- `backend/app/api/router.py`
- `frontend/src/app/admin/page.tsx`
- `docs/GOLDEN_SET_CALIBRATION_REPORT_20261001.md`（本报告）与 `docs/CURRENT_TASK.md`。

本轮证据位于 `.codex-qa/golden-set-20261001/`：`before.json`、`final-checks.json`、`data-report.md`、`queue-analysis.json`、`backend-full.log`、`frontend-tests.log`、`build.log`、`browser-fixture-results.json`、`live-ready.json`、`live-initial-metrics.json` 和 `browser-evidence/`。忽略目录中的账号/数据库不得提交 Git。

**最终状态：DOCUMENT_POLICY_AUTOMATION = BLOCKED。原因是等待用户完成真实人工标签和抽验，并据此完成校准；技术准备与自动化测试不能代替这一步。**
