# V1.0 RC1 验收报告：上线前硬化与真实Beta准备

生成时间：2026-09-03

## 最终状态

- 测试数据已清理：case1..10/v1test-*/temp-*/admin@test.local 全部删除；演示 Notification/Correction/Feedback/UpdateEvent 已删除；库中保留正式赛事数据 + 1 个通过环境变量创建的管理员（admin@rc.local，密码未落盘回显）。
- 前端生产构建：**成功**（Next.js 16，17 路由全部编译）。
- 后端测试：**39/39 通过**。

## 验收项清单

| 验收项 | 结果 |
| --- | --- |
| Production 安全检查 | **13 项通过**：默认测试凭据清理；Secret仅.env；APP_SECRET生产守卫（默认值/过短会启动报错）；DATABASE_URL生产禁SQLite；Beta邀请码强制；密码PBKDF2；Token带过期；Admin API 403；用户数据按user_id隔离；Competition写接口仅Admin；普通用户不能审批Correction/访问Admin；生产关闭docs/openapi；前端无Secret |
| 删除测试账号 | 15 个已删除（0 残留） |
| Hardcoded Secret | 3 处默认值 → 0（config 默认仅限 development；production/staging/beta 强制环境变量） |
| Admin 权限 | 通过（HTTP+自动化测试双验证） |
| Rate Limit | 完成（login/register/feedback/correction/通知读取/搜索 内存滑动窗口限流） |
| Swagger Production | 生产默认关闭 /docs /redoc /openapi.json；开发保留 |
| 数据库备份 | 成功（timestamped sqlite backup + manifest，见 data/backups/backup-20260903-011521.*） |
| 数据库恢复 | 成功（restore drill：表计数全匹配、/api/health 200、赛事抽样 1；报告 data/reports/v101_restore_drill.json） |
| Migration | 成功（空库 upgrade head：38 表、head 202609020012；现有 V1.0 库升级 head 通过） |
| Scheduler | 成功（幂等复跑 0 重复；失败单步隔离+日志 data/logs/app.log） |
| Notification Dedup | 成功（唯一约束+测试；14/7/3/1/0 档重复运行不重复通知） |
| Deadline Revision | 成功（9-20 → 9-27 全链：Revision保留旧值 → UpdateEvent → 通知关注用户 → 详情新值+历史；自动化测试） |
| Correction 闭环 | 成功（用户提交 → Admin Review → 批准+new_deadline → Fact更新 → Event → 关注用户通知 → Audit Log；自动化测试） |
| Production Logging | 完成（统一 logging：auth failure/admin action/scheduler error；不记录密码/Token） |
| Admin Audit | 完成（admin_audit_logs：admin_id/action/object/before/after/timestamp） |
| Beta 环境 | 完成（.env.production.example + BETA_INVITE_CODE + bootstrap_admin env 初始化） |
| Beta Feedback | 完成（8 类分类 + 右下角入口 + Admin 查看/处理） |
| 隐私/数据说明 | 完成（注册页说明、Profile 数据用途说明、详情页免责声明横幅） |
| 首页工程指标收敛 | 完成（普通首页仅用户向指标；Lead/Crawler/Precision 归 /data 与 /admin） |
| 错误状态 | 完成（全局 error.tsx：重试/返回列表/回首页；登录过期跳登录） |
| 移动端 | 通过（390×844 注册/Profile/列表/详情/收藏/Deadline/通知/日历相关页面无溢出无裁切） |

## 数据快照（RC 基线）

- Competitions 143 / Editions 53 / Sources 236 / FactRevisions 6 / Universities 113 / Colleges 34
- Users 1（env创建管理员）；Notifications 0（干净）；Corrections 0；BetaFeedback 0；UpdateEvents 1（真实Revision事件）

## 已知边界（如实说明）

- 自动化测试在 development SQLite 上运行，测试过程自清理；生产使用独立 DATABASE_URL（配置守卫禁止 SQLite），测试账号不存在于生产。
- 空库安装路径：全新空库执行 `alembic upgrade head` 时由 env 层一次创建当前完整 Schema 并 stamp head（历史增量迁移仍用于既有库升级）。
- Rate Limit 为单进程内存实现，多实例部署需换共享存储（上线初单实例够用）。

## 结论

**建议进入受邀请码控制的真实学生 Beta（10–20 人）。** 备份可恢复、迁移可空库重建、管理员凭据无默认值、测试数据不残留、提醒不重复、纠错闭环已实测跑通。
