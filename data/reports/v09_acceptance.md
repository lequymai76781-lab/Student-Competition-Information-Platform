# V0.9 验收报告：我的竞赛与个性化赛事中心

生成时间：2026-09-02

## 网站前端地址

- 前端：**http://127.0.0.1:3000**（首页 /、我的竞赛 /my-competitions、登录 /login、注册 /register、画像设置 /onboarding、资料编辑 /settings/profile、发现竞赛 /competitions、日历 /calendar、数据工程 /data）
- 后端 API：http://127.0.0.1:8001/docs

## 一、验收项

| 验收项 | 结果 |
| --- | --- |
| 用户系统（邮箱+密码+Token登录/注册/me） | 已完成（后端 /auth/*，前端 /login /register；Guest 保持可浏览） |
| UserProfile（学校/学院/专业/年级/兴趣/技能/偏好） | 已完成，可随时编辑并实时重算 |
| 可选择学校 | 113 所（选择框+搜索输入） |
| 可选择学院 | 学校联动学院；库中25条已收录学院直选，未收录允许手动输入并保存标准化名称 |
| 专业 | 库内专业为0条时支持标准化手动输入（保存到 Majors 并写入 Profile） |
| Interest Tags | 30+ 方向选项（人工智能/AIGC/新闻传播/数学建模/程序设计…，保存 canonical 标签） |
| 个性化可用 Competition | 事实筛选已实现（PersonalCompetitionService），5个场景输出见下表 |
| 拥有学校通知的 Competition | 仅展示已核验关系（CASE5 西南交大 4 项等）；无通知学校正常回退，不隐藏官方开放赛事 |
| 拥有学院通知/学院目录 | 关系与学校/学院政策目录证据按 Profile 过滤（武体学院目录90项来自真实政策证据） |
| 拥有个性化 Deadline | 学院→学校→官方三层 DeadlineResolutionService 已接入；未发现校内截止时只显示官方并注明，不猜造 |
| 收藏功能 | 已完成（Favorite，含收藏列表/取消） |
| 用户赛事状态 | 已完成（interested/planning/registered/participating/finished/abandoned） |
| Calendar 个性化 | 已完成（日历页“我的赛事截止”，按有效截止排序并标注层级） |
| 详情页“与你相关” | 已完成（登录用户显示理由+你的截止+三层截止） |
| 数据质量保护 | UserFacingDataPolicy 统一门禁；needs_review/result 不进“当前报名/学校通知”确定性模块 |
| 五个测试用户场景 | 已完成并逐场景输出 |

## 二、实现清单（实际落库/落代码，非方案）

后端：
- `UserProfile` 增加 university_name/college_name/major_name（自由文本标准化保存）；新增 `UserCompetitionStatus` 表（迁移 202609020010）。
- 新增 `/auth/register|login|me`；`/users/me/profile|overview|calendar-events|favorites|competitions/{id}/status|context`；`/directory/*`（学院/专业/兴趣选项）。
- `PersonalCompetitionService`：事实过滤（当前状态→方向→学校/学院关系→目录→参赛条件）+ relevance_reasons + 三层 Deadline；无任何评分/模型。
- `UserFacingDataPolicy`：只放行已核验 relation 与 open 届次。
- 5个场景用户（case1..5@test.local / test123456）与场景 JSON。

前端：
- /login /register /onboarding（学校→学院→专业→年级→方向5步）/my-competitions（工作区+状态/收藏）/settings/profile。
- 首页登录态“我的竞赛”区（现在可以参加/即将截止）、详情页“与你相关”、日历“我的赛事截止”、导航登录按钮动态切换。

## 三、5 个用户场景结果（真实数据，无 Mock）

| 场景 | 画像 | 现在可以参加 | 方向相关 | 学校通知 | 学校目录 | 即将截止(用户相关) |
| --- | --- | --- | --- | --- | --- | --- |
| CASE1 | 武汉体育学院/新闻传播学院/播音主持/大二（兴趣：新闻传播/AIGC/影视） | 14 | 64 | 0 | 90（学院目录90） | 10 |
| CASE2 | 武汉大学/计算机学院/计算机科学/大三（人工智能/程序设计/大数据） | 8 | 36 | 0 | 5 | 7 |
| CASE3 | 北京交通大学/电子信息学院/电子信息工程/大二（电子信息/人工智能） | 5 | 27 | 0 | 0 | 5 |
| CASE4 | 南京航空航天大学/机电学院/机械工程/大三（机械制造/机器人） | 0* | 12 | 0 | 0 | 0 |
| CASE5 | 西南交通大学/经济管理学院/工商管理/大二（商业分析/创新创业） | 6 | 26 | 4 | 0 | 5 |

*CASE4 为如实结果：机械方向当前数据库中无“正在开放报名”的赛事；页面按规范不造学校截止，也不硬凑推荐。方向相关 12 项仍可浏览。

各场景前5“现在可以参加”：

- CASE1：清华大学中国公共政策案例分析大赛、全国大学生数学建模竞赛、大学生“AI+信息素养”大赛、全国大学生嵌入式芯片与系统设计竞赛FPGA创新设计竞赛、中国国际大学生创新大赛
- CASE2：清华大学中国公共政策案例分析大赛、全国大学生数学建模竞赛、大学生“AI+信息素养”大赛、中国研究生企业管理创新大赛、中国国际大学生创新大赛
- CASE3：清华大学中国公共政策案例分析大赛、大学生“AI+信息素养”大赛、全国大学生嵌入式芯片与系统设计竞赛FPGA创新设计竞赛、中国大学生工程实践与创新能力大赛、AI+教育大学生创新创业大赛
- CASE5：中国首届“新域新质”创新大赛、中国研究生企业管理创新大赛、中国国际大学生创新大赛产业命题赛道、中国国际大学生创新大赛、AI+教育大学生创新创业大赛

CASE5 学校有通知：中国国际大学生创新大赛、“挑战杯”中国大学生创业计划竞赛、中国好创意暨全国数字艺术设计大赛、中国高校计算机大赛移动应用创新赛（来自V0.8.1已核验的32条关系）。

## 四、成功标准核对

- 两个不同学校/专业的学生打开平台看到的赛事、通知、截止、标签明显不同：✅（CASE1 vs CASE5 的 now/通知/截止列表不同；武体目录90 vs 武大目录5）。
- 平台回答“现在有什么比赛适合我”只来自事实相关性+当前可行动状态：✅（无推荐指数/匹配度/含金量，卡片只显示 ✓ 理由与三层截止）。
- 未扩高校、未开普通本科、未扩 Crawler、未接 LLM/Embedding/评分模型：✅

## 五、备注

- 测试账号密码均为 test123456：case1@test.local（武体）、case2@test.local（武大）、case3@test.local（北交）、case4@test.local（南航）、case5@test.local（西南交大）。
- /dashboard 旧占位页保留但导航已指向 /my-competitions。
