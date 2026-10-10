# 两级分类与 Policy 安全判定设计

用户完整设计来源：本轮 710fba4b 附件。用户已授权所有正常本地开发；不重复审批，不抓取、不扩量、不改正式库、不迁移，不改既有人标。既有工作区含大量未提交成果，原地增量且不 commit/reset/stash。

采用兼容增量方案：旧 20 类函数仍提供可解释细标签/历史评估，新 classify_source_document(source, **flags) 包装成 7 类 primary_type；document_type 保留细类，secondary_type 为规范二级标签。备选“直接替换全部 20 类枚举”会破坏历史主标签与关系类型；仅做映射则无法降低 policy false positive，因此新增独立正负证据判定器。

一级固定 participation/result/information/policy/update/repost/other；中文显示参赛相关、结果/公示、赛事信息、政策/认定、更新/更正、转发、其他。原人工主标签映射一级，原细标签与次标签只读保留。

policy_safety_classifier.classify_policy(source) -> is_policy、policy_confidence、policy_reason、policy_status、positive_evidence、negative_evidence。至少消费 title/publisher/section/content_preview/attachment_titles；仅强规范文档+赛事业务相关性+支持性机构/结构证据才判 policy，普通报名/结果/新闻/转发压低分数；不足为 NEEDS_POLICY_CONFIRM 或 NON_POLICY。不得硬编码学校、来源 ID、特定标题。

hierarchical_source_classifier.classify_source_document 与服务接口：primary_type=七类；document_type=原细类建议；secondary_type=规范二级；secondary_types=原细类多标签；referenced_primary_type 用于转发；policy_assessment 存上述独立结果并展平 is_policy/policy_confidence/policy_reason；hierarchy_version、confidence、classification_status、risk_level、informational_only、requires_human_confirmation、routing_reason。一级自动分类不批准事实，不需要选择二级。update 或含实际更新信号始终 HIGH_RISK、field review；转载不视作原始官方证据。other 人审。

自动权限依据本轮实际回放选定；未证明的 policy 正式自动权限保持关闭。信息移出须明确 information 且没有重要字段、变更、政策疑点、冲突、学校关系或内容缺失风险；缺证据不能以无抽取字段推断全文安全。policy 分类、抽取、匹配、关系决定各层独立，官方来源/有效期/唯一匹配/版本冲突任一未过，不得 SAFE_AUTO。

兼容人工更正：API 可接受七类一级与旧细类；人工已有细类保留并映射新一级，安全属性重新计算；类型确认不批准事实。缓存纳入 hierarchy_version；主队列 GET 不写库。报告与真实回放只写分析目录，原 59 条关系逐条重新分级但不改原库。

评估含旧 20 类、仅合并 7 类、新七类；保留 100 原始人工主标签。全局与 policy 独立六阈值，七类全矩阵、分母和错例；固定种子配对 bootstrap（非独立泛化验证），政策精确率区间及小样本限制。200 来源、254 候选离线重放，已有标签复用与字段事实任务分开。

测试重点：update 埋在新闻正文；普通获奖/报名包含政策词；政策证据不足；同一级多个细标签不强制人审；已有人工类型不能绕过安全门；转载不能形成正式认可；正式库哈希不变。前端只增加中文层级显示和可选修改入口，不改 Golden Set 标签。浏览器用独立副本/测试用户，自动化操作不计真人样本。

完成须验证全部后端、前端测试/lint/typecheck/build与浏览器；报告满足 30 项，技术通过不替代真实质量通过。若未证实安全或样本不足，HIERARCHICAL_CLASSIFICATION=BLOCKED。
