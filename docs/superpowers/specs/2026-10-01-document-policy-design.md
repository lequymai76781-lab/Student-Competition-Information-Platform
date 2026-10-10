# 来源文档自动分类、政策名单抽取与审核降噪设计

日期：2026-10-01。用户已明确授权本轮正常本地开发，无需重复设计/命令批准。范围以附件47节要求为准。

## 目的与约束
减少重复文档分类和有明确证据的政策关系判断。普通通知只能支持 participation_evidence，不能产生政策认可。赛事字段继续走现有 field review；延期、更正、规则更新始终高风险。不得修改正式数据库、原候选库，不迁移、不部署、不扩抓。保留人工吞吐实验副本与日志，不把自动化数据当真人。

## 选择
采用可解释规则 + 结构化抽取 + 保守赛事匹配 + 受限自动关系写入。全部交给LLM会增加不可复现与误判风险；只做分类而不接队列不能降低实际工作量。沿用既有JSON/PolicyDocument/CompetitionPolicyRecognition/ReviewQueue/AdminAuditLog，不另建模型表。

## 边界
1. classify_document(source: dict, *, has_fact_changes=False, has_conflicts=False, has_valuable_relation=False) -> dict 是纯函数。title/source_title、content_preview/content_text、publisher、section、attachment_titles；输出 document_type/primary_type/secondary_types/confidence/classification_reason/matched_rules/requires_human_confirmation/informational_only/risk_level/classification_status/rule_version。分数是规则置信分，尚非概率校准。
2. extract_policy_entries(content: str, *, format='text', title='') -> list[dict]；parse_policy_file(path) -> dict。每行保留 raw_competition_name/evidence_text/locator，缺正文和扫描件明确失败，不猜名字。HTML表/列表、编号正文、PDF文本、DOCX/DOC、XLSX/XLS复用现有解析器。
3. match_policy_competition(db, raw_name: str, *, hints=None) -> dict；只读正式Competition和verified alias。输出 normalized_name/match_status/match_confidence/matched_competition_id/match_reason。唯一精确/验证别名可AUTO_MATCHED；模糊和子赛道不能高置信度提升。
4. 文档分类与候选关联存 raw_value.document_classification。无事实修改/冲突/高价值关系的信息材料保存且归档为informational状态，不删除。普通通知自动确定类型，字段提案继续审核。分类更改写audit。
5. PolicyAutomationService处理已保存PolicyDocument；请求不能上传official=True等自证标记。来源校验使用学校/学院正式域名和实际正文/附件、原解析状态、政策范围、正式生效条款/日期。不明、失效、缺附件、OCR、冲突进入人工。仅此服务在严格校验后调用受限写入，不能改变Competition/Edition。重复回放幂等。
6. 多维认可写现有usage_type，每条关系evidence保存AUTO_POLICY_MATCH的政策原文、位置、匹配方法、有效期、原名和规则版本。PolicyDocument.metadata保存policy_automation、superseded_by版本链和current支持。冲突旧版当前关系不可继续作为已确认公开依据；明确同范围替代才自动退役旧版，否则标记needs_review供人工处理。
7. 新增/admin/document-policy管理页：来源分类列表/纠正、政策分析结果、自动关系及人工原因。原字段审核详情展示系统分类，无需重复选择类型。普通用户数据层保留usage_type多维语义，未知不推断为无。

## 验证与数据真实性
历史来源100–200条按URL去重，只读取本地已有资料。政策重放保存来源文件/文档ID证据。模型生成测试夹具仅用于A–I功能验证，真实回放指标另报。人工golden标签须有reviewer和reviewed_at，不以历史机器分类或AI临时标注冒充；暂无时生成50–100条待标注集，precision/recall/confusion matrix为未验证而非编造，最终BLOCKED。
阈值初始0.90/0.65，真实人工golden不足不能声称已校准。审核降噪分别统计分类任务与仍需审核的字段任务，不能把AUTO_CLASSIFIED算作所有人工工作已消失。

## 工作区
当前main含前阶段大量未提交实现，本任务依赖这些代码。复用此用户工作区，不切换或重置分支；本轮前文件哈希与数据库哈希保存于.codex-qa/document-policy/before.json。各子任务仅写指定文件，集成根任务负责。回放/服务均使用新的隔离副本，与3050/8050人工实验服务分离。
