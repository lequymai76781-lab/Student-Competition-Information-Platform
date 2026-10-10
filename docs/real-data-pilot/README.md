# 真实赛事资料小批量压测（2026-09-27）

本轮固定 24 个现有赛事，不新增正式实体。正式数据库只读；候选进入独立审核库，浏览器审批使用另一个副本。全部来源默认未核验，禁止自动批准生产数据。

## 样本分组

- A：1 创新大赛、2 挑战杯课外作品、3 挑战杯创业计划、4 数学建模、19 大广赛、21 三创赛、29 市场调查、43 NCDA。
- B：5 电子设计、8 ICPC、10 机械创新、11 结构设计、20 智能汽车、27 化工设计、32 西门子杯、34 计算机设计。
- C：17 数据新闻、18 体育科普、24 外研社国才杯、36 蓝桥杯、39 光电设计、47 中国软件杯、145 模拟法庭、154 大学生攀岩。

## 来源清单约定

各组写入 `sources-a.json` / `sources-b.json` / `sources-c.json`：顶层为赛事数组。

每条赛事：`competition_id`, `name`, `reason`, `aliases`（仅有证据的别名）, `sources`。

每条来源：`key`, `url`, `title`, `publisher`, `source_type`, `published_at`（ISO 日期或 null）, `accessed_at`（ISO 日期时间）, `access_status`（readable / blocked / unavailable）, `year`（明确届次年份或 null）, `competition_fields` 对象, `edition_fields` 对象, `evidence_notes`（简明释义；不复制全文）, `university_notice`（可为 null）。高校通知对象：`university_name`, `notice_type`, `is_formal_recognition`, `school_deadline`（可为 null）。日期不详保持 null；日精度日期候选记录为当日 00:00，备注原文精度；明确时刻保留时刻。

字段只提取可核对事实。来源类型：official_website / organizer_notice / government_document / university_notice / university_policy / industry_organization。学校发布的全国赛通知仍为 university_notice；组织报名不等于认定。校内截止只存高校通知元数据，不写全国截止。

每赛事至少一个读到正文的可靠来源，尽量 2–3 个；重点样本收集两届以上、多个高校、历史和真实延期。链接阻断也记录，但不将未读到内容作为已查证事实。既有库值不是新来源证据。

## 执行与验收

1. 正式库只读盘点及 SHA256 基线。
2. 24 个样本来源核查与字段提取，保留矛盾和缺失。
3. 运行时受保护会话导入独立候选库；前后正式表内容一致；重复导入幂等。
4. 16 类定向测试，必要修复遵循失败测试先行。
5. 浏览器查看全部样本；5 个代表赛事闭环，在副本审批与公开详情验证。
6. 完整后端、前端、lint、typecheck、build 与正式库校验；形成最终报告，停止扩量。

## 已完成与保留资料

最终报告：`../REAL_DATA_PILOT_REPORT_20260928.md`。本轮 24 个赛事、74 条来源记录（73 个唯一原文 URL）、107 条候选、252 个字段提案。

- `.codex-qa/real-data-pilot/candidates.sqlite`：独立待审库，107 条全部 pending，保留给人工审核。不是正式库的审核队列。
- `.codex-qa/real-data-pilot/browser.sqlite`：浏览器验证副本，7 条部分批准，其余 100 条 pending。不能将此副本批准结果视为生产审批。
- 同目录保存盘点、基线、HTTP 检查、导入结果、测试日志、浏览器结果和截图；该目录受 Git 忽略，包含合成管理员凭据，不提交。

仅向已经建立的隔离库重放清单（从 `backend` 目录）：

```powershell
.\venv\Scripts\python.exe scripts/import_real_data_pilot.py --database ../.codex-qa/real-data-pilot/candidates.sqlite
```

命令限制目标在本轮隔离目录、要求数据库已存在，不建表、不迁移、不批准；相同资料重复导入不会新增候选。正式库保留原样。资料仍默认未核验，HTTP 可访问和已读正文分别记录；来源正文可读不等同于管理员正式批准。
