# V0.8.1 验收报告：211赛事雷达修复与Discovery召回率提升

生成时间：2026-09-02

## 一、V0.8 为什么只有 1 条 Lead（根因）

- V0.8 的官网发现通道几乎完全依赖搜狗（sogou.com）的 `site:` 检索，运行时段搜狗持续返回 **HTTP 403**。
- 50 所 partial 学校中 **49 所的原因都是“搜狗检索 HTTP 403”**（未拿到任何官方 URL），剩余 1 所（北京工业大学）拿到结果但页面抓取失败。
- 另外 22 所被旧逻辑标为 completed 的学校实际 **0 Lead**：旧逻辑把“检索返回 0 且无报错”直接当作 completed。
- 因此“匹配已有 Competition = 0”是**发现层断流**的结果，不是 Normalization/Alias 匹配失效。
- 补充验证：本轮运行中 Bing 长期返回无关结果、Baidu 出验证码、360 在批量请求后触发限流——单一依赖任何一家公开搜索引擎都不可靠。

V0.8 partial 原因分类统计（50 所）：

| 分类 | 数量 |
| --- | --- |
| SEARCH_ENDPOINT_403（搜狗 site: 检索 403） | 49 |
| NAVIGATION_FAILED（官网结果抓取失败/跳出官方域名） | 1 |

## 二、V0.8.1 做了什么

1. 多通道 Discovery：Sitemap、部门栏目（教务处/本科生院/团委/创新创业学院/学生工作部/学院）、导航链接、公开搜索引擎（360/DuckDuckGo/Bing 多引擎+熔断）、公众号公开线索、已知赛事反向匹配。
2. 部门栏目抓取优先，不再把站内搜索当唯一通道；搜索失败自动降级。
3. 新状态体系：`completed` / `completed_with_gaps` / `partial` / `failed` / `blocked`；`completed` 需至少 2 种通道成功或完整部门栏目扫描。
4. 新增逐校指标：`methods_attempted`、`methods_successful`、`pages_examined`、`candidate_articles`、`examined_pages`（含被过滤原因，便于分类器审计）。
5. 发布年份与赛事年份分离（`published_at` vs `possible_year`/Edition year），近期窗口 2025-09 起，不因 2025 年发布误杀 2026 赛事。
6. 修复 robots.txt 误判（robots.txt 不可用时按 RFC 允许访问，显式 Disallow 仍遵守），修复 360 跳转 URL 污染。
7. 标题级赛事匹配 + 高频赛事签名匹配（挑战杯/中国国际大学生创新大赛/数学建模/电子设计/大广赛/外教社杯等），避免正文侧栏污染造成的错误匹配。
8. 过滤教师教学竞赛、招生/调剂/博士报名、PDF/目录/栏目页等噪声。
9. 单校子进程隔离 + 超时保护：个别站点卡死不再拖垮整批。

## 三、50 所 partial 重跑结果

原 Partial：50 → 修复后：

| 状态 | 学校数 |
| --- | --- |
| completed | 0（本轮无新增硬 completed，因为外部搜索引擎在批量时段被限流） |
| completed_with_gaps | 48 |
| partial | 2 |
| failed / blocked | 0 |

> completed_with_gaps 的含义：部门栏目/导航等通道已成功执行并产出内容，但外部检索或公众号通道失败/受限。48 所中有 38 所实际产出了 Lead。

### 发现指标（50 所学校，本轮）

| 指标 | V0.8（73 校总计） | V0.8.1（50 校） |
| --- | --- | --- |
| Lead | 1 | 294 |
| 匹配已有 Competition 的 Lead | 0 | 100 |
| 新增 UniversityCompetitionEditionRelation | 0 | 56 |
| 校内 Deadline | 0 | 29 |
| 新增真实 Competition | - | 0（本轮不以新增赛事为目标，全部复用已有 143 个赛事） |
| 检查页面数 pages_examined | 低 | 1,494 |
| 候选文章 candidate_articles | 0 | 409 |

### 数据库增量（导入后）

| 表 | V0.8 前 | V0.8.1 后 |
| --- | --- | --- |
| CompetitionLead | 201 | 491 |
| CompetitionEdition | 32 | 53 |
| UniversityCompetitionEditionRelation | 43 | 99 |
| CompetitionSource | ~180 | 236 |

211 范围 Lead：291 条，其中 **100 条已匹配已有 Competition**（V0.8 为 0）。

### 通道成功数（50 校，methods_successful）

| 通道 | 成功学校数 |
| --- | --- |
| Navigation（导航发现） | 48 |
| Department Feed（部门栏目） | 43 |
| Reverse Match（反向匹配） | 5 |
| External Search（外部检索） | 1 |
| Sitemap | 0 |
| WeChat | 0 |
| Site Search | 0 |

> 批量运行时段 360 触发安全验证、DuckDuckGo 超时、搜狗 403，因此外部检索/公众号通道在本次批量中基本不可用；验证过：搜索引擎可用时段（当日早些时候）南航单校即可从外部检索命中 27 条官方 URL。

### 高频匹配到的已有赛事

中国国际大学生创新大赛(21)、“挑战杯”中国大学生创业计划竞赛(13)、外研社·国才杯“理解当代中国”全国大学生外语能力大赛(9)、中华经典诵写讲大赛(6)、全国大学生数学建模竞赛(5)、全国大学生英语竞赛(4)、全国大学生电子设计竞赛(3)、全国大学生物理实验竞赛(3) 等。

## 四、仍为 partial 的 2 所（本轮）

| 学校 | 原因 |
| --- | --- |
| 武汉理工大学 | 官网 HTTP 403（站点级拦截），且外部检索被限流 |
| 南京师范大学 | 官网 HTTP 412（站点级拦截），且外部检索被限流 |

两校均按要求记录了 blocked_method，未绕过反爬；后续可等站点/搜索引擎可用时复跑或人工核验。

## 五、5 校人工对照（Discovery Recall 抽样）

人工“已知”= 通过公开搜索引擎结果标题+官方 URL 直接确认的近期（2025-09 及以后/2026）赛事通知。

| 学校 | 人工已知 | Crawler（最终代码，引擎受限时段） | 说明 |
| --- | --- | --- | --- |
| 北京交通大学 | ≥8（数学建模/数学/电子设计 2026 校赛通知、市场调查/跨文化/Model APEC/词达人杯/书画大赛校级选拔公示、交通科技大赛报名等） | 2 Lead / 1 匹配 | 搜索受限时仅部门栏目通道产出；跨文化大赛现可签名匹配 |
| 北京科技大学 | ≥5（挑战杯“挑战计划”征集、2026 计算机设计大赛专项、2026 华北五省计算机应用比赛、挑战杯获奖新闻等） | 1 Lead | 同上，外部检索被限流 |
| 南京航空航天大学 | ≥9（2026 大学生创新大赛暨国创大赛校内选拔、红旅赛道选拔、电子电路设计竞赛、科普微视频/新域新质/研究生创新实践/华为杯等） | 0 Lead（引擎受限时段）；引擎可用时段 12 Lead | 南航大量通知页为站点列表结构，依赖外部检索定位文章 |
| 武汉理工大学 | 无法人工确认（官网 403） | 0（官网 HTTP 403） | 站点级反爬，非 Pipeline 失败 |
| 西南交通大学 | ≥8（国创大赛 2026 校内选拔、挑战杯 2026 创业计划院赛、生命科学竞赛、好创意第 20 届、移动应用创新赛、机械创新校赛等） | 34 Lead / 7 匹配 / 6 关系 / 10 校内截止 | 部门栏目通道表现优秀 |

结论：Crawler 的召回能力远高于 V0.8（1 条），但**公开搜索引擎当前被限流**会显著影响依赖站内列表结构的学校（如南航）；部门栏目通道稳定的学校（西南交大等）不受影响。真实 Recall 应等外部检索恢复后在多轮运行中评估，本报告如实记录两种运行环境的结果。

## 六、本阶段结论

- “目录覆盖完成但 Competition Discovery 未覆盖 211”的问题已定位并修复：根因是单一搜狗通道 403 + “返回 0 即 completed”的错误状态语义。
- 50 所 partial → 48 所完成但有缺口（其中 38 所产出 Lead）、2 所站点级拦截；0 failed/blocked。
- 匹配已有 Competition 从 0 → 100 条 Lead 匹配，新增 56 条高校关系、29 条校内截止。
- /data 页面已增加 V0.8.1 诊断区（状态、通道成功数、Lead/匹配/关系/Deadline）。

## 七、复跑方式

```powershell
cd backend
.\venv\Scripts\python.exe scripts\run_v081_211_radar_fix.py --status partial --workers 6 --school-timeout 420 --seed ..\data\seeds\v081_211_radar_fix_discovery.json
.\venv\Scripts\python.exe scripts\run_v081_211_radar_fix.py --import-only --seed ..\data\seeds\v081_211_radar_fix_discovery.json --report ..\data\reports\v081_211_radar_fix_report.json
```
