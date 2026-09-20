# 985高校竞赛政策爬取报告

- 生成时间：2026-08-31T07:59:48.642645+00:00
- 执行批次：first
- 985种子：39/39
- 真实政策文档：0
- 已核验政策文档：0
- 学院级政策文档：0
- 待复核项：2

## 识别状态统计

- recognized: 0
- explicitly_not_recognized: 0
- not_mentioned: 0
- insufficient_evidence: 0
- conflicting: 0
- expired: 0

## 单校抓取结果

| 学校 | 状态 | 发现链接 | 抓取页面 | 附件 | 解析附件 | 政策文档 | 竞赛命中 | 复核项 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 北京大学 | completed | 310 | 1 | 0 | 0 | 0 | 0 | 0 |
| 清华大学 | completed | 264 | 1 | 0 | 0 | 0 | 0 | 0 |
| 浙江大学 | completed | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| 武汉大学 | failed | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 华中科技大学 | failed | 0 | 0 | 0 | 0 | 0 | 0 | 1 |

## 失败与待复核原则

| 学校 | URL | 错误 | 可重试 |
| --- | --- | --- | --- |
| 武汉大学 | https://www.whu.edu.cn | Blocked by robots.txt | False |
| 华中科技大学 | https://www.hust.edu.cn | Blocked by robots.txt | False |

## 解析策略

- HTML：优先 BeautifulSoup，依赖缺失时退回标准库 HTMLParser。
- PDF：优先 PyMuPDF，缺失时退回 pdfplumber；无文本层时只标记 scanned_pdf，不做 OCR。
- DOCX：python-docx。
- XLSX：openpyxl，读取工作表文本，不执行公式。

## 结论边界

- 政策优先级固定为 MAJOR > COLLEGE > UNIVERSITY。
- 政策存在但未提及比赛时，只能输出 not_mentioned，不能推断为不认可。
- 抓取失败、解析失败、短名歧义、低置信匹配均进入 ReviewQueue。
- 当前实现未复制 GitHub 第三方爬虫项目代码；未来引入外部实现前必须核验许可证和 NOTICE 义务。
