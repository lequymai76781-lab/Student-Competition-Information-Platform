# 中规模真实数据试点：A组独立来源研究

完成时间：2026-09-27 18:49:08 UTC（北京时间为次日凌晨）。只写本清单和本说明，未修改业务代码、数据库或其他来源清单。

## 结果

- 按 catalog 规范名称覆盖 28 个赛事，34 条来源候选。
- 21 个赛事取得可读正文，21 条 readable；另保留 11 条 blocked、2 条 unavailable。
- 所有来源均为 unverified 候选，不能直接升级为 VERIFIED。
- 7 个赛事仍无可用正文证据：6、9、12、23、28、30、54。
- 可读来源包含赛事网站、官方机构网页以及主办单位/赛事托管的 PDF。搜索用于发现线索；没有用搜索摘要填充事实字段。

## 覆盖表

| ID | 规范赛事名称 | 正文状态 | 提取范围或缺口 |
| --- | --- | --- | --- |
| 6 | 全国大学生职业规划大赛 | 未取得 | web.open 返回 Timeout fetching；HTTP 重试仍失败。 |
| 9 | 中国大学生医学技术技能大赛 | 未取得 | web.open 返回 Redirect loop detected；HTTP 重试仍失败。 |
| 12 | 全国大学生艺术节 | 未取得 | 正文访问发生重定向循环；且目录“艺术节”与官方“艺术展演活动”尚无同一实体证据。 |
| 15 | 全国科普讲解大赛 | readable | organizer、edition_name、edition_number |
| 22 | 中国大学生工程实践与创新能力大赛 | readable | description、edition_name |
| 23 | 全国大学生物流设计大赛 | 未取得 | web.open 返回 502 Bad Gateway。 |
| 25 | 两岸新锐设计竞赛·华灿奖 | readable | edition_name、edition_number |
| 28 | 全国大学生机器人大赛 | 未取得 | web.open 返回 Timeout fetching。 |
| 30 | 全国大学生先进成图技术与产品信息建模创新大赛 | 未取得 | web.open HTTPS 超时，HTTP 重试失败。 |
| 31 | 全国三维数字化创新设计大赛 | readable | short_name、english_name、official_website、edition_name、edition_number |
| 33 | 中国大学生服务外包创新创业大赛 | readable | frequency、official_website、description |
| 35 | 中国高校计算机大赛 | readable | description |
| 37 | 米兰设计周—中国高校设计学科师生优秀作品展 | readable | frequency、description |
| 38 | 全国大学生地质技能竞赛 | readable | edition_name、edition_number |
| 40 | 全国大学生集成电路创新创业大赛 | readable | organizer、official_website |
| 41 | 全国大学生金相技能大赛 | readable | official_website、founded_year、frequency |
| 42 | 全国大学生信息安全竞赛 | readable | official_website、edition_name、edition_number |
| 44 | 全国周培源大学生力学竞赛 | readable | organizer、description、edition_name、edition_number |
| 45 | 中国大学生机械工程创新创意大赛 | readable | edition_name |
| 46 | 中国机器人大赛暨RoboCup机器人世界杯中国赛 | readable | official_website |
| 48 | 中美青年创客大赛 | readable | organizer、founded_year、official_website、edition_name |
| 49 | 睿抗机器人开发者大赛（RAICOM） | readable | official_website、edition_name |
| 50 | “大唐杯”全国大学生新一代信息通信技术大赛 | readable | edition_name、edition_number |
| 51 | 华为ICT大赛 | readable | organizer、founded_year、frequency、description、edition_name |
| 52 | 全国大学生嵌入式芯片与系统设计竞赛 | readable | official_website、description |
| 53 | 全国大学生生命科学竞赛（CULSC） | readable | official_website、edition_name |
| 54 | 全国大学生物理实验竞赛 | 未取得 | web.open 返回动态站点空正文（0行）。 |
| 55 | 全国高校BIM毕业设计创新大赛 | readable | description、edition_name、edition_number |

## 必须保留的证据边界

1. ID 12“全国大学生艺术节”存在实体歧义。发现教育部“全国大学生艺术展演活动”线索，正文又遇重定向循环；没有证据证明两者相同，因此不添加别名、不填字段，也不认定已找到该目录实体的确切官网。
2. ID 22 官网页尾明确大赛组委会，虽使用大连理工大学域名，承载的是全国大赛页面。正文支持2027届次；数据库中的“厦门大学学生处”未得到正文支持。动态新闻列表未读取，未采用其内容。
3. ID 25 已读取[民革天津市委会官方报道](https://tjminge.gov.cn/system/2025/12/17/030055442.shtml)，仅支持2025年第十届。发布者是民主党派地方组织，现有枚举采用 government_official_notice 表示官方机构来源；publisher 明确保留真实机构，未声称该网页是赛事官网或主办方。
4. ID 35 [计算机教育研究会页面](https://www.ceracu.org.cn/h-nd-182.html)的标题为2019年能力挑战赛通知，正文单独明确“中国高校计算机大赛”为面向高校学生的计算机类系列竞赛。只提取这个上位赛事描述，不混入挑战赛名称、日期或规则。
5. ID 38 官方年度会议计划仅支持2026年第八届地质技能竞赛。计划中的拟举办时间不是最终日程；未单独确认发布日期，不从附件名推算。
6. ID 42 测评中心正文支持2025年第十八届及 ciscn.cn 官网。创新实践能力赛暨长城杯的主办方、半决赛日期和赛制均未写成全赛事事实。
7. ID 45、49、50 的 PDF 是具体赛项或赛道文件，只提取封面/标题明确的整届身份，以及原文明确的官网。未把赛项的队伍规模、报名节点或省赛时间提升为整赛规则。49、50为对象存储原始附件，发布归属仍待正式复核。
8. ID 53 读取全国赛事网站托管的甘肃省赛通知。标题中的全国赛事2021与网站地址可用；省赛“第二届”不是全国届次。正文2020—2021赛程与末尾2019署名日期不一致，published_at 为 null，未采纳省级规则。
9. ID 51 华为赛事采用2025—2026完整届次名称，year=2026为结束年。总决赛专题网址不当作永久比赛门户。
10. ID 54 找到的站点对应物理实验竞赛创新赛，动态页面没有可用正文，不将其身份扩展为目录中的全部物理实验竞赛。
11. ID 55 第九届官方归档页混有第五届旧文，只采纳明确第九届区域，year=2023为结束年。没有依据高校摘要把规范名改为“国际高校”，也没有凭证书盖章机构填主办方。

## 仍待补取

- ID 6 教育部第三届职业规划大赛通知及其替代路径超时；学信网赛事页未获得正文。
- ID 9 教育部获奖名单/专题出现重定向循环。没有以高校转载替代赛事官网。
- ID 12 先确认“艺术节”的目录实体，再补直接官方原文。
- ID 23 中国物流与采购联合会赛事入口/关于页出现502或超时。
- ID 28 curc.cn 官方入口超时，未采用搜索摘要中的主办方和赛道信息。
- ID 30 成图大赛官网及通知路径超时。
- ID 54 创新赛官网返回0行主体内容，需要能够读取的正式原文。

## 检查

保存前检查28个 ID 和规范名称与 catalog 一致、来源 key 全部唯一。所有非 readable 来源的 competition_fields 和 edition_fields 均为空，并记录 source_failure_reason；所有来源 verification_status=unverified、retrieval_method=web。没有执行测试或导入数据库。

