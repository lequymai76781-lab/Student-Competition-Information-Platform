# 大学生竞赛情报平台 - V1.0 Beta 服务器部署文档

版本：V1.0 RC1 / Beta 部署准备
目标：阿里云 Linux + 宝塔面板，为 10-20 名邀请码学生提供真实 Beta。

> 本文件只包含部署方法与占位符，不含任何真实 Secret / 管理员密码 / Token。

## 1. 推荐生产架构

```text
手机/浏览器
    │ HTTPS
    ▼
Nginx (宝塔, 443)
    ├─ /            → Next.js production (127.0.0.1:3000)
    └─ /api/*       → FastAPI (127.0.0.1:8000)
                         ├─ PostgreSQL（正式数据库）
                         ├─ 独立 Scheduler（systemd/Supervisor 常驻）
                         └─ data/logs（backend/scheduler/nginx 日志）
```

- Frontend：Next.js production build，浏览器只访问同域 `https://域名/api`（Nginx 反代），无跨域。
- Backend：FastAPI + Gunicorn(UvicornWorker) 监听 127.0.0.1:8000，由宝塔进程守护或 systemd 管理。
- Database：生产用 PostgreSQL（示例见 docker-compose 或云数据库），代码禁止 SQLite 作为生产库（配置守卫）。
- Scheduler：独立常驻进程 `run_v1_prod_ops.py --loop-minutes 1440`，服务器重启后自动拉起，不依赖终端窗口/Codex。
- Static assets：Next 自带静态资源；如迁移大数据量文件，可在 Nginx 单独 `location /_next/static` 指向构建产物。

## 2. 服务器目录建议

```text
/www/wwwroot/competition/
├── backend/
│   ├── app/ alembic/ scripts/ venv/
│   └── .env                      # 生产环境变量（不入 Git）
├── frontend/
│   ├── .next/ package.json
│   └── .env.production.local     # NEXT_PUBLIC_API_BASE_URL（构建时读取）
├── data/
│   ├── logs/                     # backend/scheduler 日志
│   └── backups/                  # 数据库备份
└── deploy/                       # 部署示例（nginx/systemd/supervisor）
```

## 3. 环境变量

后端 `.env`（生产）必须包含：

```ini
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/competition_intelligence
APP_SECRET=<至少24位随机串>
BETA_INVITE_CODE=<Beta邀请码>
FRONTEND_URL=https://competition.example.com
BACKEND_URL=https://competition.example.com
BACKEND_CORS_ORIGINS=https://competition.example.com
LOG_DIR=/www/wwwroot/competition/data/logs
```

前端构建环境变量：

```ini
NEXT_PUBLIC_API_BASE_URL=https://competition.example.com/api
```

参考文件：`.env.production.example`、`frontend/.env.production.example`。配置守卫：production/staging/beta 下若 APP_SECRET 为默认值/过短、DATABASE_URL 为 SQLite、缺少邀请码或正式域名、CORS 含 localhost，Backend 启动会直接报错拒绝运行。

## 4. 数据库迁移与备份

```bash
cd /www/wwwroot/competition/backend
source venv/bin/activate
alembic upgrade head                       # 服务器部署后执行一次；不重新 Seed 测试数据
python scripts/backup_database.py          # 部署前执行一次正式备份（时间戳文件+manifest）
```

恢复演练已通过（restore drill：表计数全匹配、/api/health 200、赛事抽样正常）。回滚：从 `data/backups/backup-*.sqlite`/PostgreSQL dump 恢复并重启服务。

## 5. Backend 启动命令（systemd）

示例 unit：`deploy/systemd/backend.service.example`

```bash
cp deploy/systemd/backend.service.example /etc/systemd/system/competition-backend.service
systemctl daemon-reload
systemctl enable --now competition-backend
systemctl status competition-backend
```

宝塔方案：Supervisor 配置见 `deploy/supervisor/backend.conf.example`。

## 6. Frontend 构建与启动

```bash
cd /www/wwwroot/competition/frontend
export NEXT_PUBLIC_API_BASE_URL=https://competition.example.com/api
npm ci
npm run build                          # 生产构建（已在本机验证通过）
nohup npm run start -- --hostname 127.0.0.1 --port 3000 >> ../data/logs/frontend.log 2>&1 &
```

生产建议同样交给宝塔 Node 守护或 systemd 常驻。

## 7. Scheduler 启动命令

```bash
cp deploy/systemd/scheduler.service.example /etc/systemd/system/competition-scheduler.service
systemctl enable --now competition-scheduler
```

或宝塔 Supervisor：`deploy/supervisor/scheduler.conf.example`。Scheduler 与 Backend 独立，每日执行提醒/事件同步/Freshness，失败单步隔离并写 `LOG_DIR`，不会重复通知。

## 8. Nginx 与 HTTPS

示例：`deploy/nginx/beta-nginx.conf.example`。

- 80 一律 301 → HTTPS；
- 域名已备案则申请宝塔 Let's Encrypt/商业证书，配置 fullchain.pem + privkey.pem；
- `/api/` 反代 127.0.0.1:8000，避免跨域；
- 已含基础安全头、`client_max_body_size 2m`、合理 proxy 超时；
- 当前无 WebSocket 依赖；若未来接入，可放开 upgrade 头。

## 9. 日志

- Backend：Gunicorn access/error + 应用日志（LOG_DIR/app.log），不记录密码/Token/Secret；
- Scheduler：LOG_DIR/app.log（含 v1.scheduler）；
- Nginx：宝塔 access/error 日志。

## 10. 健康检查与监控

- `https://域名/api/health` → `{"success":true,"data":{"status":"ok",...}}`
- 宝塔监控可对 /api/health 做 URL 监控。

## 11. 部署后 Smoke Test 清单

浏览器/服务器验证：

1. `/` 首页正常
2. `/competitions` 列表正常
3. `/competitions/{id}` 详情正常（至少 5 个 id）
4. `/calendar` 正常
5. `/login`、`/register`（需邀请码）正常
6. 登录后 `/my-competitions`、`/notifications`、`/settings/profile` 正常
7. `/admin/review`：非管理员 403，管理员可访问
8. `/api/health` 200
9. `/docs`、`/redoc`、`/openapi.json` 在 production 返回 404

## 12. 真实手机 Beta 验证

用真实手机（非 DevTools 模拟）访问 Beta 域名，覆盖：注册（邀请码）→ 设置学校/学院/专业 → 找比赛 → 判断可否参加 → 查看官方/校内截止 → 查看学校通知 → 收藏 → 我的竞赛 → 日历 → 通知中心 → 发现错误提交反馈。

## 13. 部署条件自检（当前代码）

✅ 已具备：
- production/staging/beta 配置守卫（Secret/DATABASE_URL/邀请码/正式域名/CORS）
- 生产关闭 /docs /redoc /openapi.json；统一日志路径可配
- Rate Limit、Admin 权限、Competition 写接口仅 Admin
- 管理员通过 env/bootstrap_admin.py 创建（无固定默认）
- 测试数据清理脚本、备份/恢复演练、空库迁移演练通过
- Scheduler systemd/Supervisor 常驻示例；前端生产构建通过；39/39 后端测试

⚠️ 部署前仍由操作者执行：
- 在服务器创建 .env（真实 Secret 不写入仓库）
- 申请域名/SSL、按示例替换 Nginx 域名与证书路径
- 用真实手机访问验证（本机无法代替真实设备）
- 部署后执行第 11 节 Smoke Test
