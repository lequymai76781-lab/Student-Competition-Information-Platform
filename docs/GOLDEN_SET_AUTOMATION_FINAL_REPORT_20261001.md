# Golden Set 校准与自动化边界最终报告

日期：2026-10-01。数据集：golden-20261001-v1。使用用户已完成的原 100 条真实人工主标签，没有重新抽样、重新标注、替换标签或排除难例。

**DOCUMENT_POLICY_AUTOMATION = BLOCKED**

评估、规则修复与安全限制已完成；阻塞原因已从“没有人工样本”变为“仍有高风险政策误判、无法验证可靠的自动阈值”。修复后准确率为 55/100，尚不支持自动正式形成政策关系。本文的修复后指标是同一开发集重放，不是独立测试集结果。

## 25 项结果

| 序号 | 项目 | 结果 |
| --- | --- | --- |
| 1 | 有效人工样本数 | 100/100；跳过 0、无效/缺主标签 0；保留全部真实主标签。 |
| 2 | 各类别 support | 20 类完整表见下；16 类有真人主标签，4 类 support=0。 |
| 3 | overall accuracy | 43.00% → 55.00%（43/100 → 55/100）。 |
| 4 | macro precision | 33.02% → 40.03%。 |
| 5 | macro recall | 36.33% → 45.47%。 |
| 6 | macro F1 / weighted F1 | 30.00% → 37.96%；weighted 43.27% → 54.43%。 |
| 7 | 每类 precision / recall / F1 | 下表列出全部 20 类修复前后数值。 |
| 8 | confusion matrix | 独立附录列出修复前、修复后完整 20×20 矩阵。 |
| 9 | 最大误分类对 | 报名→组织 7；other→政策认定 6；报名→other 5；奖励政策→政策认定 4。 |
| 10 | policy 危险误判 | 非政策→政策 8/86（9.30%）；在 21 条政策预测中占 38.10%；政策子类另错 5 条。 |
| 11 | 不同阈值对比 | 0.70、0.75、0.80、0.85、0.90、0.95 全部回放，详见下表。 |
| 12 | 最终全局阈值 | None（不启用 AUTO）；尚无可靠数值阈值，不能宣称阈值校准通过。 |
| 13 | per-class threshold | 全部 20 类 None / AUTO 关闭；逐类六档证据见附录。 |
| 14 | AUTO_CLASSIFIED 比例 | 254 条候选投影 0/254=0%。 |
| 15 | QUICK_CONFIRM 比例 | 机器建议投影 91/254=35.83%；扣除已完成真人来源标签后剩 27 条。 |
| 16 | MANUAL 比例 | 机器建议投影 163/254=64.17%；扣除已完成真人来源标签后剩 111 条。 |
| 17 | informational_only 安全性 | 旧潜在错放 5/13，新潜在错放 3/13；13 条安全专项仍无答案；本地代码关闭自动移出。 |
| 18 | AUTO_POLICY_MATCH 是否保留 | 暂停正式自动形成关系；名称匹配建议仍可保留，不构成正式关系授权。 |
| 19 | 59 条自动关系处理 | 59 条策略统一 NEEDS_QUICK_CONFIRM；保留 relation:379 已有人工答案，其余 58 条未审；政策 9 未完成专项验证。原库不改写。 |
| 20 | 校准前人工分类量 | 原始候选口径 254；旧机器自动 112，旧机器留人 142=14 quick+128 manual。独立来源总数 200。 |
| 21 | 校准后人工分类量 | 纯机器规则留人 254；复用已完成真人标签覆盖 116 条候选后，剩 138=27 quick+111 manual。 |
| 22 | 人工工作量减少百分比 | 自动分类减量 0%；已有真人分类覆盖 116/254=45.67%，是已完成人工工作，不是自动化收益或耗时节省。 |
| 23 | 剩余最大风险 | 非政策高置信度误判、政策子类混淆、文档类型与业务相关性定义差异；缺正文与小样本、未独立验证。 |
| 24 | 是否继续审核吞吐实验 | 可继续人工审核基线计时，保持自动关闭；分类保存时间间隔不能冒充完整候选审核耗时。 |
| 25 | 下一阶段建议 | 优先利用现有争议样本澄清分类口径，并完成现有政策 9/关系证据核验；不要重做 100 条，不扩大采集。 |

## 样本完整性与指标口径

实际人工记录 100，全部 annotated、human provenance、human_primary_type 非空且属于 20 类；跳过 0，草稿 0，不可评分 0。每条均保留原 predicted_type/confidence，100 条保存预测与冻结 manifest 一致。单一真人账号，100 条 prediction_exposed=false，曝光事件 0。没有把测试 fixture、脚本操作或关系抽验混进分类样本。

source_id 与 source_url 均无重复；存在 3 组同标题、共 6 条来源，来源 URL 不同，未按标题粗暴去重。37 条有人工次标签，48 条有备注。仅 human_primary_type 作为 ground truth；修复前 8 个主类错误虽命中人工次标签，仍按错误统计。

| 同标题组 | source_id |
| --- | --- |
| 竞赛简介 | 0c76c55062cfcc59, c39c002dd92148bd |
| 教育部关于举办中国国际大学生创新大赛（2024）的通知 | 833b1daacbf1aae0, cd825c5c6264530f |
| 教育部关于举办中国国际大学生创新大赛（2025）的通知 | 24735c6e914be547, a68e4f115027022a |

有效可评分不等于覆盖充足：只覆盖 16/20 个主类；recommendation_notice、innovation_credit_policy_document、rule_update、historical_material 的 support 均为 0。原冻结来源只有 11 条存有正文，89 条无冻结正文。7 条具有打不开来源、无法确定或仅标题等明确证据限制（重叠去重后），未因此改标签或删样本。具体清单见 label-quality-report.md。

accuracy=主类完全正确数/100；precision=TP/(TP+FP)；recall=TP/(TP+FN)；F1=2TP/(2TP+FP+FN)。主报告 macro 在固定全部 20 类上平均，未定义项按 0；weighted F1 以真人 support 加权。逐类表分母为 0 时显示 N/A，不能解读为 100%。

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| overall accuracy | 43.00% | 55.00% |
| weighted F1 | 43.27% | 54.43% |
| macro precision | 33.02% | 40.03% |
| macro recall | 36.33% | 45.47% |
| macro F1 | 30.00% | 37.96% |

作为补充，仅按有 support 的 16 类计算 macro：修复前 P/R/F1=41.27%/45.42%/37.50%；修复后=50.04%/56.84%/47.45%。不能混用两种 macro 分母。

## 全部 20 类表现与最终阈值

| 类型 | support | 原预测 n | 原 P | 原 R | 原 F1 | 新预测 n | 新 P | 新 R | 新 F1 | AUTO threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| registration_notice | 23 | 14 | 78.57% | 47.83% | 59.46% | 12 | 91.67% | 47.83% | 62.86% | None / 关闭 |
| organization_notice | 6 | 14 | 28.57% | 66.67% | 40.00% | 12 | 41.67% | 83.33% | 55.56% | None / 关闭 |
| selection_notice | 16 | 13 | 84.62% | 68.75% | 75.86% | 14 | 92.86% | 81.25% | 86.67% | None / 关闭 |
| recommendation_notice | 0 | 0 | N/A | N/A | N/A | 0 | N/A | N/A | N/A | None / 关闭 |
| result_notice | 3 | 2 | 0.00% | 0.00% | 0.00% | 1 | 0.00% | 0.00% | 0.00% | None / 关闭 |
| publicity_notice | 2 | 5 | 40.00% | 100.00% | 57.14% | 5 | 40.00% | 100.00% | 57.14% | None / 关闭 |
| completion_news | 5 | 2 | 0.00% | 0.00% | 0.00% | 1 | 0.00% | 0.00% | 0.00% | None / 关闭 |
| competition_intro | 8 | 6 | 83.33% | 62.50% | 71.43% | 8 | 87.50% | 87.50% | 87.50% | None / 关闭 |
| event_news | 2 | 5 | 0.00% | 0.00% | 0.00% | 4 | 0.00% | 0.00% | 0.00% | None / 关闭 |
| policy_recognition_document | 4 | 14 | 28.57% | 100.00% | 44.44% | 14 | 28.57% | 100.00% | 44.44% | None / 关闭 |
| award_policy_document | 7 | 1 | 100.00% | 14.29% | 25.00% | 1 | 100.00% | 14.29% | 25.00% | None / 关闭 |
| postgraduate_policy_document | 2 | 3 | 66.67% | 100.00% | 80.00% | 3 | 66.67% | 100.00% | 80.00% | None / 关闭 |
| comprehensive_evaluation_policy_document | 1 | 2 | 50.00% | 100.00% | 66.67% | 2 | 50.00% | 100.00% | 66.67% | None / 关闭 |
| innovation_credit_policy_document | 0 | 1 | 0.00% | N/A | 0.00% | 1 | 0.00% | N/A | 0.00% | None / 关闭 |
| repost | 3 | 1 | 0.00% | 0.00% | 0.00% | 4 | 75.00% | 100.00% | 85.71% | None / 关闭 |
| deadline_extension | 3 | 2 | 100.00% | 66.67% | 80.00% | 2 | 100.00% | 66.67% | 80.00% | None / 关闭 |
| correction_notice | 1 | 1 | 0.00% | 0.00% | 0.00% | 1 | 0.00% | 0.00% | 0.00% | None / 关闭 |
| rule_update | 0 | 0 | N/A | N/A | N/A | 0 | N/A | N/A | N/A | None / 关闭 |
| historical_material | 0 | 0 | N/A | N/A | N/A | 0 | N/A | N/A | N/A | None / 关闭 |
| other | 14 | 14 | 0.00% | 0.00% | 0.00% | 15 | 26.67% | 28.57% | 27.59% | None / 关闭 |

[完整修复前后 20×20 confusion matrix 与逐类六档阈值](GOLDEN_SET_CONFUSION_MATRIX_20261001.md)。行是真人主类，列是机器预测，两个矩阵计数均为 100，对角线分别 43、55。

completion_news（support=5）没有正确主类预测；competition_intro（support=8）新预测 8 条、正确 7 条；publicity_notice（support=2）与 result_notice（support=3）均不足以支持降低阈值。政策五类真人 support 依次为 4、2、7、1、0（认定、保研、奖励、综测、创新学分），既有明显错误也有零覆盖，不能仅靠提高置信度宣称可靠。

最终全局 AUTO threshold=None；每类 AUTO threshold=None，表示关闭，不是伪造一个大于 1 的“安全阈值”。confidence 仍是规则强度分数，尚未校准成正确概率。本轮明确了保守边界，没有得到可放行的可靠数值阈值。

## 最大混淆及业务影响

| 人工真实类 | 机器预测类 | n | source_id |
| --- | --- | --- | --- |
| registration_notice | organization_notice | 7 | 39789cc74b3c2ae4, 4ad3d9a2637d70e0, 4df4de5a54f4b4fd, 63e563237cae74e8, 6f660aa9659816f8, b3e2646ee801e983, cd825c5c6264530f |
| other | policy_recognition_document | 6 | 0d2368777f63d683, 40a271029fe332cc, 4190c6133726dffa, a03133fb85c1bdb2, ab018c808e5da3b4, df23f13bf9dcfe80 |
| registration_notice | other | 5 | 7dadc36f4575ddf3, a2ec2eede9cfc3b5, af69268dd2f79af1, b90b6751051a9a3a, db257a1ec373600e |
| award_policy_document | policy_recognition_document | 4 | 4de5bc690b072873, 90aa3b87d0f8d1f5, d007c8541743d021, ec9ad38596f10ab6 |
| completion_news | event_news | 3 | 1d1046bd65f95b10, 5f9ea3bfc9c50dc9, 80d0e27349e90e1d |
| result_notice | other | 2 | fa9757919863dab4, fe05d068972168e0 |
| award_policy_document | comprehensive_evaluation_policy_document | 1 | 76aeb4e9a46b3048 |
| award_policy_document | publicity_notice | 1 | fb2b446a2f7344dc |
| competition_intro | other | 1 | afee31ec19b8e9e8 |
| completion_news | other | 1 | a567d8a6248c307b |
| completion_news | publicity_notice | 1 | 8c7038411c0bc520 |
| correction_notice | other | 1 | e87a2fffc6126eed |

报名与组织、完成新闻与活动新闻属于语义邻近，但仍可能影响候选分流，因此保留错误计数。other→政策认定，以及奖励政策→政策认定会改变正式认可关系、政策类型和适用范围，属于业务风险，不能因标题中出现政策词而忽略人工标签。报名→other、更正→other 可能漏掉需要检查的事实，也不能直接移出队列。

## 政策危险误判专项

用户指定的五组在修复前后均为下列结果：

| 危险路径 | 命中/真人组分母 | 比例 | 具体样本 |
| --- | --- | --- | --- |
| 普通报名→政策认定 | 0/23 | 0.00% | 无命中样本 |
| 普通通知→保研政策 | 0/50 | 0.00% | 无命中样本 |
| 获奖相关新闻代理组→奖励政策 | 0/10 | 0.00% | 无命中样本 |
| 普通新闻→综测政策 | 0/7 | 0.00% | 无命中样本 |
| 公示/选拔代理组→任一政策 | 0/18 | 0.00% | 无命中样本 |

普通通知组是 registration、organization、selection、recommendation、result、publicity，共 50 条；新闻组是 completion/event，共 7 条。20 类标签没有独立“获奖新闻”，因此使用 result/completion/event 的 10 条作公开代理组；也没有独立“校内公示”标签，以 publicity/selection 的 18 条作代理组，不能声称严格学校范围已有验证。各组可能重叠，不相加。

上述五个窄组为零，不代表整体政策误判为零。全体非政策真人主类 86 条中有 8 条被判为政策：8/86=9.30%；在机器预测的 21 条政策中占 8/21=38.10%。另外 5 条真人政策被判错政策子类；政策预测的主类总错误 13/21=61.90%。21 条政策预测的规则置信度均为 0.92，所以全局阈值提高到 0.90 仍挡不住。

全部 8 条非政策→政策样本如下（修复前后未改变）：

| source_id | 标题 | 真人主类 | 机器主类 | confidence | 真人原备注 |
| --- | --- | --- | --- | --- | --- |
| 0d2368777f63d683 | 关于公布《南京邮电大学大学生创新创业竞赛项目认定及分类目录（修订）》的通知（校教发〔2025〕1号） | other | policy_recognition_document | 0.92 | 这是南京邮电大学大学生创新创业竞赛名单 ，但是不确定是不是推免名单 |
| 40a271029fe332cc | 物理与电信工程学院本科生学科竞赛级别认定表 | other | policy_recognition_document | 0.92 | 这个是教学管理文件，非竞赛相关  |
| 4190c6133726dffa | 江苏大学学生学科竞赛管理办法（江大校〔2019〕91号） | other | policy_recognition_document | 0.92 | 该网站无法进入，在维修 |
| 6b69006386c3f53e | 国际教育学院推荐2027届优秀应届本科毕业生免试攻读硕士研究生工作实施细则 | other | postgraduate_policy_document | 0.92 | 非竞赛 |
| a03133fb85c1bdb2 | 南京航空航天大学大学生竞赛级别认定表（2024年度） | other | policy_recognition_document | 0.92 | 这是南航的竞赛名单 |
| ab018c808e5da3b4 | 泉州师范学院学科专业技能竞赛管理办法（PDF发现） | other | policy_recognition_document | 0.92 | 无法进入网站，标记 |
| c5598f6ae72d68be | 外国语学院本科人才培养方案（创新实践学分竞赛项目） | other | innovation_credit_policy_document | 0.92 | 这个是本科人才培养方案，与比赛一点关系都没有 |
| df23f13bf9dcfe80 | 泉州师范学院关于印发《泉州师范学院大学生学科专业竞赛管理办法》的通知 | other | policy_recognition_document | 0.92 | 无法进入网站，标记 |

这些样本中存在“文档类型”与“是否属于赛事业务范围”的口径差异，也存在来源不可用。按用户要求，真人 other 仍是 ground truth，没有擅自纠正标签来提高分数。它们足以阻止当前正式政策自动化；后续应针对现有争议厘清口径，不能宣称机器已证实优于人工。

## 六档全局阈值回放

以下只模拟 confidence≥阈值就自动分类，不叠加当前已关闭的授权开关，不代表实际执行自动操作。阈值分母为固定 100 条。政策预测主类全错包含 8 条非政策误入和 5 条政策子类混淆；informational 错放按真人主类不属于信息类或人工次标签含高风险变更统计。

修复前：

| 阈值 | 假设自动 n/100 | 自动占比 | 正确数/自动数 | 自动正确率 | 留人 n | 非政策→政策 n | 政策预测主类全错 n | informational 错放 n | 正确率 Wilson 95% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.70 | 86 | 86.00% | 43/86 | 50.00% | 14 | 8 | 13 | 5 | 39.66%–60.34% |
| 0.75 | 86 | 86.00% | 43/86 | 50.00% | 14 | 8 | 13 | 5 | 39.66%–60.34% |
| 0.80 | 85 | 85.00% | 43/85 | 50.59% | 15 | 8 | 13 | 5 | 40.17%–60.96% |
| 0.85 | 77 | 77.00% | 39/77 | 50.65% | 23 | 8 | 13 | 5 | 39.72%–61.52% |
| 0.90 | 77 | 77.00% | 39/77 | 50.65% | 23 | 8 | 13 | 5 | 39.72%–61.52% |
| 0.95 | 5 | 5.00% | 2/5 | 40.00% | 95 | 0 | 0 | 0 | 11.76%–76.93% |

修复后：

| 阈值 | 假设自动 n/100 | 自动占比 | 正确数/自动数 | 自动正确率 | 留人 n | 非政策→政策 n | 政策预测主类全错 n | informational 错放 n | 正确率 Wilson 95% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.70 | 85 | 85.00% | 51/85 | 60.00% | 15 | 8 | 13 | 3 | 49.37%–69.76% |
| 0.75 | 85 | 85.00% | 51/85 | 60.00% | 15 | 8 | 13 | 3 | 49.37%–69.76% |
| 0.80 | 85 | 85.00% | 51/85 | 60.00% | 15 | 8 | 13 | 3 | 49.37%–69.76% |
| 0.85 | 70 | 70.00% | 40/70 | 57.14% | 30 | 8 | 13 | 3 | 45.48%–68.06% |
| 0.90 | 70 | 70.00% | 40/70 | 57.14% | 30 | 8 | 13 | 3 | 45.48%–68.06% |
| 0.95 | 5 | 5.00% | 2/5 | 40.00% | 95 | 0 | 0 | 0 | 11.76%–76.93% |

提高到 0.95 后政策危险数为 0，是因为没有政策预测通过；总自动正确率反而只有 2/5=40%，不能认定为安全方案。Wilson 区间仅描述这个已选择小样本的计数不确定性，不是未来生产性能保证；同集调规则、来源相关性、非随机选样使外推更弱。

三档边界：AUTO_CLASSIFIED 当前无可用类别；NEEDS_QUICK_CONFIRM 只表示有明确类型建议、无竞争动作和高风险信号，仍须真人确认；NEEDS_MANUAL_CLASSIFICATION 用于未知、冲突、多种竞争动作或高风险证据。QUICK/MANUAL 不再由旧 0.90/0.65 两条数字机械划线。

## informational_only 核验

旧规则信息类预测 13 条，主类完全正确 5/13，信息类别组错放 5/13。修复后仍有 13 条信息类预测，组错放降为 3/13（23.08%），source_id=0c76c55062cfcc59, 8f90563734b142b3, c0de2a9fd355d586。主类精确错误与信息类组错放是不同统计。

现有真人主标签和次标签中，没有观测到 deadline_extension/correction_notice/rule_update 被放进信息类的命中样本；但 rule_update 真人 support=0，且 13 条 informational_safe 专项均没有答案。分类标签不能证明正文不含延期、规则调整或需核实的正式事实。因此不宣称安全认证，本地代码关闭 informational_only 自动移出；投影实际移出数为 0。原先 2 条被移出的候选（66、193）在新离线投影中保留 pending，原隔离库未改写。

已修复旧“人工已确认类型”缓存绕过该限制的路径，保留人工类型，仅重新经过分流安全限制；确认文档类型不等于批准免做字段事实审核。

## 政策抽取与 59 条关系的最终策略

Golden Set 中 21 条机器政策预测只 8 条主类正确。与原 PolicyDocument 直接关联的已标注文档 ID 为 [1, 3, 4, 6, 7, 8, 13, 15, 16, 26, 41]，共 11 个；23 条来源能通过直接或 URL 等不同强度线索关联政策，不能把同 URL/标题的标签无条件传播为全部政策已验证。

59 条旧 AUTO_POLICY_MATCH 全部来自政策文档 9（东南大学同一名单），source_id=23f2c5616e2b79b8；这份文档不在已完成的 100 条分类样本中。59 条学校、非 demo/有效赛事、原 XLS 行/哈希与审计链机械检查通过；58 条精确名称、1 条已验证别名。机械一致性说明匹配可追溯，不证明政策类型、效力和适用范围获得人工认证。

原附件解析为 149 条名单、151 行；旧人工工作台冻结预览只有 60 行。完整 XLS 和解析文本已经存在，本轮没有再抓取。政策专项人工完成数 0；关系专项完成数 1（relation:379，五项 yes），保留已有答案，不能外推其余 58 条。

最终策略统一为 NEEDS_QUICK_CONFIRM，不保留正式自动写入权限；逐条 ID 与既有审计保存在 relationship-review-plan.json（59 条）。这是校准策略和本地代码中的读时约束，未将原隔离数据库的历史记录改写或删除。旧记录读时可显示 historical_automatic_relations，并给出待确认策略；历史事实与当前自动权限分开。

暂停自动化属于授权限制，不应让真实政策被标成无效，也不应撤销已有关系。本轮修复了该区分，并验证明确的版本替代不会因为校准暂停被误报成政策版本冲突。词法名称匹配 AUTO_MATCHED 可作为建议保留；正式 AUTO_POLICY_MATCH 不能仅凭名称相同恢复。

## 审核降噪：来源分类与字段事实分开

| 口径 | 校准前 | 校准后投影 |
| --- | --- | --- |
| 原始候选行 | 254 | 254 |
| 机器 AUTO_CLASSIFIED | 112 | 0 |
| 机器 NEEDS_QUICK_CONFIRM | 14 | 91 |
| 机器 NEEDS_MANUAL_CLASSIFICATION | 128 | 163 |
| informational_only 移出主队列 | 2 | 0 |
| 主队列 pending | 252 | 254 |
| 机器规则保留的分类任务 | 142 | 254 |
| 已有真人标签覆盖候选行 | 本轮读取前尚未复用 | 116（用户已完成，不是 AUTO） |
| 复用真人后剩余候选分类任务 | 不作同口径耗时对比 | 138=27 quick+111 manual |
| 独立来源总数 | 200 | 200 |
| 独立来源机器分流 | 见原回放 | 0 AUTO+96 quick+104 manual |
| 独立来源复用 100 条真人分类后的剩余 | 不重复计算已完成标签 | 100 条来源仍需分类确认 |
| 政策正式自动关系 | 59 | 0（59 条转确认策略） |
| 政策确认条目含本次暂停范围 | 454 | 513=454+59 |

100 条来源标签覆盖 116 条候选，因为同一来源可能关联多条候选。剩余 138 是候选行口径；按去重来源为 100，二者不能相加，也不能把 116 条已完成人工分类继续当作待人工分类。上述复用是离线关联计算，未导入正式事实，也未更新候选状态。

自动分类降低原始 254 条分类工作量的比例为 0/254=0%。已有真人标签覆盖 116/254=45.67%，是已完成工作。旧机器留人 142 与复用真人后 138 相差 4 条（2.82%），但混入真人先前劳动和不同门槛，不能称自动化提升或实测耗时减少。

字段事实仍有 164 条候选、392 项字段提案；学校映射候选 49 条，带标记候选 26 条，集合可能重叠，不相加。分类正确或已人工标注不等于字段事实已批准。主队列当前真实 254 条 pending 的事实状态没有被本轮操作更改。

政策 513 是单独政策名单条目口径，与 254 条主候选不直接相加。59 条策略中 relation:379 已有人审，剩 58 条关系答案待补，同时其共同政策文档 9 的专项确认未完成；513 是包含暂停范围的保守任务上界，不是去除全部复用答案后的净人工点击数。

因此上一轮 254→252 的约 0.8% 队列降噪不能作为安全收益继续保留；本轮新策略离线重放为 254→254。没有真实字段审核耗时，无法由这些计数计算管理员每小时吞吐或节省小时数。

## 本轮规则修复、重复回放与验证

只修复可概括的确定性模式：组织标题句式；校内赛/初赛选拔；publisher 明确转载特征；通用栏目标题配合列表 URL/分页正文识别导航；训练营/培训与赛事新闻区分；赛事新闻要求赛事证据；英文 About/FACTSHEET 配合赛事词。正文中的实际更正、延期、规则变更保留高风险辅助信号。未引入复杂 ML，没有按 source_id 特判。

同一 100 条中 12 条预测改变，全部由错变对，未观察到对变错；剩余 45 条仍错误。没有重取正文、换样本或改人工答案。

| source_id | 标题 | 修复前 | 修复后 | 真人主类 |
| --- | --- | --- | --- | --- |
| 833b1daacbf1aae0 | 教育部关于举办中国国际大学生创新大赛（2024）的通知 | organization_notice | repost | repost |
| 98affffc1a541a9b | 内蒙古师范大学2025年数学建模暑期集训圆满落幕 | completion_news | other | other |
| 24735c6e914be547 | 教育部关于举办中国国际大学生创新大赛（2025）的通知 | organization_notice | repost | repost |
| bb8a856574c03201 | 2024高教社杯全国大学生数学建模竞赛”报名第一次通知 数模竟赛[2024一01 ]号 | registration_notice | repost | repost |
| 2d8c0f7695f2ae08 | 学科竞赛 | result_notice | other | other |
| c2e6ad516a093afd | 2025年全国大学生电子设计竞赛暨校内赛启动报名通知 | registration_notice | selection_notice | selection_notice |
| 571985d34fdfb23f | 关于开展广西师范大学2025年“劳动周”“劳动月”活动的通知 | event_news | other | other |
| d576c53bef29c94e | 关于举办2024年第十四届“挑战杯”中国大学生创业计划竞赛校内初赛的通知 | organization_notice | selection_notice | selection_notice |
| 2504e21d82ba21db | 关于组织2025年全国大学生电子设计竞赛的通知 | other | organization_notice | organization_notice |
| e968517716a5a49a | The 2008 ACM INTERNATIONAL COLLEGIATE PROGRAMMING CONTEST — FACT SHEET – 29 JAN 2008 | other | competition_intro | competition_intro |
| b13b6c111c988f9c | The 2026 ICPC World Finals Dubai hosted by Dubai Chamber of Digital Economy — About ICPC | other | competition_intro | competition_intro |
| cb5409d323f77dd4 | 关于宿迁学院2025年“数学建模竞赛实验班”报名选拔的通知 | selection_notice | other | other |

规则版本 document-rules-1.1；校准策略 golden-20261001-hold-v1。缓存校验纳入规则版本、校准版本和来源指纹，已有人工标签保留。重复运行同输入得到逐字节一致结果，见 replay-stability.json；确定性稳定不等于统计泛化。

最终后端全套：1033 passed in 58.47s，退出码 0。新增独立安全/指标测试合计 41 项（23+18），完整日志 backend-full-final.log。先有失败回归再修复；中途一次新测试夹具遗漏 source_type 已纠正，最终全套通过。旧机制测试用局部 fixture 显式模拟“假设已获得自动授权”，真实默认关闭由独立安全测试覆盖，测试通过不能充当分类准确率或政策安全证明。

前端没有修改，本轮没有重跑前端 lint/typecheck/build，不能把上一轮结果冒充本轮新验证。没有 schema 迁移、重新采集、部署、push 或 merge；没有自动批准/拒绝候选。修改限于本地规则、自动权限保护、离线指标脚本、测试和报告。未重启已有运行服务，因此这些本地代码限制不能表述为旧服务已热更新；报告数值来自直接调用修复代码的离线重放。

## 文件完整性与可复现证据

| 保护文件 | 操作前/后 SHA256（相同） |
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

上述 9 个保护输入文件 SHA256 操作前后均一致，包括正式库、原候选库、真人标签库、原 manifest 和上一轮两个隔离回放库。新分析只写 .codex-qa/golden-calibration-20261001/ 与本报告；原标签未修改。

证据索引：

- human-snapshot.json：原真人分类、审计、事件的只读快照。
- calibration-results.json：全部统计、全局/逐类阈值曲线、分母、误分类 ID、分流与队列投影。
- source-replay-calibrated.json / candidate-replay-calibrated.json：200 来源和 254 候选逐条离线重放。
- label-quality-report.md / label-quality-facts.json：重复、缺正文、备注限制、标签覆盖审计。
- policy-safety-report.md / policy-safety-evidence.json：原政策和 59 条关系的只读证据链。
- relationship-review-plan.json：59 条关系逐条确认策略，保留已审项，不修改原库。
- before.json / final-checks.json：前后保护哈希与本轮文件变更清单。
- backend-full-final.log / replay-stability.json：最终测试与重复回放证据。
- [完整矩阵与逐类阈值附录](GOLDEN_SET_CONFUSION_MATRIX_20261001.md)。

在 backend 目录复现指标可运行 .\venv\Scripts\python.exe -m scripts.calibrate_golden_set；脚本使用既有只读快照与冻结来源，不提交真人决定或写原数据库。输出文件位于上述忽略目录。

## 结论与后续边界

100 条真实人工 Golden Set 已完整读取并评估，不再把“没有真实人工标签”当阻塞，也不要求重做这 100 条。当前数据揭示实际分类质量与政策自动权限之间存在缺口：高分并不可靠，五组窄口径零错误掩盖了 8 条其他非政策误入，政策来源 9 又未被这批分类标签覆盖。

可以继续进行人工候选审核吞吐基线实验，保持自动分类、自动移出和正式政策自动关系关闭；计时应覆盖打开候选、阅读字段/来源和提交决定，不能用此次标签保存时间差代替。现有页面运行的是先前服务版本，应在实际实验采用已验证代码的隔离服务后再评估其分流体验。

下一阶段仅建议使用已有材料澄清争议标签的定义、核验政策 9 与剩余关系、建立独立验证口径；不重新抽取 100 条、不重做已完成标签、不扩量抓取。本报告不把开发集 12 个修正包装成已证明泛化，也不为维持自动化比例而给出未经验证的阈值。

**DOCUMENT_POLICY_AUTOMATION = BLOCKED**
