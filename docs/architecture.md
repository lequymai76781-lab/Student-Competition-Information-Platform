# 项目架构说明

V0.1 使用前后端分离架构：

```text
project-root/
  frontend/   Next.js + React + TypeScript + Tailwind CSS
  backend/    FastAPI + SQLAlchemy + Alembic
  docs/       架构、API、数据模型和路线图
  scripts/    本地开发辅助脚本
  data/       本地数据与后续采集样例预留
```

后端分层：

```text
backend/app/
  api/            路由与依赖注入
  core/           配置、统一响应、异常处理
  database/       SQLAlchemy engine/session/Base
  models/         数据库模型
  schemas/        Pydantic request/response schema
  repositories/   数据访问
  services/       业务逻辑、推荐、搜索、可信度、AI预留
  crawler/        数据采集接口预留
  tasks/          后台任务预留
```

请求流：

```text
Route -> Service -> Repository -> SQLAlchemy Model -> PostgreSQL
```

设计约束：

- API 层只处理请求参数、依赖注入和响应结构。
- 业务规则放在 service，例如推荐评分和来源可信度。
- 数据查询放在 repository，方便后续替换搜索引擎或缓存。
- 社交平台信息只作为发现线索，存在官方来源时才标记为已核验。
- V0.1 不调用真实 AI API，`services/ai` 只提供可替换接口。

