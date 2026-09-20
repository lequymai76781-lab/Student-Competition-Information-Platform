# V1.0 验收报告：用户提醒闭环与上线前产品化

生成时间：2026-09-02

## 网站地址

- 前端：**http://127.0.0.1:3000**
  - 通知中心：/notifications
  - 我的竞赛：/my-competitions（含“最近变化”）
  - 审核中心：/admin/review（管理员）
  - 赛事详情页底部：纠错入口 + “最近更新”
  - 页面右下角：Beta“反馈问题”按钮
- 后端 API：http://127.0.0.1:8001/docs

## 一、验收项

| 验收项 | 结果 |
| --- | --- |
| Notification 系统 | 完成（表+服务+API+前端通知中心+导航铃铛） |
| 类型支持 | deadline_reminder / competition_updated / school_notice_added / college_notice_added / new_edition / system 均可落库，字段含 competition_id/edition_id/source_event_id/is_read/read_at/dedup_key |
| Deadline 提醒 | 完成：14/7/3/1/0 天五档；同一Deadline同一档只生成一次（dedup_key 约束+测试）；优先 effective_deadline（学院→学校→官方） |
| 赛事变化通知 | 完成：CompetitionUpdateEvent（deadline_changed/submission_changed/competition_date_changed/…，均带 old/new/source_url/changed_at）+ 关注者通知 |
| 学校/学院通知新增 | 完成：新 Relation 自动给同校且关注该赛事的用户生成通知 |
| 我的竞赛“最近变化” | 完成（通知置顶区） |
| 首页个性化强化 | 完成：登录态优先“我的近期截止/现在可以参加/学校通知”；首页统计已改为用户向指标（当前可报名/近期截止/收录赛事/方向分类/赛事届次/覆盖高校），工程指标只保留在 /data |
| UserCorrectionSubmission | 完成（详情页纠错入口 → pending 队列，不直接改库） |
| Admin Review Center | 完成（/admin/review：用户纠错/赛事线索/事实变更/候选事实/Beta反馈 Tabs + 批准/拒绝/重复/需更多证据） |
| Freshness Scheduler | 完成（run_v1_prod_ops.py 实际执行：Revision→事件、Relation→通知、提醒、freshness 刷新；失败不删旧事实，仅标记 due_for_check） |
| Beta Feedback | 完成（页面右下角按钮 + 后台列表） |
| 权限与安全检查 | 完成（见下） |
| Empty State / Onboarding UX | 完成（未设置学校时紧凑CTA，不再大空白；Onboarding仅5步） |

## 二、运行实例

- 提醒实例：为 10 个 Beta 用户自动关注赛事后，生成 **12 条截止提醒**（9个用户有提醒，case4机械方向无当前开放报名为如实空）；幂等测试确认不重复。
- 赛事变化通知：**3 个 UpdateEvent**（含演示：报名截止 2026-09-20 → 2026-09-27），对关注者生成 **8 条 competition_updated 通知**（case1 等收到“2026-09-20 → 2026-09-27”）。
- 通知中心实测：case1 未读 3，点击可进入对应赛事详情。
- 用户纠错：1 条 pending 进入审核队列（演示）。
- Beta 反馈：1 条 pending（演示）。
- Freshness 调度输出：53 个届次，40 fresh / 13 due_for_check，未删除任何旧数据。

## 三、权限与安全检查（5/5 通过）

1. 密码：PBKDF2-HMAC-SHA256 + 随机盐存储，登录校验通过。
2. Token：HMAC 签名 + exp 过期字段（verify_token 校验）。
3. Admin API：`get_current_admin` 依赖；普通用户访问 /admin/review/summary 实测返回 403，自动化测试断言通过。
4. 数据隔离：Profile/Favorite/Status/Notification 查询全部按 `user_id` 过滤；Profile 只允许本人修改。
5. 密钥：APP_SECRET 已放入 backend/.env 与 .env.example，前端无任何 Secret（前端仅 API 地址）。

## 四、Beta 用户与任务流程

- Beta 用户：10 个场景（case1..10@test.local / test123456），覆盖武体·新闻、武大·计算机、北交·电子信息、南航·机械、西南交大·经管、北邮·通信、复旦·新闻、华科·机械、川大·广告、人大·金融；场景明细见 [v09_test_users_scenarios.json](D:/Python/xuesheng/data/reports/v09_test_users_scenarios.json)（10行）。
- 核心任务（注册→画像→找比赛→资格→官方截止→学校截止→收藏→标记→我的竞赛→日历→提醒）逐项由自动化测试覆盖：注册/资料 API 全链路测试、PersonalOverview 差异测试、DeadlineResolution 个性化测试、Calendar 事件测试、Reminder 生成与幂等测试、UpdateEvent 通知测试、Correction+Admin 权限测试、Feedback 测试 → **11/11 完成**。
- 前端页面测试：首页/发现竞赛/日历/高校库/数据工程/登录/注册/5个详情页/我的竞赛/资料设置/通知中心/审核中心 共 **32 个视口检查**（1440×900、1920×1080、390×844）全部无横向滚动、无控件裁切、无运行时错误；详情页“最近更新”实测渲染（赛事122显示“报名截止更新 2026-09-20 → 2026-09-27”）。
- 后端测试：**37 项全部通过**（30 历史 + V0.9 2 项 + V1.0 5 项）。

## 五、说明

- 调度器：`backend/scripts/run_v1_prod_ops.py`（提醒+事件+通知+freshness），可加入计划任务每日执行；提醒/事件幂等。
- “最近更新”仅展示面向用户的轻量摘要（日期+类型+old→new+来源），不展示技术 Diff。
- 保持V0.9全部功能与最新视觉体系；未扩高校、未新增竞赛、未接AI/评分。
