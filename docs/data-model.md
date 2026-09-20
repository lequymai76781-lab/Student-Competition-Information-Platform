# 数据模型

核心实体：

- `Competition`：比赛主档案，保存名称、类别、级别、团队形式、难度和适合年级。
- `CompetitionEdition`：某一年或某一届比赛，保存报名、比赛和公告时间。
- `CompetitionSource`：信息来源，区分官方、高校、竞赛平台、微信、小红书、微博等来源，并记录可信度。
- `University`：高校基础信息。
- `College`：学院，归属于高校。
- `Major`：专业基础表。
- `UniversityPolicy`：高校政策文件，支持保研、综测、奖学金、竞赛奖励、创新创业学分等类型。
- `UniversityCompetitionPolicy`：学校是否认可某比赛的关系表，是后续决策能力的关键。
- `User`：用户基础账号，V0.1 不实现复杂权限。
- `UserProfile`：学校、学院、专业、年级、目标、技能、兴趣和偏好。
- `Favorite`：收藏比赛。
- `Recommendation`：推荐结果留痕。
- `Tag` / `CompetitionTag`：比赛多标签分类。

V0.1 Mock 数据全部通过 `is_demo=true` 或内容中的 `demo_data=true` 标记，不代表真实高校政策结论。

