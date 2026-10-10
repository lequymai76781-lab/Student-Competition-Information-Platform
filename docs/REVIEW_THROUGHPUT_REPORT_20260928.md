# 审核吞吐优化与高校赛事关系闭环报告

日期：2026-09-28。范围：现有 254 条候选；不扩采、不迁移、不部署、不提交远程。
结论：**功能开发、自动化验证和数据库安全检查通过；阶段验收保留人工吞吐缺口。**

用户本轮确认两项实验调整：真实整条 LOW_RISK 只有 4 条，采用“真实 4 条＋明确合成 50 条”；随后确认“暂时无法操作，保留人工样本缺口”。本报告据此明确人工样本为 0，不把授权安排、自动化点击或 API 时延算作人工实测。

**唯一阻塞项：未取得实际人工审核样本，无法确认低风险、冲突、学校关系的人工吞吐或据此估算扩张人力。**
本轮发现的预览并发、HTTP 准备、政策适用范围及有效期错误均已修复并验证。旧 R12/P2、R13/P3、R14/P3继续保留，不作为本次新增阻塞。

## 1—7. 初始队列与风险数量

| 编号 | 指标 | 实测数量 |
|---|---|---:|
| 1 | 开始时 pending | 254 |
| 2 | LOW_RISK | 4 |
| 3 | HIGH_RISK | 249 |
| 4 | conflict | 9 条候选、5 个字段组、4 个实体/届次组 |
| 5 | no_source | 0 |
| 6 | duplicate_suspected | 14 |
| 7 | 高校关系候选 | 49 |

另有 1 条 NORMAL；冲突、重复标记是风险子集，不能与风险总数相加。no_source=0 只表示有来源记录，不表示来源当前可访问或已经核验。LOW_RISK 也不代表应当批准。

## 8. 实验样本量与计时口径

- **人工：0 条。** 人工副本保持 254 条 pending，没有计时会话或审核决定。只创建隔离测试账户并打开登录页面，未代替用户操作审核。
- **真实候选自动化计时：36 条。** 低风险 11/39/49/70；单来源 5/10/17/22/34/44/53/63/67/82；跨候选一致 1/16/31/38/47/58/64/68/74/75；冲突 27/54/56/57/83；学校通知 206/210/213/217/234；赛事 51 的全部现有候选 143/144。
- **真实政策功能验证：2 条。** 212/221，未启动计时，不混入吞吐均值。
- **合成压力：50 条。** 单独数据库、候选 255—304，标题明确为合成样本，不算新增真实赛事或真实审核量。

本库“单候选内同字段两个不同 URL 且一致”的样本为 **0**；跨候选同字段一致有 24 组，选用 10 组对照，不把同一来源支持多个字段充作多个来源。来源组与候选数量分别统计。

计时服务以服务器时间记录明确开始、打开来源、首次选择决定、提交及真实完成；批量只有一份墙钟时间。部分处理、暂缓、中断和未知时长不混入完成均值。来源点击只证明操作，不证明已阅读。人工数据若后续补录，仍需标注从“开始计时”到完成的边界；初次进入页面前的思考时间未计入。

机器路径另记录详情打开时间、原文打开、提交和总 UI 时长。机器汇总如下，单位秒，**不能作为管理员产能**：

| 自动化类别 | 完成样本 | 平均 | 中位数 | P90 |
|---|---:|---:|---:|---:|
| 真实低风险 | 4 | 7.93 | 7.50 | 11.86 |
| 普通单来源 | 10 | 12.54 | 12.78 | 14.53 |
| 跨候选同字段多源一致 | 10 | 31.96 | 14.70 | 43.80 |
| 冲突候选 | 5 | 16.44 | 12.80 | 30.39 |
| 学校通知关系 | 5 | 4.88 | 4.88 | 5.46 |
| 单赛事内候选 | 2 | 5.10 | 5.10 | 7.92 |

跨候选一致组中有原文弹窗失败后的恢复等待，计时会话保留该墙钟成本；均值高于中位数，不删除失败等待来美化数字。候选 56 的提交后只读连接曾中断，恢复时依据服务器终态和审计，不重复批准；该项 UI 总时长记为未知，服务器完成耗时仍可核实。

## 9. LOW_RISK 平均审核耗时

人工：**未测得，N=0**。真实 4 条自动化均值 7.93 秒。49 的历史频率备注包含新赛制歧义，实验模拟拒绝，其他 3 条走批准；没有降低风险条件凑足 20 条。

## 10. LOW_RISK 中位审核耗时

人工：**未测得**。自动化中位 7.50 秒，P90 11.86 秒，N=4。

## 11. conflict 平均审核耗时

人工：**未测得，N=0**。5 个真实冲突样本自动化均值 16.44 秒，中位 12.80 秒。名称或地点粒度差异保留为可对照证据，不自动判定来源胜负。

## 12. 高校关系平均审核耗时

人工：**未测得，N=0**。5 条真实学校通知自动化均值 4.88 秒。2 条政策仅验证闭环，缺计时开始，不推导为零秒。

## 13. 单管理员每小时实测吞吐估算

低风险、普通、冲突、学校关系四类的人工条/小时均为 **未知**。统计页按 human/automation 分组，只有已完成会话参与均值、中位数、P90和理论每小时量；成功审核却无开始时间单列未知。

普通单来源中只有 1 条单字段候选完成样本，其自动化耗时 13.05 秒；不是“人工平均单字段耗时”。10 条单来源连续 UI 流程总计 134.63 秒。赛事 51 当前两条候选完整处理 UI 用时 12.16 秒，只表示本库该赛事现有候选处理完，不表示赛事资料已完整。

## 14. 批量审核效率与事务

50 条合成候选跨 3 页选择约 1.61 秒，选择到成功刷新共 6.21 秒；明确开始整批计时后的摘要/确认/原子提交墙钟 4.05 秒。来源核验已在此前 102 次真实 HTTP 准备请求中完成，准备约 4.62 秒；这些阶段没有冒充 50 份人工阅读。

真实 UI 显示候选、赛事/学校、字段、中文来源类型、已有值、冲突及核验状态。跨实体、跨来源可以批量，但整条必须 LOW_RISK、字段空值补全、所有所选来源核验通过，最多 50 条；高风险和关系候选禁止混入。

采用**整批原子事务**。20 条中第 19 条注入失败后，成功 0、全部仍 pending、正式值/修订/审计无半成功；错误返回失败候选和保留 ID。预览后新增外部冲突或正式值变化会拒绝旧预览。先前错误归因到最后一条的问题已用首目标锁失败测试修复。

## 15. 审核积压模型

以实测人工分类占比 p 和每条耗时 t 建模，平均 t = Σ(p类 × t类)，其中 Σp=1：

| 每日新增候选 | 每日净审核小时 | 按8小时净审核折算 |
|---:|---|---|
| 100 | t / 36 | t / 288 人日 |
| 500 | t / 7.2 | t / 57.6 人日 |
| 1000 | t / 3.6 | t / 28.8 人日 |

t 单位秒；当前 t 未取得，**不填虚假的人数**。休息、补证、来源故障和积压返工还会增加排班需求。上一阶段新增147条、当前真实主候选库254条均保持待审；隔离实验批准不减少这份真实积压。不能把采集或自动化 API 速度直接等同人工消化速度。

## 16. 来源核验体验

原始链接一键打开，展示标题、类型、发布机构、发布时间、采集时间、访问观察时间和证据片段；可达性与人工核验分开。真实数据脚本记录50次打开链接，其中26次未在探针等待窗口内得到新页面/正文完成状态，按实际限制保留，不自动判源无效，也不写成已读。

两条政策原文另行验证均HTTP200、标题匹配、正文可读。管理员核验身份与完整证据留在审计；公开正式来源使用字段白名单，不输出候选ID/核验管理员ID。

## 17. 来源时间线

同一字段展示本地及跨候选证据，按发布时间、采集时间排序；突出延期、更正、补充字样，标明校内截止/赛事官方届次/赛事本体。不同字段语义不会仅因日期不同直接冲突。同值外部证据不再误标为冲突。

详情时间线/外部证据初始最多50项，可通过来源API分页继续查看。新来源会改变预览令牌。只有明确报名通知、带时分时区的校内截止写入业务时间列；日期级、选拔或其他含义保留原文/精度，不能改全国截止。

## 18. 高校赛事关系正式批准流程

等价 school_mapping 候选 → 确认学校/赛事/届次/材料类型 → 必要时保存准备 → 打开原文并核验 → 单条批准、拒绝或暂缓 → 正式关系与审计同事务。

普通通知写入 UniversityCompetitionEditionRelation；同学校、赛事、届次和类型重复证据合并来源，不创建重复关系。未知或错误届次、关系冲突阻止批准，允许明确拒绝/暂缓。5条真实通知已在自动化副本批准并通过查询确认；正式库不变。

真实 HTTP prepare 对省略字段的 Pydantic 处理错误已修复：保留 exclude_unset 语义；已知身份不能显式清空或替换。新增通知、补年份、政策准备真实HTTP成功路径，显式空身份仍409。

## 19. policy_recognition 流程

单独确认政策范围、学生范围、认定条款及有效期，核验后写入既有 PolicyDocument 和 CompetitionPolicyRecognition；不复制为每届通知。历史未确认有效保存历史表达，研究生范围不自动扩为本科。

212/221真实UI先后完成准备、核验、批准；均保存 historical_recognition/is_current=false，分别保留本科历史/研究生历史范围。公开 resolve 返回 insufficient_evidence、需要人工核实；当前认可列表未增加。

本轮还修复两类直接相关公开查询错误：历史或研究生材料不能兜底为“当前政策未提及”；新审核政策每次公开解析均检查当前范围及有效期，过期/未到生效期不能继续 recognized。正向结果和兜底共用检查，旧无新关系元数据的历史策略不作全仓重写。

## 20. 普通通知与正式认定隔离

普通通知表单没有政策范围输入，尝试通过关系准备API额外提交 policy_recognition 类型返回422。5条通知未提升认定，2条历史政策未新增届次通知。运行时写保护覆盖正式关系、政策文档和认定表，未审核写入被拒绝；既有未适配直写调用会明确报错。

## 21. 分页、搜索、筛选

队列20条一页；真实254条可读取最后14条；521条夹具验证超过500的搜索/分页和查询数量，浏览器50条跨三页选择不丢失。支持状态、风险/冲突、赛事、学校、关系类型、来源类型、提交人、日期与排序。

搜索赛事名、学校名、字段内部名及中文显示名、来源标题；“举办频率”中文搜索有RED→GREEN回归。批准后局部更新队列、统计及详情。实际409失败保留选择、意见、风险筛选和页码；500/网络失败恢复另由前端交互测试覆盖。

## 22. 性能观察

254候选只读 TestClient/API 实测中位：默认列表52.63ms/12 SELECT；风险筛选65.26—73.04ms/12；统计65.33ms/14；字段详情16.78ms/15；学校关系详情15.88ms/14；来源14.74—16.27ms/14—15；审计12.66ms/7。该次审计历史为空，不能代表海量审计性能。

关系49条详情请求内批量预载从250次SELECT降为9次。读缓存仅在请求范围生效，写操作清除缓存并使用新鲜快照。风险/统计仍需在服务端扫描候选JSON，属于规模边界；浏览器不接收全部候选或全部外部来源。以上是本机小规模指标，不是生产SLA，也未声称解决旧R12。

## 23. 本轮修改文件

按本轮开始文件哈希与当前文件比较，保留此前已有改动。完整清单同步在 review-throughput/VALIDATION.json；旧中文原始附件未被本轮重写或采集。
- README.md
- backend/app/api/routes/field_reviews.py
- backend/app/core/exceptions.py
- backend/app/database/review_guard.py
- backend/app/schemas/review_telemetry.py
- backend/app/schemas/school_relation_review.py
- backend/app/services/field_review_service.py
- backend/app/services/policy_resolution_service.py
- backend/app/services/review_bulk_service.py
- backend/app/services/review_queue_query.py
- backend/app/services/review_telemetry_service.py
- backend/app/services/school_relation_review_service.py
- backend/tests/test_field_ingestion.py
- backend/tests/test_field_review.py
- backend/tests/test_real_data_pilot.py
- backend/tests/test_review_policy_resolution_scope.py
- backend/tests/test_review_telemetry.py
- backend/tests/test_review_throughput.py
- backend/tests/test_review_throughput_api_access.py
- backend/tests/test_school_relation_review.py
- docs/CURRENT_TASK.md
- docs/REVIEW_THROUGHPUT_REPORT_20260928.md
- docs/review-throughput/VALIDATION.json
- docs/superpowers/plans/2026-09-28-review-throughput.md
- docs/superpowers/specs/2026-09-28-review-throughput-design.md
- frontend/src/app/admin/field-review/page.tsx
- frontend/src/components/FieldReviewBatch.tsx
- frontend/src/components/FieldReviewDetail.tsx
- frontend/src/components/ReviewTelemetry.tsx
- frontend/src/components/SchoolRelationReview.tsx
- frontend/src/lib/field-review-api.ts
- frontend/src/lib/v09-api.ts
- frontend/tests/api-security.test.mjs
- frontend/tests/field-review.test.mjs
- frontend/tests/review-throughput.test.mjs

## 24. 新增测试

后端新增风险/原子事务/时间线/521分页测试、41项学校关系（含5项真实HTTP准备边界）、33项计时、36项接口鉴权、13项政策范围和时效HTTP回归。既有批量测试按本轮明确允许跨实体/来源调整，既有政策 fixture 显式走测试写保护上下文；没有降低运行时保护。

前端新增批量筛选、跨页保留、学校关系、真实React状态、计时模式锁定、会话失效重启、部分字段/混合决定完成边界、中键来源事件和来源类型断言。独立复查补充了事务与账号隔离探针。

## 25. 后端测试结果

最终完整测试：**792 passed，50.79秒**。命令在 backend 目录执行 venv/Scripts/python.exe -m pytest tests -o addopts='' -q。最终日志：.codex-qa/review-throughput/backend-final-full.log。

## 26. 前端测试结果

最终代码完整测试：**57 passed，0 failed**。使用环境已有Playwright运行库；一次缺NODE_PATH导致的启动失败已查明并重跑，无安装依赖。最终日志 final-isolated-frontend-tests.log。

## 27. lint / typecheck / build

全部通过。最后来源类型改动后再次lint、完整前端测试、typecheck和显式8050 API生产build。隔离构建src与原src逐文件哈希一致，仅副本配置调整Turbopack共同依赖根，复用已有node_modules。当前项目.env.local未改。

## 28. 浏览器验证结果

- 真实候选主脚本 **9组通过**：登录/254分页、4低风险、10普通单来源、10跨候选一致、5冲突、5通知、完整赛事当前2候选、通知类型隔离、409失败恢复。
- 50合成候选：跨三页摘要与原子批准、清空选中和队列实时更新通过。
- 2条真实历史/研究生政策：UI闭环、匿名公开查询通过；最后有效期补丁重启后2条公开查询再次通过。
- 最终生产构建：批量摘要中文来源类型和未核验禁止批准通过。
- 模式锁定、会话失效后重启、账号切换清理有独立浏览器探针。没有把模拟HTTP的组件测试冒充真实服务浏览器实验。

真实服务浏览器API仅透明重定向到各自隔离副本，未伪造成功响应。政策与通知均在副本完成，批准结果不回放生产。

## 29. 数据库 SHA256

正式 data/v02.sqlite，前后相同：

9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320

原主候选库 .codex-qa/mid-scale/candidates.sqlite，前后相同：

6bffca4c20f6aaa673246cc1768913cedab789fbd30d4364e0a1f4e64f4a95b6

测试使用隔离fixture；浏览器分别使用manual/automation/synthetic副本。只读盘点使用mode=ro与query_only；没有用正式数据库跑测试。

## 30. schema 是否变化

**没有。** 复用ReviewQueue JSON、AdminAuditLog和既有关系/政策表；未新增表、迁移文件或运行正式迁移。

## 31. 正式数据污染

**没有。** 正式库及主候选库字节哈希一致。自动化批准只在实验副本；合成库额外50个测试赛事夹具与候选明确命名，不当成真实覆盖数据。未生产清理、未生产修正、未部署、未push/merge。

## 32. 是否支持进一步扩张

接口与流程已证明可处理当前规模和521条隔离夹具，**没有证明人工组织能消化扩量**。由于人工样本0、来源访问仍有失败，暂不据此启动更大规模采集。

## 33. 下一阶段建议与停止点

仅建议后续补一组真实管理员计时：至少覆盖4条现有低风险、冲突及学校关系，记录来源失败、拒绝与暂缓，不强迫批准。获得样本后重算第9—15项，再判定是否解除阶段验收阻塞。

用户已选择本轮保留该缺口。本轮测试服务及专用人工窗口已停止，副本/脚本/证据保留；不再索取开发批准、不继续采集、不自动进入下一阶段。代码修复、自动化验证及本报告已交付；人工产能验收仍未完成。

**REVIEW_THROUGHPUT = BLOCKED**

唯一真正阻塞项：缺少实际人工计时样本，无法给出实测人工吞吐与人力积压估算。

---

证据索引（忽略目录，保留本地，不含在可提交报告内的临时凭据）：
before.json、sample-inventory.json、statistics-before.json、experiment-summary.json、performance.json、browser-results.json、synthetic-browser-results.json、policy-browser-results.json、policy-public-final.json、final-source-type.json、backend-final-full.log、final-isolated-frontend-*.log、security-review.md。
