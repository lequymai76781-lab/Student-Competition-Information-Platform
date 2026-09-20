# GENERAL_UNDERGRADUATE_BATCH_A_REPORT

# 一、普通本科 Master

目标：1228
已有：0
新增：32（仅 Batch A 学校实体；未重复创建既有实体）

权威基线为教育部截至 2026-06-17 的全国普通高等学校名单（本科 1412 所）；排除既有 985/211/双一流重点数据和两轮专业院校专项共 184 所。

# 二、内部批次

Batch A：32
Batch B：1196

注意：A/B 仅为采集任务内部拆分，不是公开院校等级，不进入前端或 university 公共 schema。

# 三、Batch A Research Coverage

32 / 32（100%）

# 四、Verified Data Coverage

0 / 32（0.0%）

# 五、新增数据

Competition：0

Recognition：0

Notification：0

Participation：0

Source：0

QA 删除 5 个误分类政策页及其派生的 1 条错误 Recognition；没有为提高覆盖率保留不可靠关系。

# 六、Final Status

VERIFIED_DATA：0

VERIFIED_NO_PUBLIC_DATA：0

ACCESS_LIMITED：32

DEEP_PASS_REQUIRED：0

AMBIGUOUS：0

# 七、采集成本

平均每校：33.2 秒，1.1 次记录请求

页面数：36（平均 1.1）

候选数：0（平均 0.0）

有效关系：0（平均 0.00）

数据命中率：0.0%

# 八、QA

PASS：0

FAIL：0

UNCERTAIN：30

正式关系总体只有 0 条，因此无法在不制造数据的前提下抽检 30 条；已检查全部可用关系。误判清理后无正式关系可抽检，30 条缺口全部记为 UNCERTAIN，而不是伪造 PASS。

# 九、Batch B 可行性

STOP

当前方法不能直接复制到 Batch B：Recognition 命中率为 0%，多数学校在严格预算内为 ACCESS_LIMITED，且政策分类器出现人物页、推免页和科技项目页误判。应先修复政策候选分类、为校级竞赛目录增加专门检索式与附件优先路径，并重新跑一个小型 A 校验证集；本任务未启动 Batch B。

# 十、测试与审计

- Backend pytest：196 passed，0 failed。
- general undergraduate importer / checkpoint 专项：6 passed，0 failed。
- Batch A 完成审计：14 PASS，0 FAIL。
- duplicate competition、relation、source、recognition、orphan、idempotency、checkpoint resume：全部 PASS。
- 全库历史质量审计：9 PASS、2 WARN、2 FAIL；2 个 FAIL 均为既有的 6 个 `verified_official` 赛事只有高校级来源，并非本轮新增。Batch A 新增正式赛事、关系和来源均为 0。