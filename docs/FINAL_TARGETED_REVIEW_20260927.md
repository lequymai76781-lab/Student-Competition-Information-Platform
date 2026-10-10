# 阶段最终定向复核报告

日期：2026-09-27。范围：仅 R06、R12、R13、R14。结论：**【建议批准本阶段改动】**。

依据：[独立审查报告](D:/Python/xuesheng/docs/INDEPENDENT_REVIEW_20260927.md)、[安全与数据一致性修复报告](D:/Python/xuesheng/docs/SECURITY_DATA_CONSISTENCY_FIX_REPORT_20260927.md)、当前代码，以及本轮重新执行的测试和浏览器/API 证据。原报告保留历史结论，本报告给出最终阶段判断。未重新开展全仓审计。

| 问题 | 原级别 | 本轮最终状态 | 是否阻塞本阶段 |
| --- | --- | --- | --- |
| R06 | P2 | CLOSED | 否，已修复并回归 |
| R12 | P2 | PARTIALLY FIXED | 否，仍有规模增长时的性能债务 |
| R13 | P3 | OPEN | 否，UI 不提供 unknown 筛选 |
| R14 | P3 | OPEN | 否，手工重复参数触发，正常表单与恢复路径通过 |

## 1. R06 原始问题

原报告 D/R06：首页状态计数与状态筛选列表使用不同的赛事集合。同一赛事的 2026 届仍在报名、7 天后截止，2027 届明天开始报名。未筛选列表选择动作更近的 2027 届；统计从该代表届次计数，得到报名中 0，而报名中列表返回 2026 届 1 条。作品提交计数存在相同错误。

## 2. R06 当前状态

**CLOSED**。修复 [stats_repository.py:52](D:/Python/xuesheng/backend/app/repositories/stats_repository.py:52) 和 [competition_service.py:119](D:/Python/xuesheng/backend/app/services/competition_service.py:119)：报名中、作品提交中分别按列表共用的已核验届次、当前日期及截止解析规则匹配；每种状态下每场赛事只计一次。

复用同一个候选赛事查询和 `_current_edition(required_status=...)`，不再从未筛选卡片的代表届次推导计数。不改变默认列表的届次选择、不改变审核或核验规则、不写入源数据。

## 3. R06 验证证据

失败复现 → 失败测试 → 根因修复 → 回归完成：

- 修复前新增 9 项测试中 2 项失败、7 项通过；报名、作品提交两种多届次场景均为列表 1、统计 0。证据：[r06-red.txt](D:/Python/xuesheng/.codex-qa/final-targeted-review/r06-red.txt)。测试脚本最初使用超出 API 上限的 limit，已纠正为 100；上述红灯记录来自合法请求，失败原因是 `0 != 1`。
- 修复后，新增 9 项及原核心流程 19 项，共 28 项通过。覆盖多届次、同赛事去重、待审届次、待审赛事、演示赛事、过期届次和超过默认 50 条分页的计数。证据：[r06-green.txt](D:/Python/xuesheng/.codex-qa/final-targeted-review/r06-green.txt)。
- 独立合成库：默认列表选择待开始届次 12/22；报名筛选返回届次 11、提交筛选返回届次 21，各 1 场，`/api/stats` 对应均为 1。证据：[probe-results.json](D:/Python/xuesheng/.codex-qa/final-targeted-review/probe-results.json)。
- 真实浏览器从首页进入报名/提交列表，再进入详情，分别保留 `edition_id=11/21`；桌面及手机报名计数均为 1。证据：[browser-results.json](D:/Python/xuesheng/.codex-qa/final-targeted-review/browser-results.json)、[首页截图](D:/Python/xuesheng/.codex-qa/final-targeted-review/home.png)、[报名列表截图](D:/Python/xuesheng/.codex-qa/final-targeted-review/registration-list.png)。

## 4. R12 原始问题

原报告 D/R12：列表即使请求 `limit=1`，仍加载全部候选赛事和关联 ORM 对象，逐条构建卡片后才分页；统计接口也调用全量列表构建。数据增长时，查询数、对象数量与计算成本增长。

## 5. R12 当前状态

**PARTIALLY FIXED**。R06 修复使统计接口不再构建赛事卡片，本轮统计探针的卡片序列化数为 0；但列表仍先全量构建再分页，统计也仍加载全部候选对象。全量加载问题未关闭，仍记 P2。

本轮不进行查询架构重写。合成 176 条规模及核心浏览器流程没有出现阻塞或错误结果，原审查也将其列为可按规模分步优化的问题。此结论只支持当前阶段验收，不等同于并发、大数据量或部署 SLA 验证。

## 6. R12 验证证据

在独立内存库创建 N 个已核验赛事、每场一个有效届次，通过真实 FastAPI 路由测量；每个请求使用新的 Session，统计 SQL、加载对象和卡片构建次数。所有请求 HTTP 200。

| 合成赛事数 | 列表 limit=1 耗时/SQL | 列表加载赛事+届次 | 列表构建卡片/返回条数 | stats 耗时/SQL | stats 加载赛事+届次 | stats 构建卡片/报名计数 |
| --- | --- | --- | --- | --- | --- | --- |
| 176 | 0.0983s / 8 | 176+176 | 176 / 1 | 0.0392s / 44 | 176+176 | 0 / 176 |
| 200 | 0.0420s / 8 | 200+200 | 200 / 1 | 0.0419s / 44 | 200+200 | 0 / 200 |
| 2,000 | 0.4089s / 29 | 2,000+2,000 | 2,000 / 1 | 0.3175s / 65 | 2,000+2,000 | 0 / 2,000 |
| 5,000 | 0.8711s / 71 | 5,000+5,000 | 5,000 / 1 | 0.9269s / 107 | 5,000+5,000 | 0 / 5,000 |

证据：[探针脚本](D:/Python/xuesheng/.codex-qa/final-targeted-review/probe.py)、[测量原始结果](D:/Python/xuesheng/.codex-qa/final-targeted-review/probe-results.json)。176 取自已有目录规模报告；以上数据全部为合成数据，不是正式库性能测试。耗时为本机单次观测，不能据此推导性能提升比例或容量保证。浏览器额外确认正常列表可用，HTTP limit=1 只返回 1 条；响应大小有界不代表数据库加载量有界。

## 7. R13 原始问题

原报告 E/R13：`edition_status=unknown` 将本来有已知状态的赛事纳入结果。状态过滤后无匹配届次时，`_current_edition` 返回 None，后续 None 被转为 unknown，又通过最终过滤，导致返回无届次、无截止的赛事卡片。

## 8. R13 当前状态

**OPEN**，P3。当前 [competition_service.py:101](D:/Python/xuesheng/backend/app/services/competition_service.py:101) 仅在来源或年份筛选时排除无匹配届次结果，该问题仍存在。本轮记录，不修改此 API 边界行为。

其影响为直接使用 unknown 参数时的错误结果；正常 UI 状态筛选未提供该选项。它不会把待审届次升级为正式事实，也不改变已有正式届次数据。本轮正常报名、提交及详情链路通过，不因此阻塞阶段收口。

## 9. R13 验证证据

- 两场合成赛事的所有届次均为已知状态：当前届分别正在报名/提交，下一届均待开始。
- `/api/competitions?edition_status=unknown` 仍 HTTP 200 返回两场赛事，均为 `current_status=unknown`、`current_edition_id=null`、`action_deadline=null`。这是缺陷复现，不能算行为正确。
- 同一库的报名/提交筛选各返回正确的 1 条及正确届次。
- 浏览器检查 `select[name="edition_status"]`：unknown 选项数量为 0。

证据：[API 结果 unknown/default/open/submission](D:/Python/xuesheng/.codex-qa/final-targeted-review/probe-results.json)、[浏览器第 5 项](D:/Python/xuesheng/.codex-qa/final-targeted-review/browser-results.json)。

## 10. R14 原始问题

原报告 E/R14：Next 接收重复查询参数时会提供字符串数组，页面却按字符串调用 `source_scope.startsWith`。访问 `/competitions?source_scope=official_current&source_scope=university_notice` 触发异常页。

## 11. R14 当前状态

**OPEN**，P3。[competitions/page.tsx:41](D:/Python/xuesheng/frontend/src/app/competitions/page.tsx:41) 仍未规范化重复参数。本轮没有修改前端业务代码。

普通表单只产生一个 source_scope，浏览及筛选正常。错误仅作用于该次异常 URL，请求正常列表后可恢复；本轮未观察到数据写入或持久损坏。它是明确保留的输入健壮性缺陷，不作为本阶段阻塞项。

## 12. R14 验证证据

- Edge/Playwright 实际访问原报告相同 URL，页面显示“页面暂时无法加载”。
- 此次请求新产生一条服务端 `TypeError: resolvedSearchParams.source_scope?.startsWith is not a function`。
- 普通表单选择 official_current、点击“应用筛选”，URL 中 source_scope 数量为 1，正常显示 2 场合成赛事；异常 URL 后再次进入正常列表恢复。
- SSR 流式响应在该错误场景仍记录 HTTP 200，不能仅凭响应码认定页面成功；本轮使用实际错误页与新增服务端异常共同判定。

证据：[错误页截图](D:/Python/xuesheng/.codex-qa/final-targeted-review/r14-duplicate-query.png)、[服务端日志](D:/Python/xuesheng/.codex-qa/final-targeted-review/frontend-server.txt)、[浏览器第 5–7 项](D:/Python/xuesheng/.codex-qa/final-targeted-review/browser-results.json)。初版探针误要求已被 React 错误边界捕获的异常触发 pageerror，已修正为检查错误页和新增服务端日志；未因此修改产品代码或掩盖缺陷。

## 13. 本轮是否修改代码

**是。仅修复 R06 核心计数错误。** 修改 2 个后端业务文件、新增 1 个后端测试文件；另更新 2 份状态文档并新增本报告。未重构列表查询，未修复 R13/R14，未启动新功能。

## 14. 修改文件

| 文件 | 本轮改动 |
| --- | --- |
| [competition_service.py](D:/Python/xuesheng/backend/app/services/competition_service.py:119) | 新增按共用届次规则、每赛事去重的状态计数 |
| [stats_repository.py](D:/Python/xuesheng/backend/app/repositories/stats_repository.py:52) | 使用上述计数，替换未筛选代表届次计数 |
| [test_remaining_issue_review.py](D:/Python/xuesheng/backend/tests/test_remaining_issue_review.py) | 新增 9 项 R06 回归 |
| [README.md](D:/Python/xuesheng/README.md) | 更新最新验证结果和阶段结论 |
| [CURRENT_TASK.md](D:/Python/xuesheng/docs/CURRENT_TASK.md) | 记录阶段收口及保留问题，等待用户下一阶段指令 |
| [本报告](D:/Python/xuesheng/docs/FINAL_TARGETED_REVIEW_20260927.md) | 新增定向复核证据与批准判断 |

临时探针、合成库、日志及截图位于被忽略的 `.codex-qa/final-targeted-review/`；不加入业务仓库改动。保留原工作区已有改动，未提交、push 或 merge。

## 15. 新增测试

正式测试 9 项：报名/提交多届次计数 2 项；报名/提交同赛事多匹配届次去重 2 项；待审届次、待审赛事、演示、过期排除 4 项；超过默认页大小的 52 场计数 1 项。

另有本地诊断：8 组 API 规模测量、R06/R13 API 数据断言、8 项浏览器核验。R13/R14 的复现断言仅用于记录现状，没有将缺陷行为写成正式产品契约测试。

## 16. 测试结果

| 检查 | 本轮结果 | 证据 |
| --- | --- | --- |
| R06 修复前合法请求 | 2 失败、7 通过；失败值均 0 != 1 | [红灯日志](D:/Python/xuesheng/.codex-qa/final-targeted-review/r06-red.txt) |
| R06 + 原核心流程 | 28 passed，1.84s | [定向回归](D:/Python/xuesheng/.codex-qa/final-targeted-review/r06-green.txt) |
| 后端完整 pytest | 458 passed，25.66s，退出 0 | [完整后端日志](D:/Python/xuesheng/.codex-qa/final-targeted-review/backend-full.txt) |
| 前端 npm test | 30 passed、0 failed，46.03s，退出 0 | [前端测试日志](D:/Python/xuesheng/.codex-qa/final-targeted-review/frontend-tests.txt) |
| npm run lint | 退出 0 | [lint](D:/Python/xuesheng/.codex-qa/final-targeted-review/frontend-lint.txt) |
| npm run typecheck | 退出 0 | [typecheck](D:/Python/xuesheng/.codex-qa/final-targeted-review/frontend-typecheck.txt) |
| npm run build | Next 16.3.3 编译、类型检查、18/18 静态页面生成通过，退出 0 | [build](D:/Python/xuesheng/.codex-qa/final-targeted-review/frontend-build.txt) |
| git diff --check | 退出 0；只有现有 CRLF 提示 | 本轮命令输出 |

后端命令：在 backend 运行 `venv/Scripts/python.exe -m pytest -o addopts='' -q`。前端使用既有测试脚本及已安装的 Playwright 运行时。构建时 API 指向本轮隔离服务；未修改 .env 或真实密钥。

## 17. 浏览器验证结果

**8 项核验符合预期：7 项正常流程通过，1 项确认已知 R14 缺陷仍可复现。** 不能解读为四项缺陷全部关闭。

1. 实际 HTTP 统计与报名/提交集合一致。
2. 首页报名计数及报名、提交分区对应当前届次。
3. 首页 → 报名列表 → 届次 11 详情。
4. 首页 → 提交列表 → 届次 21 详情。
5. unknown 无 UI 入口；正常来源筛选仅生成单参数并正常显示。
6. 重复 source_scope 参数触发预期错误页和服务端 TypeError（R14 OPEN）。
7. 正常列表恢复；limit=1 实际 HTTP 返回 1 条。
8. 390px 手机视口下报名计数与列表一致。

浏览器未捕获未处理 pageerror；R14 异常由错误边界处理，服务端异常有单独记录。截图已人工查看。完整证据：[browser.cjs](D:/Python/xuesheng/.codex-qa/final-targeted-review/browser.cjs)、[结果](D:/Python/xuesheng/.codex-qa/final-targeted-review/browser-results.json)。

## 18. 数据库安全结果

**通过。** 保持既有 `conftest.py`、数据库隔离 fixture 和生产路径拒绝规则不变；全量测试包含数据库隔离回归。本轮探针导入相同 SQLite 连接保护，并验证正式路径在建立连接前被拒绝。

- pytest 使用内存或临时数据库；既有需要目录样本的测试通过 `production_copy_session_factory` 连接临时复制库，不连接正式库。
- 性能探针只使用内存库；浏览器及构建服务只连接新建的合成库 `.codex-qa/final-targeted-review/browser.sqlite`。
- 正式库没有作为测试连接目标，没有迁移、清理、真实数据修正或 schema 变更。
- 修复前 SHA256：`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`。
- 修复后 SHA256：`9f2eb40a640eb5bdbfc0ad4006787f7d0e910a3d1d3598b9d0d551a30768f320`。
- 两者一致。测试服务已停止，3038/8038 监听数为 0。

证据：[修复前快照](D:/Python/xuesheng/.codex-qa/final-targeted-review/before.json)、[代码验证后快照](D:/Python/xuesheng/.codex-qa/final-targeted-review/after-code.json)。没有正式部署或远程仓库操作。

## 19. 当前 P0 数

**0。** 指本阶段已登记问题及本轮定向复核范围，不表示完成一次新的全仓安全认证。

## 20. 当前 P1 数

**0。** 已修复的隐私问题沿用上一轮证据，相关回归包含在本轮完整测试中且通过。

## 21. 当前 P2 数

**1：R12（非阻塞）。** 统计卡片构建已去掉，全量 ORM 加载仍在；当前规模的可用性验证通过，保留性能债务。R06 已关闭。

## 22. 当前 P3 数

**2：R13、R14（均非阻塞）。** 直接 unknown API 筛选和手工重复 URL 参数仍有缺陷；不能标为关闭。

## 23. 是否建议批准此前阶段改动

**【建议批准本阶段改动】**。

判断依据：本阶段已知 P0/P1 为 0；本轮关闭影响核心计数的 R06；剩余问题未阻塞已验证的正常发现、筛选及同届次详情链路。此前已关闭的隐私泄露、审核事务半成功、跨届次事实和未核验信息公开问题不重复审计，其已有回归在本轮完整测试中全部通过。正式数据库哈希保持不变。

此结论明确接受 1 项性能债务和 2 项 P3 留存，不把它们改写为“全部缺陷已清零”，也不据此批准 push、merge 或部署。

**此前 48 个文件的阶段开发可以进入收口。**

## 24. 是否可以正式结束这一阶段

**可以。本轮以阶段批准判断结束。** 没有进入字段级入库预览、来源核验、后台扩展、会议前端或新赛事采集；下一阶段等待用户另行下达。

真正阻塞项：无。

**PHASE_APPROVAL = PASS**
