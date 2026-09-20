# Core Competition Library V1 — Release Candidate 验收报告

- 生成时间：2026-09-05T15:14:08.420758+00:00

## A. 核心库

- 核心 Competition 数量：100
- 正式大厅实际展示（含 core + pending/school 带标签实体）：133
- 隐藏 duplicate：2；隐藏 non_competition/suspected：7；隐藏无证据 unverified：1
- pending 展示：24（前端明确显示“信息核验中”）
- 人工审核：review_queue pending 28；RoboTac/CURC 保持人工

## B. 页面字段覆盖（冻结，不再追求增长）

| 指标 | 当前 |
| --- | --- |
| 主办单位 | 35.0% |
| 官方页面/承载页 | 31.0% |
| 参赛对象 | 13.0% |
| ≥1届历史 | 39.0% |
| ≥2届历史 | 5.0% |
| ≥3届历史 | 3.0% |
| 2025+ 当前届信息 | 18.0% |

## C. 页面质量（20 项抽样）

- PASS：14；WARN：6；FAIL：0
- WARN 均为“无 Edition/无官方通知页”的已知缺口（有数据才显示，无则不显示）；无 FAIL。

## D. 数据安全

- 高校截止污染全国截止：2 个已知历史遗留（comp109/137 Edition 全国字段由高校来源填写），保留待 S/A 届次证据，不冒充；另有 comp137 校内截止晚于全国截止 1 项人工复核
- 高校等级污染全国等级：0
- 第三方 URL 冒充官网：0
- duplicate/non_competition 进入大厅：0
- AI 生成事实：0（模板化“首次发现”简介在前端被过滤不展示）

## E. 维护与按需更新

- 维护队列任务汇总：{"missing_history": 96, "missing_latest_edition": 85, "missing_official_page": 69, "missing_organizer": 65, "missing_participant_rule": 87, "official_site_js_only": 7}
- 已提供 refresh_competition_facts(competition_id) 与 CLI（run_v14_refresh_competition.py --id N），2027 届发布时只更新单个赛事，不重跑全库

## F. 备注

- 大小挑：comp2/comp3 两个独立赛事，别名仅作 alias，未合并
- RoboTac/CURC 等人工项未强决
- pending/school 与已核验赛事的展示规则见前端核验徽标