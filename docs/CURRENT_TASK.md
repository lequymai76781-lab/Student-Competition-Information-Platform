# 当前任务与接续入口

更新日期：2026-10-01。本轮《两级文档分类与 Policy 安全判定》实现与评估完成，**HIERARCHICAL_CLASSIFICATION = BLOCKED**。原 100 条人标未修改；不重新标注、不扩量。

- 七类一级+二级语义、独立 Policy 正负证据门、中文可选更正已接入。分类不批准事实或政策关系。
- 同批 Accuracy：旧细类 55%→机械合并71%→新保守规则68%；Macro F1 新61.97%，weighted F1 新67.43%。不能将合并红利宣称泛化提升；相对机械合并配对 bootstrap 差 −3pp，95% CI [−12,+6]pp。
- Policy FP8→0，但TP1/FN13，阳性n=1。正式关系安全阈值未获验证；59条均QUICK_CONFIRM，原库不改。update漏1/4（无正文占位来源，保留other人工），吞入information0。
- 仅清晰participation开放一级自动分类，Golden36/36；result/information/repost仍确认，update/other人工，信息自动移出关闭，真实informational_only0。
- 254候选离线：77AUTO/34QUICK/143MANUAL；机器减少分类任务30.31%。复用已有116行人标（89来源）后剩110分类任务，不能把已完成的人力算成机器收益；字段164行392提案仍独立审核，原254仍pending。
- 后端1149、前端84、lint/typecheck/build与真实Edge七场景通过。11个保护输入SHA不变；无抓取/扩量/迁移/部署。新增独立8055/3055是明确功能夹具验证预览，不是原真人实验库。
- [完整30项报告](HIERARCHICAL_CLASSIFICATION_REPORT_20261001.md)、[新一级矩阵/逐类阈值](HIERARCHICAL_CLASSIFICATION_MATRIX_20261001.md)。证据 .codex-qa/hierarchical-classification-20261001/。
- 下一阶段先补现有来源证据/语义口径和政策专项验证；不重标100条。可继续人工吞吐基线，但分类减量不是实测工时。

## 上一阶段校准记录

更新日期：2026-10-01。本轮已读取用户完成的原 100 条真实人工 Golden Set，完成分类评估、确定性规则修复、全部重放与自动边界限制。**DOCUMENT_POLICY_AUTOMATION = BLOCKED**，原因是高风险政策误判仍存在、尚无可靠自动阈值；不再是缺少分类标签。

- 100/100 完整且未改标；准确率 43%→55%，全部 20 类 macro F1 30.00%→37.96%，weighted F1 43.27%→54.43%。12 条错变对，无对变错；属于开发集重放，不是独立验证。
- 仍有非政策→政策 8/86；21 条政策预测中 13 条主类错误。全部 20 类 AUTO threshold=None，本地代码暂停自动分类、informational_only 自动移出与正式 AUTO_POLICY_MATCH；quick/manual 根据证据明确性与风险分流。
- 59 条旧自动关系统一确认策略，保留 relation:379 既有人审；其余 58 条及共同政策文档 9 尚未专项确认。原隔离数据库没有改写。
- 原始候选仍 254 pending；机器投影 0 AUTO/91 quick/163 manual。100 条既有人审来源覆盖 116 条候选，复用后剩余分类 138=27 quick+111 manual；已有分类不等于字段事实批准。
- 最终后端 1033 passed；正式库、候选库、真人标签库及全部 9 个保护输入哈希未变。无迁移、抓取、部署。未重启已有服务，代码收紧与队列统计为本地实现及离线投影。
- [完整 25 项报告](GOLDEN_SET_AUTOMATION_FINAL_REPORT_20261001.md)；[完整矩阵与逐类阈值](GOLDEN_SET_CONFUSION_MATRIX_20261001.md)。证据目录 .codex-qa/golden-calibration-20261001/。
- 不让用户重新标 100 条；不新建样本，不扩量。可继续人工吞吐基线，但不能以标签保存间隔代替候选审核耗时。

## 上一轮准备记录（已被上述实际完成结果更新）

更新日期：2026-10-01。本轮《建立真实人工 Golden Set 并完成分类器校准》已完成专用页面与真实样本准备，等待用户人工操作。**DOCUMENT_POLICY_AUTOMATION = BLOCKED**，真人分类 0/100、政策抽验 0/20、关系抽验 0/20（交接前只读核验）。

- 页面：http://127.0.0.1:3054/admin/golden-set；独立 API 8054。默认预测隐藏、无预选；1–9 选高频类型，Enter 保存下一条，Alt+左右翻页。草稿/跳过不计完成，修订受版本保护。
- 原 100 条 ID/顺序/预测完整保留，只有 11 条有已存正文；20 政策和20关系从上一轮历史回放选取，未重新采集。
- 标注只写 `.codex-qa/golden-set-20261001/live/annotations.sqlite`；同目录 `auth.sqlite` 仅用于实验登录，正式实体为空。fixture 子目录只用于功能验证，禁止把其中机器操作计入真人数据。
- 技术验证：后端992、前端77、lint/typecheck/build、真实 Edge 交互和真实数据只读核验通过。正式/候选/原吞吐实验库哈希不变，分类规则、阈值与政策自动化权限未改动。原服务8050/3050、8053/3053未被重用。
- 完整29项报告：[GOLDEN_SET_CALIBRATION_REPORT_20261001.md](GOLDEN_SET_CALIBRATION_REPORT_20261001.md)。证据在 `.codex-qa/golden-set-20261001/`，人工使用说明 `HUMAN_GUIDE.md`。
- 后续先让用户自己标注；不要代选、自动approve/reject、抓取或扩大功能。真实标签完成后读取评估与导出，补充安全/阈值结论。未达到100+20+20及有效校准时保持BLOCKED。

## 上一阶段记录

更新日期：2026-10-01。《来源文档自动分类、政策名单抽取与审核降噪机制》实现与隔离验证已完成，**DOCUMENT_POLICY_AUTOMATION = BLOCKED**。阻塞是独立人工golden set为0、阈值未校准，以及主队列实际仅减少2/254，尚未证明明显减少总审核工作。用户本轮最后粘贴的完整请求已明确授权正常本地开发，替代此前“本轮不开发”范围。

- 完整37项报告：[DOCUMENT_POLICY_AUTOMATION_REPORT_20261001.md](DOCUMENT_POLICY_AUTOMATION_REPORT_20261001.md)。
- 真实回放200个来源、76条历史政策、513条名单条目；193条名称自动匹配，59条通过政策证据条件自动形成policy_recognition，均在隔离副本。454条政策条目仍待确认；原field队列隔离重放254→252，仅2条informational退出。
- 20类可解释规则、多标签、分类修正审计、事实审核隔离、普通通知participation_evidence、政策多维匹配和版本冲突保护已接入。修订/更正/延期保持高风险。未建立新表或迁移。
- 后端940项、前端65项，lint/typecheck/build通过；真实浏览器证据在`.codex-qa/document-policy/`，A–I与分类纠正分别记录。功能测试样例与真实历史统计完全分开。
- 真实回放目录：`.codex-qa/document-policy/replay-verified/`；`golden-to-label.csv`是100条真实来源的空白人工表。人工标注、precision/recall、混淆矩阵与阈值校准尚未完成，不能用自动化结果代替。
- 数据库：正式`data/v02.sqlite`、原候选`.codex-qa/mid-scale/candidates.sqlite`及原人工实验副本SHA256均未改变。无部署、push、merge、新抓取或全国扩量。
- 实验预览：8053 API、3053前端；当前连接明确的功能样例数据库`browser.sqlite`，不是正式库、真实回放库或原人工审核实验库。原人工审核8050/3050保持独立，没有自动代审。
- 停止于报告。下一步先补真实人工分类标签并抽检自动政策关系，不自动扩大赛事或高校规模。

## 前阶段人工吞吐状态（保留历史结论）

更新日期：2026-09-28。《审核吞吐优化与高校赛事关系正式入库闭环》代码与自动化验证已完成；REVIEW_THROUGHPUT = BLOCKED，仅保留人工吞吐验收缺口。停止新增赛事和高校采集，使用原 254 条候选的隔离副本。用户已确认：4 条真实 LOW_RISK 加 50 条明确合成批量压力验证；最新答复为“暂时无法操作，保留人工样本缺口”。

本轮工作与证据：
- 设计与计划：superpowers/specs/2026-09-28-review-throughput-design.md、superpowers/plans/2026-09-28-review-throughput.md。
- 风险分类、跨候选原子批量、来源/队列分页、学校关系审核、审计计时已实现。真实HTTP准备、政策范围/时效缺陷已修复；后端792、前端57及lint/typecheck/build通过。
- 三个实验副本：.codex-qa/review-throughput 下 manual.sqlite、automation.sqlite、synthetic.sqlite；真实主候选库 .codex-qa/mid-scale/candidates.sqlite 与正式 data/v02.sqlite 保持原样。
- 本轮服务已停止，副本与证据保留。复现端口约定：人工8050/前端3050、自动化8051、合成8052。人工临时账号见忽略目录 HUMAN_GUIDE.md；不得将账号、数据库及审计原始副本提交 Git。
- 真实自动化 36 条：4 低风险、10 单来源、10 跨候选同字段一致、5 冲突、5 学校通知、单赛事额外 2 条；合成 50 条另行统计。机器时长不是人工产能。
- 人工样本0，副本254条仍pending；不得用自动化耗时替代人工产能。真实政策另2条功能闭环通过，无人工计时。
- 完整33项报告见 [REVIEW_THROUGHPUT_REPORT_20260928.md](REVIEW_THROUGHPUT_REPORT_20260928.md)，本轮不继续扩量。旧 R12/R13/R14 仅保留。

## 前阶段中规模状态

更新日期：2026-09-28。“中规模真实数据扩展与普通本科高校覆盖试点”已完成，**MID_SCALE_DATA_EXPANSION = PASS**。停止于本轮报告，暂不建议更大规模采集，等待用户另行安排。

## 最新阶段结果

- [完整 32 项报告](MID_SCALE_DATA_EXPANSION_REPORT_20260928.md)、[来源与重放说明](mid-scale/README.md)、[30 校逐校覆盖](mid-scale/SCHOOL_COVERAGE.md)、[80 个赛事覆盖](mid-scale/COMPETITION_COVERAGE.md)。
- 80 个选定赛事：69 个有结构化提案、11 个仅线索；30 校尝试、28 校有正文。新增 122 条来源、147 条候选、140 项字段提案。累计 254 条主库候选全部 pending；3 条明确政策证据不是正式新增认定。
- 后端 647 项、前端 45 项、lint/typecheck/build 通过；正常应用真实浏览器 10 组及最后 2 项日期精度断言通过。
- 主库 `.codex-qa/mid-scale/candidates.sqlite`；浏览器副本同目录 `browser.sqlite`。仅后者批准一个候选的两个低风险字段，前者保留全部人工待审。原 `.codex-qa/real-data-pilot/candidates.sqlite` 与正式库 SHA 均保持不变。
- 批量任务暂停/恢复、完整重放（0 新增、147 复用）、部分失败重跑、租约并发与失败历史已验证；普通审核列表分页小范围优化。
- 限制：本地 HTTP 122 条最新探测仅 24 条返回 200；真人审核平均耗时未知，主库净增积压 147。学校关系可查看/筛选/拒绝，尚无正式批准入口；冲突筛选 1,142 次 SQL。PASS 不代表这些扩量前提已解决。
- 无 schema 迁移，无正式入库、清理、部署或 Git 提交。旧 R12/R13/R14 不在本轮重新审计范围。

## 前阶段小批量状态

更新日期：2026-09-28。“真实赛事小批量资料补齐与审核链路压测”已完成，**REAL_DATA_PILOT = PASS**。24 个现有赛事、74 条来源记录生成 107 条未批准候选、252 个字段提案。独立审核库保留全部待审，5 个真实赛事的浏览器批准在另外副本完成。正式库 SHA256 不变；停止于本轮报告，不自动扩大数据量。

## 前阶段小批量结果

- 报告：`REAL_DATA_PILOT_REPORT_20260928.md`；来源清单与重放说明：`real-data-pilot/README.md`。
- 后端 606 项、前端 43 项通过；lint/typecheck/build 通过；浏览器 8 组验证及 2 项匿名日期断言通过，逐一查看 24 个赛事、完成 5 个闭环。
- 候选库：`.codex-qa/real-data-pilot/candidates.sqlite`；浏览器验证副本：同目录 `browser.sqlite`。前者 107 条全部 pending，不能用后者代替人工审核队列。
- 5 组字段值差异涉及 9 条冲突候选；65 条来源读到正文，9 条只留原始线索。实时 HTTP 检查 86 个链接中 17 个返回 200，其余连接受限或超时，未将它们自动核验。
- 保留日期精度、专项赛道、学校映射/认定审核及来源核验重复操作等实际痛点；下一步仅适合受控候选扩量，详见报告限制。R12/R13/R14 未扩展处理。

## 已完成的字段审核阶段

“字段级入库预览 + 来源核验 + 审核后台强化”阶段已完成，**PHASE_APPROVAL = PASS**。正常应用、用户提交、旧审核入口及 SessionLocal 写保护均已接入。

## 字段审核阶段实施依据

- 范围只包括 Competition / CompetitionEdition；复用 ReviewQueue JSON、事实来源、修订与审计，不新增表或迁移。
- 已实现候选、字段差异、来源人工核验、冲突、逐字段决定、届次隔离、原子审核、低风险批量，以及 `/admin/field-review` 前端。
- SessionLocal已使用ReviewGuardedSession。采集适配走候选；旧赛事POST/PUT直写返回409，用户纠错/赛事补充进入候选。零字段材料可保留原来源直接拒绝；并发转入原提交只创建一个候选。
- 用户已明确批准此前具体切换并取消相关暂停限制，接入已完成。授权与切换记录见 `FIELD_REVIEW_WRITE_GATE_APPROVAL.md`，当前无待确认事项。
- 进度、验证结果及准确缺口见 `FIELD_INGESTION_SOURCE_REVIEW_REPORT_20260927.md`；设计见 `FIELD_REVIEW_DESIGN_20260927.md`；采集边界见 `FIELD_REVIEW_INGESTION_AUDIT_20260927.md`。
- 完整后端584项、前端43项通过；lint/typecheck/build通过；正常应用+真实SessionLocal+合成库的浏览器12项通过，正式库SHA256未变。两轮独立复查6项问题均已修复复验。不要开始大规模采集、学校通知/政策审核扩展或会议前端。

## 已完成

- 恢复仓库和只读数据基线，见 `CORE_USER_JOURNEY_20260927.md`。
- 真实 API 驱动首页、搜索筛选、同届次详情、学校通知与来源、纠错/遗漏提交。
- 按当前时间及学校/学院截止计算状态；排序后分页；学校选择覆盖全部已收录院校。
- 私人提交所有者隔离、管理员队列鉴权；截止审批的正式事实/队列/通知/修订/审计统一事务，异常回滚并可重试，旧审核快照不能覆盖终态。
- 安全登录返回地址、身份切换清理、迟到响应防护；SSR会话恢复和手机退出已验证。
- 用户历史和管理员各队列有界分页，需补证与已处理状态保持可访问。
- 2024/2025/2026届次来源隔离；UTC存储/API和上海时区展示；公开待审事实、未核验届次及冲突核验标记过滤。
- 上一轮安全修复后端449项、前端30项回归通过；lint/typecheck/build通过；真实浏览器17项通过。正式库SHA256不变。详见 `SECURITY_DATA_CONSISTENCY_FIX_REPORT_20260927.md`。
- 前阶段报告及 `INDEPENDENT_REVIEW_20260927.md` 保留当时结论，不视为当前剩余缺陷已自动关闭。
- 最终定向复核：R06 CLOSED；R12 PARTIALLY FIXED；R13/R14 OPEN。仅修复R06，新增9项回归；后端458项、前端30项通过，lint/typecheck/build通过，8项浏览器核验符合预期（含1项R14缺陷复现）。正式库SHA256不变。最终阶段判断见 `FINAL_TARGETED_REVIEW_20260927.md`。

## 保留问题与停止点

1. R12/P2：列表及统计全量ORM加载仍存在；统计已不再构建卡片。保留为非阻塞性能债务，未开展查询重写。
2. R13/P3：直接使用unknown状态参数时仍可能返回无匹配届次的赛事；UI不提供此选项。
3. R14/P3：重复source_scope仍导致错误页；正常表单生成单参数，返回正常URL可恢复。
4. 当前P0=0、P1=0、P2=1、P3=2。无真正阻塞项，阶段可结束；不是全部缺陷清零。
5. 上述缺陷计数属于已批准的上一阶段，保留为非阻塞技术债；本轮不重新审计 R12/R13/R14。字段审核阶段依据本轮独立测试及真实浏览器证据通过，没有沿用旧结果代替验证。

## 工作约束

- 不重做测试数据库隔离，保持防误连接和 fixture。
- 本轮未迁移正式库，迁移版本仍为 `202609060005`；无生产清理、数据导入或部署变更。
- 正式库SHA256：`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`。
- 旧无时区日期按UTC解释，不猜测修正历史数据；旧JSON缺失的时分秒没有自动恢复。
- 缺失数据保持缺失，不生成赛事历史、学校通知或政策。
- 高校类型仅用于内部采集策略，不做用户分级。
- 用户补充必须审核；来源及目标实体不明确时不得写正式事实。
- 留可审查 Git diff，不提交敏感文件、数据库副本、缓存或凭据。
