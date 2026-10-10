# 来源文档自动分类、政策名单抽取与审核降噪报告

日期：2026-10-01。范围依据本轮最后粘贴的《来源文档自动分类、政策名单抽取与审核降噪机制》，该请求已明确授权本地开发。原人工吞吐实验未被自动代审，本报告也不将机器耗时作为人工吞吐。

**DOCUMENT_POLICY_AUTOMATION = BLOCKED**

分类、抽取、匹配、隔离库关系写入与审计已实现。真实回放得到59条自动政策关系，但独立人工golden set为0，无法给出有效precision/recall或校准阈值；原主队列仅减少2/254（约0.8%），尚不能证明“明显减少总审核工作”。这两项验收缺口不能由功能测试通过替代。

## 1—27：真实回放与降噪

| 序号 | 要求 | 结果与口径 |
| --- | --- | --- |
| 1 | 文档分类体系 | 20种，见下表；支持主类型和次要类型。 |
| 2 | 自动分类规则 | deterministic规则；标题优先，正文开头、栏目、机构、附件标题辅助。命中规则、原因、风险、分数和规则版本均可追溯。无LLM分类调用。 |
| 3 | 真实回放数量 | 264个已有真实URL中按预测类型轮询选200条；另回放原254条field候选及全部76条历史PolicyDocument。没有新增抓取。 |
| 4 | golden set | 准备100条真实来源的空白标注表；已确认独立人工标签 **0条**。不把规则或模型标签当人工标签。 |
| 5 | 各类型precision | 全部N/A；人工真值不足。 |
| 6 | 各类型recall | 全部N/A；人工真值不足。 |
| 7 | confusion matrix | 空矩阵 `{}`，n=0；不是零错误矩阵。机器预测分布不能作为混淆矩阵。 |
| 8 | AUTO_CLASSIFIED | 200来源中105；254候选中112。 |
| 9 | NEEDS_QUICK_CONFIRM | 200来源中14；254候选中14。 |
| 10 | NEEDS_MANUAL_CLASSIFICATION | 200来源中81；254候选中128。 |
| 11 | informational_only | 200来源静态分类13；考虑实际字段和学校关系后，仅2条真实field候选安全退出主队列。 |
| 12 | 政策文件数量 | 76条历史文档记录全部回放；其中21条主分类为政策类。200来源中29条政策类来源；这些口径不能相加。 |
| 13 | 政策赛事条目 | 513条提取条目，513个带认可维度的候选。9条文档读取已保存的本地附件；不完整解析仍进入人工。 |
| 14 | 自动赛事匹配 | 193条AUTO_MATCHED；匹配成功仍须通过官方来源、有效期、范围、完整性、版本等条件。 |
| 15 | 快速确认匹配 | 127条NEEDS_QUICK_CONFIRM。 |
| 16 | 人工匹配 | 193条NEEDS_MANUAL_MATCH。 |
| 17 | 自动形成认可关系 | **59条**，只写入隔离政策回放库，均保存AUTO_POLICY_MATCH审计。其余454条保留待确认任务。 |
| 18 | postgraduate recognition | 真实回放新增0；浏览器功能样例另行验证，未混入统计。 |
| 19 | comprehensive evaluation recognition | 真实回放新增0。 |
| 20 | innovation credit recognition | 真实回放新增0。 |
| 21 | award recognition | 真实回放新增0；功能样例另行验证。 |
| 22 | policy recognition | 真实回放新增59，均来自东南大学已保存的正式竞赛目录。 |
| 23 | participation evidence | 15条高置信度普通学校通知已保存显式participation_evidence来源记录；状态evidence_only。不是政策认可，不批准正式字段。缺少学校/赛事身份或分类不足的材料不自动建立该记录。 |
| 24 | 新旧政策冲突 | 真实回放检出0条冲突文档；不能解释为历史不存在冲突。功能样例验证了冲突、明确替代、否定废止和旧关系失效。 |
| 25 | 人工审核任务减少 | 分类选择子任务可省112/254，约44%；**实际主队列254→252，仅减少约0.8%**。字段或高价值关系仍保留人工审核。未测人工耗时。 |
| 26 | 人工关系判断减少 | 59/513，约11.5%，是“每个提取条目原本逐条判断”假设下的自动覆盖率。454条仍待确认；不是实测人工工时降幅。 |
| 27 | 误分类主要类型 | 无人工真值，不能报告实测误分类率或主要误分类类型。重点待核查：模糊标题other、普通通知引用政策、正式福利政策标题和多用途文件。 |

初始阈值为0.90/0.65，属于**未经人工校准的规则分数**，不表示准确率为90%/65%。阈值尚未完成用户要求的真实golden set验证。

| 类型 | 200来源预测数 | 人工支持n | precision | recall |
| --- | ---: | ---: | --- | --- |
| `registration_notice` | 17 | 0 | N/A | N/A |
| `organization_notice` | 31 | 0 | N/A | N/A |
| `selection_notice` | 18 | 0 | N/A | N/A |
| `recommendation_notice` | 0 | 0 | N/A | N/A |
| `result_notice` | 2 | 0 | N/A | N/A |
| `publicity_notice` | 5 | 0 | N/A | N/A |
| `completion_news` | 2 | 0 | N/A | N/A |
| `competition_intro` | 6 | 0 | N/A | N/A |
| `event_news` | 5 | 0 | N/A | N/A |
| `policy_recognition_document` | 22 | 0 | N/A | N/A |
| `award_policy_document` | 1 | 0 | N/A | N/A |
| `postgraduate_policy_document` | 3 | 0 | N/A | N/A |
| `comprehensive_evaluation_policy_document` | 2 | 0 | N/A | N/A |
| `innovation_credit_policy_document` | 1 | 0 | N/A | N/A |
| `repost` | 1 | 0 | N/A | N/A |
| `deadline_extension` | 2 | 0 | N/A | N/A |
| `correction_notice` | 1 | 0 | N/A | N/A |
| `rule_update` | 0 | 0 | N/A | N/A |
| `historical_material` | 0 | 0 | N/A | N/A |
| `other` | 81 | 0 | N/A | N/A |

采样限制：类型轮询是有意覆盖采样，不是随机总体抽样；20种中3种在本次200条中没有出现。只有20条保存了可直接用于本次分类的正文，其余主要依靠标题。即使后续标完100条，仍须明确稀有类别样本数、漏报和“普通通知误判正式政策”的风险，不能把单次样本表现包装成稳定生产准确率。

### 政策回放的实际限制

59条自动关系全部来自一份文档（policy_document_id=9）。其本地XLS有149个赛事标题，旧缓存只有60个；本轮读取已保存附件后恢复完整149条，再进行匹配和安全校验。其中59条通过全部规则，其余90条待匹配确认。这个结果不能代表所有学校和政策格式。

76条文档均仍有至少一项需要人工补证或匹配，包括上面已有59条自动关系的文档。常见文档级阻塞计数（可重叠）：有效期依据不足69、学生适用范围不明60、不能确认正式政策55、学校/学院/专业范围不足34、抽取不完整17、没有可靠名单14、正文语义不足12、附件缺失3、已过期3；非官方来源1、来源未验证1、保存的附件不可读/不可用1。未降低这些条件来追求自动量。

PDF复用文本层和定位表格，保留页/表/行证据；文本缺页、跨行不可靠、正文附注与名单边界不明时阻止自动认可。本轮没有运行OCR。DOC/DOCX/XLS/XLSX/HTML复用已有解析器；仅安装requirements已声明的xlrd 2.0.1，没有更改依赖声明。

主field队列与政策条目队列来自不同隔离副本，不能直接相加称为一个去重后的总积压，也不能据此计算管理员每小时吞吐。

## 28：本轮修改文件

以下相对本轮开始文件哈希基线统计，保留之前所有未提交工作。实验数据库、构建副本、截图、运行日志均在忽略目录；运行产生的data/logs/app.log.1不是本轮交付代码。

- `backend/app/api/router.py`（修改）
- `backend/app/api/routes/document_policy.py`（新增）
- `backend/app/schemas/document_policy.py`（新增）
- `backend/app/services/competition_field_ingestion_service.py`（修改）
- `backend/app/services/document_policy_evaluation.py`（新增）
- `backend/app/services/document_policy_service.py`（新增）
- `backend/app/services/field_review_service.py`（修改）
- `backend/app/services/mid_scale_ingestion_service.py`（修改）
- `backend/app/services/policy_automation_service.py`（新增）
- `backend/app/services/policy_competition_matcher.py`（新增）
- `backend/app/services/policy_list_extractor.py`（新增）
- `backend/app/services/policy_resolution_service.py`（修改）
- `backend/app/services/source_document_classifier.py`（新增）
- `backend/app/services/user_facing_data_policy.py`（修改）
- `backend/scripts/evaluate_document_classification.py`（新增）
- `backend/scripts/replay_document_policy.py`（新增）
- `backend/tests/test_document_policy_evaluation.py`（新增）
- `backend/tests/test_document_policy_integration.py`（新增）
- `backend/tests/test_policy_competition_matcher.py`（新增）
- `backend/tests/test_policy_list_extractor.py`（新增）
- `backend/tests/test_source_document_classifier.py`（新增）
- `docs/superpowers/plans/2026-10-01-document-policy.md`（新增）
- `docs/superpowers/specs/2026-10-01-document-policy-design.md`（新增）
- `frontend/src/app/admin/document-policy/page.tsx`（新增）
- `frontend/src/app/admin/page.tsx`（修改）
- `frontend/src/components/DocumentClassification.tsx`（新增）
- `frontend/src/components/FieldReviewDetail.tsx`（修改）
- `frontend/src/components/SchoolRelationReview.tsx`（修改）
- `frontend/src/lib/document-policy-api.ts`（新增）
- `frontend/src/lib/field-review-api.ts`（修改）
- `frontend/tests/document-policy.test.mjs`（新增）
- `docs/DOCUMENT_POLICY_AUTOMATION_REPORT_20261001.md`（本报告）
- `docs/CURRENT_TASK.md`（接续说明）

## 29—33：验证

| 序号 | 验证项 | 结果 |
| --- | --- | --- |
| 29 | 新增测试 | 后端148：分类49、抽取28、匹配6、集成62、人工指标3；前端新增8。 |
| 30 | 后端 | **940项全部通过**，完整pytest汇总940 passed，62.35秒，退出码0。 |
| 31 | 前端 | **65项全部通过**，无跳过、无失败。 |
| 32 | lint/typecheck/build | ESLint、tsc、Next生产构建全部退出码0。构建在独立副本完成，使用8053测试API，未部署。 |
| 33 | 真实浏览器 | **A–I全部通过**，另有分类修正/审计及同页新旧政策刷新验证；Edge + 实际Next/FastAPI，无API拦截。全部为明确功能样例，与真实回放分开。 |

测试覆盖普通通知不生成政策关系、全部认可维度、排除名单、未验证别名、子赛道、失效政策、版本冲突、校院专业范围、来源域名冒充、附件失败、重放幂等、管理员权限、分类修正审计、来源变更失效和赛事事实写保护。自动确认只写政策认可，不改变赛事本体字段。

独立复核发现的10项问题及5个残留边界，已经补测试修复。复核原报告保留当时失败快照；最终关闭依据为补充的回归测试与本轮完整运行，不把旧失败记录删除或改称当时通过。

### 浏览器逐项证据

| 场景 | 最终验证 |
| --- | --- |
| A 公示 | publicity_notice自动分类；无需重新选择类型；来源可见。 |
| B 完赛 | completion_news、informational，主待审队列不包含此材料。 |
| C 介绍 | competition_intro、informational。 |
| D 推免目录 | 提取2项，自动生成2条postgraduate_recommendation_recognition；证据与定位可见。 |
| E 报名 | 只保存participation_evidence；另一个真实字段流程功能样例仍pending，赛事字段未变化。 |
| F 奖励 | 自动生成award_recognition，与推免维度分开。 |
| G 模糊名称 | 先NEEDS_QUICK_CONFIRM；明确选择赛事并填写依据后记为HUMAN_POLICY_MATCH，不计机器自动关系。 |
| H 版本冲突 | 两份文档都显示冲突、自动有效关系0；旧条目待人工审核，旧认可公开可见性为false。 |
| I 延期 | deadline_extension，字段审核HIGH_RISK，提案未自动通过。 |
| 补充 | 分类纠正审计及回放保留；同一页面先分析旧政策，再出现并分析新冲突政策，旧卡片及时变为待审核。 |

完整运行保留9/10加H定位器复测记录；最终H与同页刷新均重新验证通过，合并结果为全部通过。最初功能夹具和定位器问题保留在实验记录中，未作为产品成功或真实样本。详见`../.codex-qa/document-policy/browser-report.md`、`browser-final-summary.json`及`browser-evidence/`截图。

测试网站已重新打开：[来源文档分类与政策分析](http://127.0.0.1:3053/admin/document-policy)。该端口连接**功能样例数据库**，不是真实人工实验、真实历史回放或正式库。原人工8050/3050独立保留。

## 34—36：数据库与部署边界

| 序号 | 项目 | 结果 |
| --- | --- | --- |
| 34 | 正式库SHA256 | 开始/结束一致：`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`。 |
| 34补充 | 原候选库SHA256 | 开始/结束一致：`6bffca4c20f6aaa673246cc1768913cedab789fbd30d4364e0a1f4e64f4a95b6`。 |
| 35 | schema | 没有新增模型表、列或迁移；正式库alembic版本仍为202609060005。整个数据库文件哈希一致也覆盖其schema。 |
| 36 | 正式数据污染 | 未发生；59条自动关系只存在于政策回放副本。没有部署、push、merge、正式事实批量写入、新赛事/高校采集。 |

规则信息复用ReviewQueue JSON和已有AdminAuditLog；政策候选复用ReviewQueue item_type=policy_match；关系复用CompetitionPolicyRecognition usage_type和证据JSON。原候选254条pending没有被改写。

## 37：下一阶段建议与停止点

暂不扩大采集规模。先由真实审核者完成50—100条文档分类标注，优先检查普通通知与正式政策边界，同时抽检这59条自动关系的赛事身份、有效期及范围；然后计算分类指标、审查混淆矩阵并校准阈值。当前规则允许自动关系，不等于自动关系正确率已经经过人工测量。

保留主队列降噪实际仅约0.8%的限制；已有事实提案和学校关系任务不能因标题易分类而消失。后续是否改进证据完整性、政策范围补录或审核流程，需要根据人工记录决定。本轮停止于报告，不继续扩量。

### 复现与人工标注入口

- 真实回放汇总：`../.codex-qa/document-policy/replay-verified/summary.json`。
- 逐来源分类：`../.codex-qa/document-policy/replay-verified/source-replay.json`。
- 逐政策/条目/来源/阻塞依据：`../.codex-qa/document-policy/replay-verified/policy-replay.json`。
- 空白人工表：`../.codex-qa/document-policy/replay-verified/golden-to-label.csv`。填写label、label_provenance=human、reviewer、reviewed_at（ISO日期时间），保留source_id。原表无预测标签，避免直接照抄机器结果。
- 指标文件：`../.codex-qa/document-policy/replay-verified/classification-metrics.json`，当前n=0，所有precision/recall为null。
- 完整检查日志：`../.codex-qa/document-policy/backend-final.log`、`frontend-final-tests.log`、`frontend-final-checks.json`、`build-final.log`。

在人工作业表填好后可以只运行指标计算，不重放或写任何数据库：

```powershell
backend/venv/Scripts/python.exe backend/scripts/evaluate_document_classification.py --labels .codex-qa/document-policy/replay-verified/golden-to-label.csv --predictions .codex-qa/document-policy/replay-verified/source-replay.json --output .codex-qa/document-policy/replay-verified/human-metrics.json
```

标签计算器拒绝未标注、非human来源、缺审核者/时间、未知类型和相互冲突的标签。已用空白表验证不会生成虚假的人工样本。它输出指标；不会仅因样本数够50就自动宣布阈值校准完成。

**DOCUMENT_POLICY_AUTOMATION = BLOCKED**
