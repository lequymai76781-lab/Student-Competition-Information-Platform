# 项目恢复审计：验证附录

验证日期：2026-09-13。

- 数据库审计脚本：通过；成功只读扫描 `data/v02.sqlite` 并生成 `data/reports/project_recovery_audit.json`。
- 公共 API smoke：通过；health、竞赛列表/详情、高校详情、stats、tags 均返回 200。
- Backend pytest（主库临时副本）：154 passed，1 failed。失败项 `test_deadline_reminder_generation_and_idempotency` 表明第二次生成提醒仍新增 1 条；主库未被测试修改。
- Frontend typecheck：通过。
- Frontend production build：通过，17/17 页面生成。沙箱内首次因 `.next/trace` EPERM 失败，宿主环境复测成功。
- Frontend lint：失败，20 errors + 4 warnings；主要是 V0.9 页面/组件的 `no-explicit-any` 与 `react-hooks/set-state-in-effect`，另有未使用 import。
- 会议后端由 pytest 覆盖；当前无会议前端路由，因此不能执行会议列表/详情的浏览器级验证。

上述失败均存在于本轮只读脚本和文档改动之外；本轮没有删除或弱化测试。
