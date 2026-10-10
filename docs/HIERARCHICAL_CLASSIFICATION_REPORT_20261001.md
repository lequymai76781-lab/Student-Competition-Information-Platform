# 两级文档分类与 Policy 安全判定报告

日期：2026-10-01。固定数据集 golden-20261001-v1，复用原有 100 条真实人工标签；未重新抽样、未改标签、未新增赛事或高校。

**HIERARCHICAL_CLASSIFICATION = BLOCKED**

两级分类、独立 Policy 判定、审核解耦、中文界面与测试已实现；实际质量验收仍未满足全部条件。Policy 误报从 8 降至 0，代价是召回只剩 1/14；没有可认证的正式关系自动阈值，也没有真实 information 安全移出样本。不能把技术验证通过写成全面自动化通过。

| 序号 | 报告项目 | 最终结果 |
| --- | --- | --- |
| 1 | 原 20 类指标 | 冻结 43% accuracy / 30.00% macro F1；上一轮修复后 55% / 37.96%，完整对比见下表。 |
| 2 | 新 7 类指标 | 100 条固定真人标签；accuracy 68%，macro P 74.07%、R 65.88%、F1 61.97%，weighted F1 67.43%。 |
| 3 | Accuracy 对比 | 55%→68%；但仅合并类别已达 71%，新安全规则相对机械合并为 −3pp。 |
| 4 | Macro F1 对比 | 37.96%→61.97%；仅合并类别为 66.83%。类别数不同，不等于泛化提升。 |
| 5 | Weighted F1 对比 | 54.43%→67.43%；仅合并为 71.83%。 |
| 6 | 一级 confusion matrix | 下文完整 7×7；总数 100，对角线 68。 |
| 7 | 各一级 precision | 完整七类表见下，含 support、预测分母与 TP。 |
| 8 | 各一级 recall | 完整七类表见下。 |
| 9 | 各一级 F1 | 完整七类表见下。 |
| 10 | Policy precision | 1/1=100%，预测阳性仅 n=1；95% Wilson 区间 20.65%–100%。 |
| 11 | Policy recall | 1/14=7.14%；不把低召回掩盖为完全成功。 |
| 12 | Policy false positive | 8/86→0/86；只是在固定开发样本中观测到零错误。 |
| 13 | Policy false negative | 13/14，其中政策线索保留人工，不产生正式关系。 |
| 14 | Policy 安全阈值 | 独立语义判定门 .90；已验证的正式 AUTO_POLICY_MATCH 安全阈值=None，关系自动权限关闭。 |
| 15 | update 漏判 | 主/次真人更新 4 条，识别 3，漏判 1；进入 information 0。漏判来源缺少可用正文且标题为待复核占位，保持 other 人审。 |
| 16 | informational_only 准确性 | 实际移出 0，精度 N/A；预测 information 14 条，其中 3 条类别错置，14 条事实安全专项均未答，不能认证安全降噪。 |
| 17 | AUTO 一级分类比例 | 100 条标签 36%；200 来源 31.50%；254 候选 77/254=30.31%。均只开放 participation。 |
| 18 | QUICK_CONFIRM 比例 | 100 条标签 24%；200 来源 13.50%；254 候选 34/254=13.39%。 |
| 19 | MANUAL 比例 | 100 条标签 40%；200 来源 55%；254 候选 143/254=56.30%。 |
| 20 | 分类人工任务减少 | 机器分类减量 77/254=30.31%；复用已完成人标后剩 110 条，综合覆盖 56.69%，不等于机器收益或耗时减少。 |
| 21 | 59 条关系重分级 | SAFE_AUTO=0，QUICK_CONFIRM=59，MANUAL=0。保留 relation:379 已有人工答案；未写原库。 |
| 22 | 样本特判 | 无来源 ID、学校或整条样本标题特判；静态检查新生产分类模块无 100 个 source_id 字面值，通用词/正则不等于样本例外。 |
| 23 | bootstrap / 限制 | 配对 source bootstrap，n=100、2000 次、seed=20261001。相对机械合并 accuracy 差 −3pp，95% CI [−12,+6]pp；不是独立留出验证。 |
| 24 | 修改文件 | 设计/计划、分类与安全模块、服务接入、评估脚本、中文前端和测试；完整清单见下。 |
| 25 | 新增测试 | 后端新增 116=89 分类 +14 指标 +13 集成；前端新增 7。先 RED 后 GREEN；功能夹具不计入真人指标。 |
| 26 | 后端测试 | 最终 1149 passed in 57.41s，退出码 0。 |
| 27 | 前端测试 | 84 passed；lint、typecheck、隔离 build 均退出码 0。 |
| 28 | 浏览器验证 | 真实 Edge + 本地真实 API 的 7 个场景通过，无 pageerror；仅本轮独立功能测试库。 |
| 29 | 正式数据库 SHA256 | 9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320；前后相同，其他 10 个保护输入也未变。 |
| 30 | 下一阶段建议 | 不扩量、不重标这 100 条；先澄清现有语义争议与正文证据缺口，保持关系/信息移出关闭，可进行隔离人工审核计时。 |

## 两级分类与映射

| 一级类型 | 原人工细类（保留不改） | 二级语义 |
| --- | --- | --- |
| participation | registration_notice / organization_notice / selection_notice / recommendation_notice | registration / organization / selection / recommendation |
| result | result_notice / publicity_notice | result / award / publicity / recommendation_result |
| information | completion_news / competition_intro / event_news / historical_material | completion / intro / news / history |
| policy | policy_recognition_document / award_policy_document / postgraduate_policy_document / comprehensive_evaluation_policy_document / innovation_credit_policy_document | recognition / award / postgraduate / comprehensive_evaluation / innovation_credit |
| update | deadline_extension / correction_notice / rule_update | deadline_extension / correction / rule_update |
| repost | repost | repost + referenced_primary_type |
| other | other | other |

一级字段 primary_type 固定七类；document_type 保留细类语义供兼容和追溯，secondary_type 提供规范二级标签，secondary_types 保留多标签。人工 ground truth 按上述固定映射得到一级，不重新解释人工备注，不把次标签当主标签替换。原 human_primary_type 及 human_secondary_types 完整保存在只读评估记录中。

明确转载保留 referenced_primary_type，但不当作原始官方证据。other 不强猜。update、正文实际变更、旧层已有 HIGH_RISK 或来源冲突均不得被一级转换降为普通信息。正文中英文延期、更正、规则更新、包装式转载前缀均有独立回归。

已确认的人工细标签可兼容映射新一级；重新计算安全属性，不信任旧 informational_only 缓存。更正 API 兼容七类与旧细类；只更正一级时不强制生成一个虚假的二级细类。

## 同一批样本的四组指标

| 模型/口径 | n | Accuracy | Macro P | Macro R | Macro F1 | Weighted F1 |
| --- | --- | --- | --- | --- | --- | --- |
| 原冻结 20 类 | 100 | 43.00% | 33.02% | 36.33% | 30.00% | 43.27% |
| 上一轮修复后 20 类 | 100 | 55.00% | 40.03% | 45.47% | 37.96% | 54.43% |
| 仅映射旧结果为 7 类 | 100 | 71.00% | 66.94% | 69.01% | 66.83% | 71.83% |
| 新两级分类 + Policy 安全门 | 100 | 68.00% | 74.07% | 65.88% | 61.97% | 67.43% |

20 类 macro 固定分母 20，七类 macro 固定分母 7；未定义项按 0。每项指标均基于人工主类，weighted F1 按 support 加权。七类合并使部分旧细类混淆不再算一级错误，故跨 20/7 的提升不能直接解释为模型更会泛化。

关键分解：55%→71% 的 +16pp 来自类别合并；71%→68% 的 −3pp 是新增语义/安全规则相对“仅合并”的净变化。相对机械合并有 9 条由错变对、12 条由对变错，主要交换是消除非政策误报并把证据不足的真实政策转为 other 人工确认。源 ID 和原文在 changes_from_mechanical_merge 与 misclassifications.json 中逐条列出。

## 各一级类别与完整矩阵

| 一级类别 | support | 预测 n | TP | precision | recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| 参赛相关 / participation | 45 | 37 | 36 | 97.30% | 80.00% | 87.80% |
| 结果/公示 / result | 5 | 6 | 2 | 33.33% | 40.00% | 36.36% |
| 赛事信息 / information | 15 | 14 | 11 | 78.57% | 73.33% | 75.86% |
| 政策/认定 / policy | 14 | 1 | 1 | 100.00% | 7.14% | 13.33% |
| 更新/更正 / update | 4 | 3 | 3 | 100.00% | 75.00% | 85.71% |
| 转发 / repost | 3 | 4 | 3 | 75.00% | 100.00% | 85.71% |
| 其他 / other | 14 | 35 | 12 | 34.29% | 85.71% | 48.98% |

| 人工真实 \ 机器预测 | 参赛相关 | 结果/公示 | 赛事信息 | 政策/认定 | 更新/更正 | 转发 | 其他 | support |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 参赛相关 | 36 | 2 | 1 | 0 | 0 | 1 | 5 | 45 |
| 结果/公示 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 5 |
| 赛事信息 | 0 | 1 | 11 | 0 | 0 | 0 | 3 | 15 |
| 政策/认定 | 0 | 1 | 0 | 1 | 0 | 0 | 12 | 14 |
| 更新/更正 | 0 | 0 | 0 | 0 | 3 | 0 | 1 | 4 |
| 转发 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 3 |
| 其他 | 0 | 0 | 2 | 0 | 0 | 0 | 12 | 14 |

常见同一级细类混淆已降为描述性差异；registration/organization/selection 不要求管理员反复选择。result、公示与推荐/奖励政策之间仍存在功能定义冲突，不能靠合并消除。保留原人工主标签后，result 精确率仅 2/6，暂不能安全开放该一级所有高分预测。

## Policy 独立二分类与阈值

独立判定器消费 title、publisher、section、content_preview/content_text/body、attachment_titles。需要规范政策词和正文规范条款或结构化赛事目录等正向证据，并核对赛事业务相关性；发布机构、栏目或标题政策词单独出现不足以确认。明确报名、结果、公示、报道或转载的页面受到负向约束，附件政策不自动变成父页面政策。

输出 is_policy、policy_confidence、policy_reason、policy_status、正/负证据列表。证据不足进入 NEEDS_POLICY_CONFIRM 或 NON_POLICY。规则评分表达证据强弱，不是正确概率。

| 独立 policy 阈值 | 判为 POLICY n | TP | FP | FN | TN | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.70 | 1 | 1 | 0 | 13 | 86 | 100.00% | 7.14% |
| 0.75 | 1 | 1 | 0 | 13 | 86 | 100.00% | 7.14% |
| 0.80 | 1 | 1 | 0 | 13 | 86 | 100.00% | 7.14% |
| 0.85 | 1 | 1 | 0 | 13 | 86 | 100.00% | 7.14% |
| 0.90 | 1 | 1 | 0 | 13 | 86 | 100.00% | 7.14% |
| 0.95 | 0 | 0 | 0 | 14 | 86 | N/A | 0.00% |

独立判定门为 0.90，与普通一级分类阈值分开。0.70–0.90 得到同一组阳性；0.95 没有阳性，precision=N/A，不能说“更高阈值达到 100% 安全”。

最终 TP=1、FP=0、FN=13、TN=86；precision=1/1，recall=1/14。唯一真人政策命中 source_id=7d1a7424a7bf3483。预测阳性精确率的 Wilson 95% 区间为 20.65%–100%，99% 为 13.10%–100%。这不足以支持正式 AUTO_POLICY_MATCH；已认证的正式关系安全阈值仍为 None，自动权限保持关闭。

原有八个非政策误报均被保守退回：

| source_id | 标题 | 原人工细类 | 新一级 | Policy 判定状态 |
| --- | --- | --- | --- | --- |
| 0d2368777f63d683 | 关于公布《南京邮电大学大学生创新创业竞赛项目认定及分类目录（修订）》的通知（校教发〔2025〕1号） | other | other | NON_POLICY |
| 40a271029fe332cc | 物理与电信工程学院本科生学科竞赛级别认定表 | other | other | NEEDS_POLICY_CONFIRM |
| 4190c6133726dffa | 江苏大学学生学科竞赛管理办法（江大校〔2019〕91号） | other | other | NEEDS_POLICY_CONFIRM |
| 6b69006386c3f53e | 国际教育学院推荐2027届优秀应届本科毕业生免试攻读硕士研究生工作实施细则 | other | other | NEEDS_POLICY_CONFIRM |
| a03133fb85c1bdb2 | 南京航空航天大学大学生竞赛级别认定表（2024年度） | other | other | NON_POLICY |
| ab018c808e5da3b4 | 泉州师范学院学科专业技能竞赛管理办法（PDF发现） | other | other | NEEDS_POLICY_CONFIRM |
| c5598f6ae72d68be | 外国语学院本科人才培养方案（创新实践学分竞赛项目） | other | other | NEEDS_POLICY_CONFIRM |
| df23f13bf9dcfe80 | 泉州师范学院关于印发《泉州师范学院大学生学科专业竞赛管理办法》的通知 | other | other | NEEDS_POLICY_CONFIRM |

固定 86 条真人非政策上，误报率由 9.30% 降为 0%。配对错误比较为改善 8、恶化 0，名义双侧精确检验 p=0.0078125；同一开发集已用于改规则和选择权限，不能把该探索性显著性当作独立生产验证。没有更改 other 标签来提高分数。

## 一级阈值与最终权限

下面是假设仅按一级 confidence≥阈值自动处理的诊断回放，没有套实际风险/权限门，也没有执行任何自动决定：

| 规则阈值 | 假设 AUTO n/100 | 正确 n | 正确率 | 留人 n | Policy FP | update 全量漏判 | 自动集漏判 update | information 错放 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.70 | 65 | 56 | 86.15% | 35 | 0 | 1 | 0 | 3 |
| 0.75 | 65 | 56 | 86.15% | 35 | 0 | 1 | 0 | 3 |
| 0.80 | 65 | 56 | 86.15% | 35 | 0 | 1 | 0 | 3 |
| 0.85 | 63 | 56 | 88.89% | 37 | 0 | 1 | 0 | 3 |
| 0.90 | 63 | 56 | 88.89% | 37 | 0 | 1 | 0 | 3 |
| 0.95 | 5 | 2 | 40.00% | 95 | 0 | 1 | 0 | 0 |

表中“自动集漏判 update=0”不表示整体无漏判；全体真人更新 4 条仍漏 1 条，该条分数 0.35、留在人工组。假设表中的 update 高分通过只是数字切片，实际 update 永远保持高风险字段复核。

| 一级类别 | AUTO 阈值 | 254 条 AUTO n | 规则/证据边界 |
| --- | --- | --- | --- |
| 参赛相关 | 0.9 | 77 | 仅清晰参赛功能、无跨一级歧义和高风险；仅免类型选择 |
| 结果/公示 | None / 关闭 | 0 | 机制保留，当前真实证据不足以放行；二级差异不要求单独判断 |
| 赛事信息 | None / 关闭 | 0 | 机制保留，当前真实证据不足以放行；二级差异不要求单独判断 |
| 政策/认定 | None / 关闭 | 0 | 政策分类、关系授权与名称匹配独立；正式关系 AUTO 关闭 |
| 更新/更正 | None / 关闭 | 0 | 始终高风险字段复核 |
| 转发 | None / 关闭 | 0 | 机制保留，当前真实证据不足以放行；二级差异不要求单独判断 |
| 其他 | None / 关闭 | 0 | 未知直接人工 |

只为清晰 participation 设置操作阈值 0.90；在本批相同分数段中，0.85 与 0.90 选择相同 36 条，不能认为 0.90 是精确最优或 90% 正确概率。其实际 AUTO 36/36 正确，n=36，Wilson 95% 区间 90.36%–100%，仍受开发集与选样偏差限制。只免除类型选择，不能批准任何正式字段。

result、information、repost 的路径仍支持层级分类与可选二级，当前权限因真实错误而保留确认。未因二级标签不同新增必选任务，但也未假装它们的一级自动处理已获验证。policy、update、other 的 AUTO 不开放。

## update 与 information 安全检查

真人主类/次类合计 update n=4，识别 3，漏判 1。漏判 source_id=e87a2fffc6126eed，原人工 correction_notice，次标签 rule_update，备注为“赛事的规则更新”。机器输入却只有“来源待复核·真实资料”类占位标题，无正文，无法据此推断具体更正内容。它保持 other / NEEDS_MANUAL_CLASSIFICATION，未进入 information，也未被自动批准；其机器风险仍非 HIGH_RISK，是本轮明确保留的缺口。

information 预测 14 条，类别组错置 3 条，ID 为 0c76c55062cfcc59、8f90563734b142b3、c0de2a9fd355d586。对应原人工 other、selection、other；未根据备注改标。14 条的 informational_safe 原人工专项全部未答。

实现的可移出条件还要求完整正文明确标记 content_is_complete=True、没有截断、待处理关键字段、实际 update、政策疑点、来源冲突或学校关系。这些只是功能安全门，尚无真实安全移出样本支撑开启；当前 HIERARCHICAL_INFORMATIONAL_ENABLED=False，实际 informational_only=0/100、0/200、0/254，移出精度为 N/A。

因此“update 被 information 吞掉”在本批为 0，但“所有 update 均已识别”和“information 可以安全降噪”均未被完全证明。测试中的完整正文功能夹具只证明条件分支，不计入真实分类或安全精度。

## 审核任务：分类、字段事实、政策关系各自计算

| 人口径 | 总量 | AUTO | QUICK | MANUAL | 类型仍需人工 |
| --- | --- | --- | --- | --- | --- |
| 原 100 条 Golden Set | 100 | 36 | 24 | 40 | 64 |
| 当前 200 个独立来源 | 200 | 63 | 27 | 110 | 137 |
| 当前 254 条候选 | 254 | 77 | 34 | 143 | 177 |
| 去掉已有人工标签覆盖后的 138 条候选 | 138 | 28 | 3 | 107 | 110 |

254 条候选按 AUTO participation/result/information/policy/update/repost 分别为 77/0/0/0/0/0；manual other=128。所有字段候选投影仍 pending，原队列没有被写回。上一轮 254→252 的两条信息移出不沿用，新策略为 254→254。

原 100 个已完成标签中，89 个来源映射到这 254 条候选的 116 行；其他 11 个标签来自独立政策文档等，不在此候选队列内。116 行中已有 49 行同时符合本轮 AUTO，所以人工标签额外免除的是 67 行分类，不能把 77+116 直接相加。

分类工作量的三个不同数字：

- 机器免除：77/254=30.31%；原 254 条中仍有 177 条需类型确认。
- 复用已经完成的人工标签：进一步免除 67 条，剩余 110 条分类任务（3 quick+107 manual）。
- 两者合计覆盖 144/254=56.69%，其中含用户先前劳动，不是全由机器创造的效率。

77 条自动候选只有 49 条行级关联已标注来源，其余 28 条候选不在现有真人标签覆盖中；不能把 36/36 的观察外推成全部 77 条百分之百正确。候选重复使用同一来源，因此不对 49/49 行级结果计算假独立二项区间。

仍有 164 条候选含 392 项字段提案；学校映射 49 条、标记候选 26 条（可重叠，不能相加）。本轮自动批准字段数为 0。分类任务减少不等于字段审核减少，更不能换算管理员小时吞吐；未用分类保存间隔或浏览器机器操作时间充当人工计时。

## 59 条既有政策关系重新分级

读取原隔离 policy-replay.sqlite，mode=ro、query_only=ON；不调用会写库的 analyze 路径。逐条核验新 Policy 判定、官方来源/有效期/范围门、完整正文哈希和原行、当前名称匹配与赛事状态。

SAFE_AUTO=0；QUICK_CONFIRM=59；MANUAL=0。全部来自同一政策文档 9，不能当成 59 个独立政策样本。新判定为 policy、policy_confidence=0.92（名录标题与已保存 XLS 表格结构），但正式自动权限未被验证，仍全部 quick confirm。

保留 relation:379 原有五项人工 yes，其他 58 条没有关系专项答案，共同政策文档也没有完成政策专项抽验。既有机械证据与匹配可追溯不等于政策/关系安全已获人工确认。59 个 ID 的新分级、分层阻挡理由、匹配结果和已有审计保存在 policy-relations-regraded.json。没有更新、删除原关系或正式库。

层级隔离保持：policy document → competition extraction → competition matching → relation decision。Policy 的规则分、条目抽取证据、名称匹配置信分、关系门分别保留；名称匹配的 1.0 不会替代来源、效期或政策校准。

另外修复了一个实际安全问题：独立政策判定未通过的新文档，不能凭“废止旧标题”让旧政策失效，也不能把同一操作转成冲突而间接失效。新证据只有通过 Policy 和证据门才进入版本处理；纯自动化授权暂停不会撤销已有合法历史证据。失败复现和通过回归均已保存。

## 稳定性与样本限制

固定种子 source-level paired percentile bootstrap：n=100，2000 次，seed=20261001；比较新七类与机械合并七类。下表差值以百分点理解（例如 −3.00% 为 −3pp）：

| 指标差 | 点估计 | 95% 下界 | 95% 上界 |
| --- | --- | --- | --- |
| Accuracy 差 | -3.00% | -12.00% | 6.00% |
| Macro F1 差 | -4.87% | -11.03% | 1.69% |
| Weighted F1 差 | -4.40% | -13.97% | 4.54% |

区间均不支持“新语义规则整体优于机械合并”的结论。bootstrap 只是条件于这 100 条的稳定性估计，不是 cross-validation，不消除此前已经见过全部标签的开发偏差。事后再称这批为未见过的留出集不成立。

真实标签完整 100/100，无跳过、缺主标签或 ID 重复；有 3 组同标题但来源不同，未删样本。原 20 类有 4 类没有真人主标签；映射后的七类均有 support，但 result=5、update=4、repost=3 很小。只有 11 条有冻结正文，89 条没有；上轮已识别的 7 条来源/证据质量限制继续保留。未自动纠正有争议的人工语义定义。

## 修改文件、测试与浏览器证据

| 本轮新增/修改文件 |
| --- |
| backend/app/services/document_calibration_policy.py |
| backend/app/services/document_policy_service.py |
| backend/app/services/document_taxonomy.py |
| backend/app/services/hierarchical_classification_metrics.py |
| backend/app/services/hierarchical_source_classifier.py |
| backend/app/services/policy_automation_service.py |
| backend/app/services/policy_safety_classifier.py |
| backend/scripts/evaluate_hierarchical_classification.py |
| backend/tests/test_document_policy_integration.py |
| backend/tests/test_hierarchical_classifier.py |
| backend/tests/test_hierarchical_integration.py |
| backend/tests/test_hierarchical_metrics.py |
| docs/superpowers/plans/2026-10-01-hierarchical-classification.md |
| docs/superpowers/specs/2026-10-01-hierarchical-classification-design.md |
| frontend/src/app/admin/document-policy/page.tsx |
| frontend/src/components/DocumentClassification.tsx |
| frontend/src/lib/document-policy-api.ts |
| frontend/tests/document-policy.test.mjs |
| frontend/tests/hierarchical-classification.test.mjs |

另生成本报告、矩阵附录、CURRENT_TASK 更新及忽略目录中的离线证据。没有依赖安装、schema 迁移、生产部署、push/merge、新采集或数据扩量。

后端新增 116 项测试：89 项两级分类/政策/变更/转载边界，14 项指标/分母/bootstrap，13 项服务集成/权限/人工标签兼容/政策版本保护。最终 1149 passed in 57.41s，退出码 0。先 RED 后 GREEN 的日志保留；旧证据门及信息归档机制测试在局部夹具中显式注入“假设已验证权限”，真实默认权限由独立测试覆盖，不能混作生产质量证明。

前端新增 7 项，全部前端测试 84 passed；lint、typecheck、build 均退出码 0。隔离构建最初缺少目录外已存在的学校种子 JSON，原样复制到构建副本后通过，未新增或更改学校数据。构建的三个实现文件与工作区源码逐字节一致。

真实 Microsoft Edge + 本地真实 API 浏览器验证 7/7：自动参赛一级无必选细类；待审字段保留；update 高风险；信息移出暂停；七类中文可选更正及原因必填；政策分类/抽取/匹配/关系分层且自动关系 0；界面无一级/状态英文枚举外露。初次浏览器检查的 main 定位匹配两个元素，修正测试定位后重跑；未因此改动业务行为。截图检查还修正旧细类“需确认主类型”与一级已自动确定的文案冲突，增加失败/通过回归，再跑完整后端与浏览器。

浏览器仅使用本轮 browser.sqlite 功能夹具，机器更正操作不计真人样本。数据库检查：所有六条字段候选仍 pending，两赛事 frequency 未改，正式认可关系 0，无事实自动批准。截图在 browser-evidence/，结果 browser-results.json，库检查 browser-database-check.json。

本轮仅启动独立 8055 API 与 3055 前端验证服务；使用最终本地代码。既有真人标注和其他服务未替换、未部署。该预览含明确功能夹具，不作为真实审核实验队列。

## 正式库和原始输入保护

| 保护输入 | 操作前/后相同 SHA256 |
| --- | --- |
| data/v02.sqlite | 9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320 |
| .codex-qa/mid-scale/candidates.sqlite | 6bffca4c20f6aaa673246cc1768913cedab789fbd30d4364e0a1f4e64f4a95b6 |
| .codex-qa/golden-set-20261001/live/annotations.sqlite | c6b80072d60c28b0d1f48342c745457ffc9c855c28c12c99628edb3d36ac7f80 |
| .codex-qa/golden-set-20261001/live/manifest.json | 936cc8c9663e151350d2c678ee1bb952fa017e4f4454ea98d3a67e4a6095e9fb |
| .codex-qa/document-policy/replay-verified/golden-to-label.csv | afe2bbb560f90616038e661a92962cdd51476ad8f5311636fbb1414893c9864c |
| .codex-qa/document-policy/replay-verified/source-replay.json | db74a78394ab1ea2726acf80b3b456bb6f572c3b132ae7dae6953b29f4b5950c |
| .codex-qa/document-policy/replay-verified/policy-replay.json | e14365dae3621df20a1e0b9bc4cf071d8c861c41df3fd733eb343146e9657295 |
| .codex-qa/document-policy/replay-verified/replay.sqlite | 406b367e287189c0134dfa155aead48604800d46d5e00433d51c81f2575565b5 |
| .codex-qa/document-policy/replay-verified/policy-replay.sqlite | 070b3f600fe7ee76552001316eb760e1b39ace8356c63f6ac529b8fd0a4fe2ba |
| .codex-qa/golden-calibration-20261001/human-snapshot.json | 15691f0cf402bb620d76b4821aafb3d8b85aa0d3280a63486a3cd58c2eef49f9 |
| .codex-qa/golden-calibration-20261001/calibration-results.json | 7b0a1d51dc5b118c96f55285762efa810187de7c5d77bd0fdf579d93c9dfebe6 |

全部 11 个保护文件哈希一致，包括正式库、候选库、真人标签库、固定 manifest、上轮隔离库及原始指标。新真实指标仅写 .codex-qa/hierarchical-classification-20261001/；原 100 条人工决定完整保留。

主要证据：

- evaluation-results.json：四组指标、七类矩阵、独立阈值、bootstrap、队列分母、代码与输入哈希。
- golden100-records.json：原细标签/次标签、新一级、Policy 独立结果及逐条原人工记录。
- source200-replay.json / candidate254-replay.json：完整离线来源/候选重放。
- policy-relations-regraded.json：全部 59 条原关系只读重新分级。
- [完整一级矩阵与逐类阈值附录](HIERARCHICAL_CLASSIFICATION_MATRIX_20261001.md)。
- backend-final-after-explanation.log、frontend-tests.log、frontend-lint.log、frontend-typecheck.log、frontend-build.log、browser-results.json。
- before.json / final-checks.json：哈希、实际变更清单与最终验证摘要。

在 backend 目录运行 .\venv\Scripts\python.exe -m scripts.evaluate_hierarchical_classification 可复现实验指标；运行 .\venv\Scripts\python.exe ..\.codex-qa\hierarchical-classification-20261001\reevaluate-policy-relations.py 可重分级 59 条关系，两个脚本都不写原数据库。

## 完成标准与下一阶段

| 验收点 | 判定 |
| --- | --- |
| 一级明显优于旧 20 类 | 数字 55%→68%，但仅合并已达 71%；不能证明规则泛化提升。 |
| Policy false positive 显著下降 | 本开发集 8→0；n=1 阳性、召回 7.14%，不足以支持正式自动关系。 |
| update 不被 information 吞掉 | 本批吞入数 0；仍有 1/4 更新因输入缺失而漏判，保留人工。 |
| information 可以安全降噪 | 未证实；真实移出 0，精度 N/A，自动移出关闭。 |
| participation/result 不因细标签差异造人工任务 | 层级和界面已实现；participation 自动启用，result 一级质量不足暂保留确认。 |
| 无样本特判 | 通用语义与结构规则；无 ID/学校特判。 |
| 分类与字段审核分离 | 测试及浏览器通过，事实自动批准 0。 |
| Policy 分类与赛事匹配分离 | 独立判定、抽取、匹配与关系安全门；59 条不写库。 |
| 真实 100 条重放 | 完成，原标签不改。 |
| 新一级矩阵 | 完整生成并核验总数 100。 |

下一阶段不扩大数据规模，也不重新标这 100 条。优先使用现有争议记录澄清“文件功能”和“业务相关性”的区别，并补足已有来源的可核验证据与政策专项审核；在本轮约束下未做新抓取。可继续隔离人工审核吞吐基线实验，只测真实打开来源、判断和提交的时间，不把本次分类减量直接换算工时。

本轮停在已实现的安全边界和真实报告。自动信息移出、result/repost 一级自动权限、正式政策关系自动权限不因测试通过而开启。

**HIERARCHICAL_CLASSIFICATION = BLOCKED**
