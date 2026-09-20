# 下一阶段路线图

建议优先级：

1. 用户登录与资料页：接入 `UserProfile`，让匹配结果使用真实用户资料。
2. 管理后台 CRUD：先做竞赛、届次、来源、政策和认可关系的表格管理。
3. 官方核验工作流：把发现线索、待核验、已核验、冲突信息状态化。
4. 高校政策解析：先做人工导入，再接入 LLM 结构化抽取。
5. 爬虫最小闭环：从少量高校官网和赛事官网开始，避免一开始采集社交平台。
6. 搜索升级：数据量上来后用 Meilisearch 替换当前 PostgreSQL 模糊搜索。
7. 推荐增强：在规则评分基础上加入用户行为、政策可信度和报名时间衰减。

当前预留接口：

- `backend/app/crawler`：BaseCrawler、UniversityCrawler、CompetitionCrawler、SocialMediaCrawler、CompetitionPlatformCrawler。
- `backend/app/services/ai`：extract_competition、extract_policy、deduplicate_competition、generate_recommendation_reason 的 mock 实现。
- `backend/app/services/search_service.py`：搜索抽象，当前 PostgreSQL，未来可接 Meilisearch。
- `REDIS_URL`、`MEILISEARCH_URL` 环境变量已预留。

