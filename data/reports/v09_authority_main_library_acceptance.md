# V1 全国大学生竞赛权威主库 — 验收记录

- 生成时间：2026-09-04T14:56:22.435027+00:00
- 模式：apply（已写库）

## A. 权威来源接入结果

- 注册表条目：4（教育部2、高教学会1、数模组委会1）
- 成功匹配赛事：3
- 新增 S 级来源：1（2025 教育部文件；2026 文件沿用既有来源行）
- 新增 A 级来源：0（高教学会官方附件不可机读，未伪造）
- 本次运行来源已存在（幂等去重）：3
- 冲突（累计记录、未静默覆盖）：2
- 本次待人工审核/发现：1

### 教育部 / 中央部门
- 教高函〔2025〕7号（2025届）与教高函〔2026〕26号（2026届）均为真实教育部文件；本轮将2025文件新增为 S 级来源并建立2025官方届次，2026文件补全届次字段。
### 中国高等教育学会
- A 级官方发布页《2022全国普通高校大学生竞赛分析报告》已注册（registry + Organization 入库）。
- 公开正文未逐项列出竞赛目录附件名单，故**不伪造**逐赛 A 绑定；待官方附件（PDF/Excel）可机读后由同一管线继续绑定（见 E）。
### 赛事官方来源
- 全国大学生数学建模竞赛 2026 第一次通知（组委会发布于中国大学生在线）作为同文不同域名证据完成届次时间核验，未新增重复来源行；
- 全国大学生数学竞赛第18届官方通知绑定2026届次；中国国际大学生创新大赛 2026 官方通知绑定2026届次。

## B. 状态变化

### competitions
| 状态 | 变化 |
| --- | --- |
| suspected | +7 |
| pending_verification | -7 |

### editions
| 状态 | 变化 |
| --- | --- |
| verified_official | +3 |
| school_confirmed | -2 |

- 赛事级 pending_verification：89 → 82（差额 7 项为实体类型非 competition 的对象按规则转 suspected，实体保留、未删除）
- 赛事级 verified_official：10（未伪升级）
- 非 competition 对象：7 项（award/festival/exhibition/unknown，is_competition=0，保留不展示）
- 本次重跑幂等性：状态增量 0 / 新增 0（见下方“本次运行”）。

## C. 来源覆盖

- 拥有 S 级来源的赛事：10
- 拥有 A 级来源的赛事：0
- 同时拥有 S+A/官方来源的赛事：0（暂无真实 A 绑定）
- 仅高校来源支撑的赛事：118
- 完全没有来源的赛事：12

## D. 匹配质量

- 自动匹配：3（教育部2025/2026、数模2026，confidence=1.0）
- 人工审核/发现：1（高教学会页无逐项名单）
- duplicate：来源 URL 去重（本次运行 3）；重复实体组 1（全国大学生生命科学竞赛 id 53/102，供人工确认）
- 冲突：2（数模2026届旧日期 vs 官方第一次通知，未静默覆盖，已由届次修复显式修正并留 revision）
- 低置信匹配：0（低分一律不自动绑定）

## E. 待处理问题

- 仍无 S/A 来源的赛事：82 项（完整矩阵见 v09_pending_verification_matrix.json）
- 仅高校来源：118 项；无来源：12 项
- 高校截止仍占用全国字段、待人工复核：2 个届次（comp109 ed23、comp137 ed22；未删除，保留待 S/A 届次证据）
- 校内截止晚于所谓全国截止：1 条（comp137，值均来自高校，需主办方确认）
- S 来源质量待复核：comp138（hc-cdn 回顾资料 PDF）、comp143（高校域官网）、comp107/108（来源 URL 为2023指南页，届次待复核）。
- 高教学会逐赛 A 绑定：0（官方附件名单暂不可机读；组织机构与注册表已接入，后续按同一管线绑定）。
- 同一赛事多个官方 URL（均为有效证据，无需去重）：2（comp1 2025/2026 两个年度文件、comp4 官网+通知）。

## 验收标准对照

1. 可重复运行的 authority pipeline：✅ `backend/scripts/run_authority_sync.py --dry-run|--apply`（幂等：重复运行新增为 0，见测试）。
2. 教育部/中央部门来源真实接入：✅ 2025/2026 教育部文件已绑定并建立/补全届次。
3. 中国高等教育学会来源真实接入：⚠️ 注册表+组织+解析管线已接入；逐赛 A 绑定 0（官方附件不可机读，未伪造，列入 E）。
4. 官方赛事来源开始绑定：✅ comp1/comp4/comp99 届次与官方来源绑定。
5. pending 重新核验：✅ 89 → 82（另 7 项按实体类型转 suspected），逐项矩阵已生成，无强制升级。
6. university source 不能晋升 official：✅ 代码规则 + refresh 复核 + 测试，审计违规 0。
7. Competition 与 CompetitionEdition 分别核验：✅ 届次须有自己的 S/A 来源（本次 +3 官方届次即由届次级来源促成）。
8. source provenance 可追踪：✅ CompetitionSource/FactSource + 19 条 revision（old/new/source URL 齐备）。
9. 高校截止不污染全国截止：✅ 5 个届次清理 + 字段级 can_prove 规则 + 测试；2 个届次列入人工复核（保留原值）。
10. 测试：见测试报告（backend pytest、authority pipeline 测试、API smoke、frontend typecheck）。
11. 未删除旧数据：✅ competitions 143、school_competitions 172、75 通知、102 目录关系原样保留；备份已生成。
12. 未伪造权威来源：✅ 仅绑定 3 份真实抓取/既有文件；高教学会无逐项名单时不伪造 A 绑定。

## 清理修复（全部带 revision）

- 官方来源链接到届次：3（comp1-2025/2026、comp99-2026）
- 校内截止误写全国字段修复：5 个届次（值保留在学校关系层）
- edition.source_url 修正为官方 URL：5 个届次
- 新增官方届次：1（中国国际大学生创新大赛2025）
- fact_source 行净增：17；fact_revision 净增：19
- 组织机构新增：1（中国高等教育学会）

## 审计摘要

- 赛事总数：143；届次总数：54
- 数据净变化：赛事 0、届次 1、来源 1、school_competitions 0、通知关系/目录关系 0（未删除）
- verified_official 无来源：0
- 仅高校来源却 verified_official：0
- orphan SchoolCompetition：0；届次/赛事错位：0
- 届次早于创办年份：0；官方截止晚于开赛：0

## 数据保护

- 未删除任何 Competition / CompetitionEdition / SchoolCompetition / 通知 / 来源行。
- 所有字段变更写入 competition_fact_revisions。
- 备份：{'source': 'D:\\Python\\xuesheng\\data\\v02.sqlite', 'backup_file': 'D:\\Python\\xuesheng\\data\\backups\\backup-authority-main-library-20260904-225622.sqlite', 'size_bytes': 6279168, 'created_at': '2026-09-04T22:56:22.469627'}

## 本次运行（幂等性验证）

- 新增 S 来源：0；新增届次：0；字段变更：0
- 清理变更：来源链接 0、截止清理 0、URL 官方化 0、届次修复 0。
