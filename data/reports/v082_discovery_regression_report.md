# V0.8.2 Discovery Regression Report

- 版本：V0.8.2
- 范围：三校 regression（西南财经大学、华中农业大学、武汉理工大学）
- 运行时间：2026-09-07（Asia/Shanghai）
- 数据文件：[v082_three_school_regression.json](D:/Python/xuesheng/data/reports/v082_three_school_regression.json)
- 结论：**B.【V0.8.2 blocker 已修复，但三校 Recall 仍不合格，需要继续修 discovery】**

## 1. 接管时的半成品状态

上一轮已经向 `university_radar_discovery_service.py` 写入部分 V0.8.2 结构，但主流程调用的多个 helper 不存在或签名未迁移，真实 discovery 会直接 `AttributeError` / `TypeError`。

## 2. 缺失 helper 清单

本次逐项比对后补齐：

- `_canonical_url`
- `_fetch`
- `_department_match`
- `_department_candidates`（priority/tier 排序）
- `_probe_known_entries`
- `_merge_departments`
- `_internal_search_candidates`
- `_sitemap_candidates`（funnel + sitemap index 递归）
- `_scan_department_feeds`（CrawlBudget + funnel）
- `_search_multi(required_domain=...)`
- `_title_score`

同时补齐：

- `DiscoveryFunnel.source_unavailable`
- `DiscoveryFunnel.candidate_urls` 实际记录
- `DiscoveryFunnel.matched_competitions / relations_created / deadlines_found`
- `_is_blocked` 支持 403、412、429

## 3. 如何恢复 helper API

- 未整份 apply diff。
- 先以当前 caller 为准，逐一检查方法存在性、签名、返回值。
- 优先复用旧实现，再参考 [v082-entry-helpers.diff](D:/Python/xuesheng/tmp/v082-entry-helpers.diff) 移植。
- 统一 `_fetch` 作为唯一页面抓取入口，使 Funnel 能记录成功、403、412、timeout、source_unavailable。
- 保持搜索结果是 URL discovery，最终仍要抓取官方页面后才进入 Lead。

## 4. 修改文件

- [university_radar_discovery_service.py](D:/Python/xuesheng/backend/app/services/university_radar_discovery_service.py)
- [test_v082_discovery_helpers.py](D:/Python/xuesheng/backend/tests/test_v082_discovery_helpers.py)
- [run_v082_three_school_regression.py](D:/Python/xuesheng/backend/scripts/run_v082_three_school_regression.py)

## 5. 新增测试

新增 13 个 V0.8.2 测试，覆盖：

- canonical URL
- department discovery / priority
- duplicate department merge
- known entry probe budget
- internal search candidate
- sitemap candidate
- 403 / 412 fallback
- `source_unavailable != no_competition`
- DiscoveryFunnel counter
- CrawlBudget 边界
- 主 discovery 路径 end-to-end integration

Backend 全量测试：155/155 通过。

## 6. 三校 V0.8.2 Funnel

| 学校 | entry | department | urls discovered | pages fetched | 403 | 412 | source_unavailable | parsed | candidate pages | Lead | matched | relations | deadlines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 华中农业大学 | 17 | 17 | 88 | 85 | 10 | 0 | 10 | 65 | 60 | 34 | 8 | 4 | 10 |
| 武汉理工大学 | 19 | 19 | 23 | 23 | 14 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| 西南财经大学 | 17 | 17 | 57 | 54 | 0 | 0 | 0 | 49 | 26 | 12 | 3 | 3 | 2 |

## 7. 三校 known-page hit

已知页面来自上一轮人工验收报告和本轮官网核对。

### 西南财经大学：5/5

- 第六届全国大学生发展经济学论文大赛成功举办：命中
- 学校在第五届CMAU全国大学生市场研究与商业策划大赛中喜获佳绩：命中
- 学校第一届AI智能体创新大赛（中移杯）颁奖活动圆满举行：命中
- 2025年西南财经大学数学建模培训选拔赛报名通知：命中
- 2026光华创新创业大赛暨中国国际大学生创新大赛校内选拔通知：命中

### 华中农业大学：2/4

- 全国高校商业精英挑战赛品牌策划竞赛校内选拔：命中
- 全国大学生英语竞赛：命中
- 全国大学生市场调查与分析大赛校内选拔：未命中
- 外研社·国才杯“四新”专项赛校赛：未命中

### 武汉理工大学：0/3

- 智能建造竞赛通知：未命中
- 研究生人工智能创新大赛通知：未命中
- 华为软件精英挑战赛校内赛：未命中

原因：主入口仍为 HTTP 403，known-path 也未取得可解析官方页面，最终 0 Lead。

## 8. Page Recall

- 已知页面总数：12
- 命中页面：7
- **Page Recall = 58.3%（7/12）**

未达到三校门槛 `>=70%`。

## 9. Candidate Recall

- 已知候选页面总数：11
- 命中候选页面：6
- **Candidate Recall = 54.5%（6/11）**

未达到三校门槛 `>=70%`。

## 10. Lead Precision

按可行动口径（registration_notice / internal_selection / submission_notice / competition_notice / competition_announcement / team_recruitment）：

- 可行动 Lead：23
- 全部 Lead：46
- **Lead Precision = 50.0%（23/46）**

若把获奖/结果证据也算作有价值的赛事证据，则约 95.7%，但两者不能混为一谈。可行动 Lead Precision 仍低于 70%。

## 11. Match Precision

有匹配赛事名的 Lead 共 28 条。逐条标题级检查未发现明显错配；但本轮未做固定随机样本的人工全量复核，因此不宣称精确百分比。

## 12. 403 / 412 fallback

- 403/412 已记录为 `source_unavailable`，没有变成 `no_competition`。
- 华中农业大学、武汉理工大学均有 403 记录，状态仍保留为 `completed_with_gaps`。
- 武汉理工大学主入口和 known-path 均未成功获得可解析官方页面，因此 fallback 尚未真正召回内容。

## 13. 是否达到三校门槛

未达到：

- Page Recall 58.3% < 70%
- Candidate Recall 54.5% < 70%
- Lead Precision 50.0% < 70%

因此不进入 15 校 Acceptance。

## 14. 是否进入 15 校 Acceptance

否。下一步应继续修三校 discovery 的最大损失层。

最大损失层不是 Competition Match / Relation / Deadline，而是：

1. 华中农业大学市场调查与“四新”页面未进入 candidate URL。
2. 武汉理工大学 403 后的多入口、学院页和 PDF 降级仍不闭环。

因此应优先：

- 增强官网内文 URL 候选提取与分页/栏目命中，而不是继续堆关键词。
- 修复 403 后多子站/学院/PDF fallback，保证武汉理工大学能从非主入口找到官方页面。

