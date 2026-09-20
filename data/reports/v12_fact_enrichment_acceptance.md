# V12 核心赛事事实信息补全 — 验收记录

- 生成时间：2026-09-05T14:29:46.160009+00:00
- 范围：仅冻结的核心赛事（100项）；未新增 Competition；未改数据架构；未开发会议/推荐/评分/UI 大改

## A. 核心赛事完整度（100项，前后对比）

| 指标 | 前 | 后 | Δ |
| --- | --- | --- | --- |
| 有主办单位 | 28.0% | 29.0% | +1.0% |
| 有官网字段 | 16.0% | 30.0% | +14.0% |
| 有参赛对象 | 10.0% | 13.0% | +3.0% |
| 有赛事简介 | 86.0% | 86.0% | +0.0% |
| 有结构化届次（≥1届） | 34.0% | 36.0% | +2.0% |
| 有最近2届（2024-2026中任2届） | 1.0% | 4.0% | +3.0% |
| 有最近3届（2024/2025/2026齐全） | 0.0% | 3.0% | +3.0% |
| 有2025+官方通知/报名链接的届次 | 13.0% | 18.0% | +5.0% |

## B. 历史数据（Edition 层）

- 当前 Edition 总数：62（新增 8 行，全部来自官方证据）
- Edition 状态：{"pending_verification": 8, "school_confirmed": 31, "verified_official": 23}
- 2023-2026 年份分布：{"2024": 3, "2025": 7, "2026": 52}
- 有官方通知 URL 的赛事：14
- edition_result_url 事实行：3

## C. 来源

- 本轮新增 CompetitionSource（source_repository=v12-fact-registry）：13，等级分布：{"S": 13}
- 全库 official_website 非空赛事数：33

### 本轮使用的官方原始来源清单

| Competition ID | source_url | 标题 |
| --- | --- | --- |
| 1 | https://www.moe.gov.cn/srcsite/A08/s5672/202405/t20240513_1130304.html | 教育部关于举办中国国际大学生创新大赛（2024）的通知 |
| 2 | https://www.tiaozhanbei.net/article/15795/ | 第十九届“挑战杯”中国移动全国大学生课外学术科技作品竞赛通知（组委会2025-06-13发布） |
| 3 | https://www.tiaozhanbei.net/article/15842/ | 关于举办第十五届“挑战杯”建设银行中国大学生创业计划竞赛的通知 |
| 4 | https://www.mcm.edu.cn/upload_cn/node/745/ogFWOgXVc36c27bb3ee3adf21e06f53146b03585.pdf | 2025高教社杯全国大学生数学建模竞赛第一次通知（报名和参赛须知2025-04-02修订） |
| 5 | https://www.nuedc-training.com.cn/index/news/details/new_id/330 | 关于组织2025年全国大学生电子设计竞赛的通知 |
| 5 | https://www.nuedc-training.com.cn/index/news/details/new_id/329 | 2024年全国大学生电子设计竞赛赛区赛暨模拟电子系统设计专题赛（TI杯）初赛赛题 |
| 5 | https://www.nuedc-training.com.cn/index/news/details/new_id/340 | 关于公布2025年全国大学生电子设计竞赛获奖名单的通知 |
| 5 | https://www.nuedc-training.com.cn/index/news/details/new_id/345 | 关于开展2026年全国大学生电子设计竞赛模拟电子系统设计专题赛的第一次通知 |
| 5 | https://www.nuedc-training.com.cn/index/news/details/new_id/358 | 关于公布2026年全国大学生电子设计竞赛模拟电子系统设计专题赛决赛获奖名单（初评）的通知 |
| 24 | https://ucc.fltrp.com/c/2026-04-15/541569.shtml | 2026“外研社·国才杯”“理解当代中国”全国大学生外语能力大赛通知 |
| 99 | https://www.cmathc.org.cn/tzgg/88.html | 关于举办第十六届全国大学生数学竞赛的通知 |
| 99 | https://www.cmathc.org.cn/tzgg/201.html | 关于举办第十七届全国大学生数学竞赛的通知 |
| 99 | https://www.cmathc.org.cn/csmd/390.html | 关于公布第十七届全国大学生数学竞赛初赛获奖名单的通知 |

## D. 数据质量/删除说明

本轮未删除 Competition/CompetitionEdition/CompetitionSource/通知/证据文件。仅清理 6 条错误的关系行：comp1 江苏省人民政府(organizer)、南京大学(undertaker)、南京市人民政府(undertaker)（2026届当届承办，写入届次事实层）；comp3 人社部(organizer)（旧缩写、当届名单按届次记录）；comp24 外语教学与研究出版社(organizer)（改为 undertaker）；comp5 全国大学生电子设计竞赛组织委员会(organizer)（组委会是组织机制而非独立主办机构）。另有 2 项字段级修正：comp1 2025届 official_registration_deadline 错误值置空、comp34 2026届 official_notice_url 由高校通知改为置空等待官网当届通知页。所有变更均写入 CompetitionFactRevision/AdminAuditLog。

Competition 层状态未变（无升降级）；Edition 层 verified_official 8→23，school_confirmed 38→31，均为高校占位届次被官方 S 级来源覆盖后的真实晋升。

## E. Batch1 重点赛事逐项状态

| ID | 名称 | 官网 | 主办单位 | 参赛对象 | 官方届次年份 |
| --- | --- | --- | --- | --- | --- |
| 1 | 中国国际大学生创新大赛 | https://cy.ncss.cn | 教育部、中央统战部、中央网信办、国家发展改革委、工业和信息化部、人力资源社会保障部、农业农村部、中国科学院、中国工程院、 | 全日制在校本专科生、研究生及符合条件的高校毕业生；参赛人员年龄不超过35岁（以当 | 2026、2025、2024 |
| 2 | “挑战杯”全国大学生课外学术科技作品竞赛 | https://tiaozhanbei.net | 共青团中央、中国科协、教育部、中国社会科学院、全国学联 | - | 2025 |
| 3 | “挑战杯”中国大学生创业计划竞赛 | https://www.tiaozhanbei.net/ | 共青团中央、中国科协、教育部、中国社会科学院、全国学联 | - | 2026 |
| 4 | 全国大学生数学建模竞赛 | https://mcm.edu.cn | 中国工业与应用数学学会 | 普通高校全日制在校本专科学生（研究生不得参赛）；以队为单位，每队不超过3人且须属 | 2026、2025 |
| 5 | 全国大学生电子设计竞赛 | https://www.nuedc-training.com.cn/ | 教育部、工业和信息化部 | 普通高等学校具有正式学籍的全日制在校本科或高职高专学生；自愿组合、3人一队，由学 | 2026、2025、2024 |
| 21 | 全国大学生电子商务“创新、创意及创业”挑战赛 | https://3chuang.net | 教育部高等学校电子商务类专业教学指导委员会 | - | - |
| 24 | 外研社·国才杯“理解当代中国”全国大学生外语能力大赛 | https://ucc.fltrp.com/ | 北京外国语大学 | 全国普通高等学校全日制在校本科生和硕士研究生（含来华留学生）；国际中文组面向全日 | 2026 |
| 32 | “西门子杯”中国智能制造挑战赛 | https://siemenscup-cimc.org.cn | 教育部高等学校自动化类专业教学指导委员会、西门子（中国） | - | 2026 |
| 34 | 中国大学生计算机设计大赛 | https://jsjds.blcu.edu.cn/ | - | 在籍本科生 | 2026 |
| 35 | 中国高校计算机大赛 | http://www.c4best.cn/ | - | - | - |
| 36 | 蓝桥杯全国软件和信息技术专业人才大赛 | https://dasai.lanqiao.cn | 工业和信息化部人才交流中心 | - | - |
| 46 | 中国机器人大赛暨RoboCup机器人世界杯中国赛 | https://rcccaa.drct-caa.org.cn/ | - | - | - |
| 47 | “中国软件杯”大学生软件设计大赛 | https://cnsoftbei.com | 工业和信息化部、教育部、江苏省人民政府 | - | - |
| 56 | 全国高校商业精英挑战赛 | http://www.cubec.org.cn/ | - | - | - |
| 59 | 中国好创意暨全国数字艺术设计大赛 | https://www.cdec.org.cn/ | - | - | 2026 |
| 63 | iCAN大学生创新创业大赛 | http://www.g-ican.com/ | - | - | - |
| 65 | 中华经典诵写讲大赛 | https://jdsxj.eduyun.cn/ | 教育部、国家语委 | 面向大中小学在校学生、教师及社会公众（含港澳台与海外赛区；具体对象以各赛项实施方 | 2026 |
| 99 | 全国大学生数学竞赛 | https://www.cmathc.org.cn/ | 中国数学会 | 所有全日制在校大学生；分数学专业类、非数学专业类与高职高专类（数学专业类再分A/ | 2026、2025、2024 |
| 101 | 全国大学生英语竞赛 | http://www.chinaneccs.cn/ | 教育部高等学校大学外语教学指导委员会 | - | - |
| 125 | 中国研究生企业管理创新大赛 | https://cpipc.acge.org.cn/ | 中国学位与研究生教育学会、全国工商管理专业学位研究生教育指导委员会 | 在校研究生及已获研究生入学资格的本科生和本研贯通学生 | 2026 |