# 中规模试点来源与重放说明

2026-09-28；结论见 [试点报告](../MID_SCALE_DATA_EXPANSION_REPORT_20260928.md)。本目录是可审查研究清单，不是已核验正式事实。全部新候选仍待审；来源等级不能替代人工来源核验。

## 文件与口径

- `competitions-a.json`、`competitions-b.json`：56 个既有赛事、73 条来源记录；与前阶段 24 个赛事合计 80 个选定赛事。其中合计 69 个已有结构化字段提案，11 个只保留线索材料。
- `universities.json`：30 校内部取样资料；未知类型/政策用 null，未查到不等于不存在。
- `school-sources.json`：47 条学校来源；`school-years.json`：额外 2 条历史通知，用于验证同校跨年隔离。合计 49 条映射候选。
- `*-notes.md`：原始研究范围、正文证据、失败与限制。高校原始笔记的 47 条口径不包含后来补充的 2 条历史通知。
- [学校逐校覆盖表](SCHOOL_COVERAGE.md)、[80 个赛事覆盖表](COMPETITION_COVERAGE.md)：本轮真实覆盖、资料缺口和来源入口。

字段 `access_status=readable` 表示研究时取得支持备注的正文；不代表全部附件解析成功或人工 VERIFIED。只拿到搜索摘要、标题或目录的材料不会产生确定事实。`published_at` 保留原日期精度，`accessed_at` 是本次研究读取/尝试时间；未知赛事年份保持空值。原始来源类型别名和失败描述保存在 `source_type_original`、`source_failure_detail`（适用时）。

学校材料的 `university_notice.notice_type` 分别保留报名、组织、选拔、推荐、政策认定、奖励、转载和其他；`is_formal_recognition` 仅说明存在针对该赛事的明确原文条款，仍要核验适用范围、有效期和身份。它不代表正式库已认定。

## 候选库与写保护

主库为仓库内 `.codex-qa/mid-scale/candidates.sqlite`，由此前的独立试点库复制，保留原 107 条待审记录；新增 147 条后共 254 条 pending。独立浏览器副本为同目录 `browser.sqlite`，仅该副本进行一例两字段的低风险批准。不能用浏览器副本替代待审主库。

新工具仅接受 **已经存在** 的 `.codex-qa/mid-scale/*.sqlite`，设置测试环境并检查数据库目标；不会自动建库、迁移或复制正式库。没有该本地库时，应由受控测试 fixture 建立隔离库，不能把参数改成正式库。测试脚本和临时数据库均在 git 忽略目录中，未加入交付文件。

学校关系仍为结构化待审材料，支持查看/筛选/拒绝；本轮未实现学校关系正式批准入口，不能将其“整理”为赛事本体字段。未知届次或明确年份但正式届次不存在时，不会绑定最新届次。

## 已执行的任务与使用方式

从仓库根目录用 PowerShell 运行以下形式（均只针对已存在的隔离库）：

```powershell
# 新任务处理前三条后暂停；--probe-links 为有上限的逐来源 GET
backend/venv/Scripts/python.exe backend/scripts/import_mid_scale.py --database .codex-qa/mid-scale/candidates.sqlite --manifest docs/mid-scale/competitions-a.json --max-items 3 --probe-links
# 依据上一命令输出的 job_id 恢复，不重复创建任务
backend/venv/Scripts/python.exe backend/scripts/import_mid_scale.py --database .codex-qa/mid-scale/candidates.sqlite --job-id 1 --probe-links
# 查询状态
backend/venv/Scripts/python.exe backend/scripts/import_mid_scale.py --database .codex-qa/mid-scale/candidates.sqlite --job-id 1 --status
# 对失败项重试；也可使用 --item-key <状态记录中的键> 限定单项
backend/venv/Scripts/python.exe backend/scripts/import_mid_scale.py --database .codex-qa/mid-scale/candidates.sqlite --job-id 1 --retry-failed --probe-links
# 学校清单采用 --school-manifest
backend/venv/Scripts/python.exe backend/scripts/import_mid_scale.py --database .codex-qa/mid-scale/candidates.sqlite --school-manifest docs/mid-scale/school-sources.json --max-items 10 --probe-links
```

例中 `1` 是本次已执行任务号；新环境必须使用实际返回 ID。进程异常且租约已过期时，才可对同一任务使用 `--recover`；仍持有有效租约时不抢占。每条来源的候选与检查点同事务提交，并以租约所有者比较更新，失去租约的旧进程不能覆盖新结果。

任务复用 `crawler_jobs`；metadata 保存来源快照、身份、起止时间、状态、候选 ID、失败、重试历史。无新任务表。每任务最多 500 条来源，HTTP 超时 4 秒、读取上限 1 MiB；不进行链接递归发现，不关闭证书校验。

幂等键排除抓取时间及清单展示 key；相同材料重放复用候选，原文内容变化形成新版本。不同来源的零字段材料保持各自出处。已处理候选也不会被重放重置回 pending。

## 失败与状态解释

研究工具取得正文和本地 HTTP GET 是两次不同观察：前者 83/122 有正文，后者最新一次为 24/122 返回 HTTP 200。失败保留在来源与任务记录，不能相互覆盖为成功。未开启 `--probe-links` 的重放不声称完成新抓取。

`completed` 只表示清单处理完成；应同时检查 `source_failures`、`failures` 与逐项 `fetch_result` / `attempt_history`。候选详情保留研究时失败；后续 HTTP 重试结果以任务状态为准。内部任务不通过公开政策 jobs API 暴露，使用本地状态命令查看。

本轮已完成分段暂停/恢复、122 条完整重放（新增 0、复用 147）和单项失败重试。更大规模采集尚不建议启动；人工吞吐、学校关系批准能力及冲突查询仍需后续任务安排。
