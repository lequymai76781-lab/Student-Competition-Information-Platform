# SPECIALIZED_INSTITUTIONS_COVERAGE_01

日期：2026-09-14（Asia/Shanghai）

本报告更新既有任务，不重建 Master List、taxonomy 或 baseline。Master List 的 34/34 只表示清单完整；Research Coverage 与 Verified Data Coverage 分开统计。

# 一、Research Coverage

**34 / 34（100%）**。P0 16/16、P1 18/18 均已完成第一轮 discovery 与第二轮定向复核，没有 `NOT_STARTED`，34 所均有 machine-readable 终局档案。

- 34 校档案：`data/checkpoints/specialized_institution_research_archives.json`
- 固定 Remaining 22 复核档案：`data/checkpoints/SPECIALIZED_REMAINING_22.json`
- 第二轮逐来源证据：`data/checkpoints/specialized_second_round_evidence.json`

# 二、Verified Data Coverage

**27 / 34（79.4%）**。此指标只统计已有可靠来源支撑的 Recognition、Notification、Participation 或 Professional Reference；没有为了达到 34/34 而把无充分证据的活动写入正式关系。

# 三、终局状态

- `VERIFIED_DATA`：27 所——北京体育大学、上海体育大学、武汉体育学院、成都体育学院、首都体育学院、西安体育学院、广州体育学院、天津体育学院、沈阳体育学院、山东体育学院、哈尔滨体育学院、北京舞蹈学院、中央戏剧学院、上海戏剧学院、中国戏曲学院、南京艺术学院、云南艺术学院、广西艺术学院、内蒙古艺术学院、新疆艺术学院、中国传媒大学、浙江传媒学院、山西传媒学院、河北传媒学院、四川传媒学院、四川电影电视学院、吉林动画学院。
- `VERIFIED_NO_PUBLIC_DATA`：2 所——南京体育学院、吉林体育学院。
- `ACCESS_LIMITED`：2 所——河北体育学院、南京传媒学院。
- `AMBIGUOUS`：3 所——北京电影学院、山东艺术学院、吉林艺术学院。
- `NEEDS_DEEPER_REVIEW`：0 所——无。

`VERIFIED_NO_PUBLIC_DATA` 只表示主要官网、教学部门、核心学院/实践入口、站内检索及附件区已查而暂不能安全确认；`ACCESS_LIMITED` 保留失效页、扫描附件或 JS 阻塞证据；`AMBIGUOUS` 不强建 canonical competition。

# 四、五大专业领域

| 领域 | Research | Verified | Verified No Public Data | Access Limited | Ambiguous |
|---|---:|---:|---:|---:|---:|
| 体育 | 14 / 14 | 11 / 14 | 2 | 1 | 0 |
| 舞蹈 | 9 / 9 | 7 / 9 | 0 | 0 | 2 |
| 电影 | 17 / 17 | 13 / 17 | 0 | 1 | 3 |
| 戏剧 | 16 / 16 | 13 / 16 | 0 | 1 | 2 |
| 传媒 | 10 / 10 | 9 / 10 | 0 | 1 | 0 |

院校跨领域，因此各领域目标数不可相加为 34。

# 五、数据库新增

- Competition：20（净新增；上一轮 13 个中删除 1 个无可靠详情来源项，第二轮新建 8 个）。
- Recognition：6。
- Notification：12。
- Participation：17。
- Professional Reference：22。
- 学院级关系：11；专业级关系：1。
- CompetitionSource：32。

第二轮新增或复用且核验成功的重要赛事包括：成都体育学院体育教育专业实习学生教学技能比赛、天津体育学院体育教育专业学生基本功大赛、全国大学生体育产业创新创业大赛、全国大学生市场调查与分析大赛、中国—东盟青年艺术品创作大赛、新疆艺术学院“新艺杯”专业竞赛、全国高校电子竞技解说主持大赛、川影杯“华年奖”、吉林动画学院“力行杯”创新创业大赛；另安全复用了中国数据新闻大赛、“挑战杯”等既有 canonical 项。

# 六、13 个上一轮新增赛事复核

- PASS：12（修正后全部通过）。
- 修正：12，补齐或纠正 canonical name、organizer、精确 source、event_type 及关系证据。
- 删除：1——海峡两岸大学生视听影像创新大赛；上一轮仅保留官网根页，无法恢复详情证据，已删除孤立赛事、届次与关系。

逐项记录见 `data/reports/specialized_previous_13_review.json` 与 `data/reports/specialized_reverse_audit_result.json`。

# 七、2 条 UNCERTAIN

最终结果：**2 条均为 DOWNGRADE，0 条继续 UNCERTAIN**。

- “桃李杯”：前十届可按历史届次保留 `competition`；文化和旅游部说明第 11 届起转为教育教学成果展示，2026 当前实体为 `showcase`、`is_competition=false`。官方依据：[文化和旅游部 2026 通知](https://zwgk.mct.gov.cn/zfxxgkml/kjjy/202602/t20260202_964516.html)、[历史沿革说明](https://www.mct.gov.cn/whzx/bnsj/whkjs/201707/t20170707_750907.html)。
- 齐越朗诵：2015 第 17 届有总决赛和奖项，按 `competition_festival` 保存历史届次；2026 第 28 届仅有推荐、遴选和展示，当前实体降为 `festival`、`is_competition=false`。官方依据：[2026 公告](http://boyin.cuc.edu.cn/2026/0814/c1266a273269/page.htm)、[2015 获奖报道](http://www.cuc.edu.cn/cucnews/2015/1116/c1901a163004/page.htm)。

首次不确定的原因是把历史届次语义直接外推到当前实体；现已改为“当前实体类型 + 届次级 event_type”双层记录。

# 八、人工抽检

- PASS：27。
- FAIL：0。
- UNCERTAIN：0。
- 五类样本数：{"sports": 5, "dance": 6, "film": 5, "drama": 5, "media": 6}。

每条均核对学校、赛事/活动、关系类型、scope、官方来源、event_type 与 canonical 状态。完整明细见 `data/reports/specialized_institutions_coverage_01_qa.json`。

# 九、测试

- Backend pytest：183 passed，0 failed。
- 专项 pytest：11 passed，0 failed。
- 完成审计：24 PASS，0 FAIL。
- importer 幂等：PASS；duplicate/source/event_type/relation/recognition_scope/orphan 均纳入完成审计。
- 本轮新增失败：0。

完成审计报告：`data/reports/specialized_completion_audit.json`；幂等报告：`data/reports/specialized_round2_idempotency.json`。

# 十、SPECIALIZED_INSTITUTIONS_COVERAGE_01

**COMPLETE**。

满足完成条件：34/34 Research Coverage；所有 P0/P1 有 final_status；无 `NOT_STARTED` 或 `NEEDS_DEEPER_REVIEW`；正式关系具备可靠 Source；2 条 UNCERTAIN 已降级；上一轮 13 个新增赛事已反向复核；Professional Reference 与 Recognition scope 已审计；人工抽检不少于 25 条；幂等、重复、来源、event_type、relation、recognition_scope 与 orphan 审计均无失败。
