# 竞赛与届次字段审核设计

用户授权：直接完成本轮设计与实现；不重复审批普通开发操作。正式库、schema 不改；不提交远程；上一阶段 PASS 及 R12/R13/R14 保持。当前工作区已有 90 个改动文件，保留并继续。

## 范围与方案

本轮新增可独立使用的字段审核闭环，实体仅 competition / edition。复用 ReviewQueue.raw_value 的版本化 JSON 保存候选字段、来源、提交人及字段处理结果；复用 CompetitionFactSource、CompetitionFactRevision 和 AdminAuditLog 保存正式来源与完整审核前后快照。CandidateCompetition 依赖政策及学校，不适合作为所有用户/爬虫候选的唯一父表；保留其原始资料角色。无需新增表或迁移。

候选提交不得写赛事/届次正式值；来源权重只用于提示。字段白名单区分本体/届次，年月身份不可通过普通字段修改。一个候选只针对一个实体，edition 必须携带对应 competition_id 和明确 edition_id/year。新赛事/新届次只有人工接受必需字段后才创建正式记录。

字段来源使用 official_website、organizer_notice、government_document、university_notice、university_policy、industry_organization、user_submission、third_party、ai_assisted、crawler、manual_entry。来源缺失为 NO_SOURCE；其余默认 UNVERIFIED，由管理员明确核验后才可批准。来源元数据含 title/url/publisher/published_at/collected_at/verified_at/verified_by。人工核验不伪装官网核验，不自动抓取来源链接。

## API 契约

统一前缀 `/api/admin/field-reviews`，全部使用 get_current_admin，响应 `{data: ...}`。

- `GET /config`：`{fields:{competition:[{field_name,display_name,value_type}],edition:[...]},source_types:[{value,label,priority}]}`。
- `POST /`：创建候选；`{entity_type,competition_id?,edition_id?,year?,title,description?,university_id?,origin?:manual_entry|crawler|ai_assisted|user_submission,origin_id?,fields:[{field_name,candidate_value,source?:{source_type,source_title?,source_url?,publisher?,published_at?},confidence?}]}`。同字段可提供多个不同来源/值。缺省候选 source 不代表已核验。
- `GET /`：filters `status`（pending/approved/rejected/partially_approved/all），`flag`（CONFLICT/NO_SOURCE/UNVERIFIED），`entity_type,competition_id,university_id,source_type,submitter_id,created_from,created_to,limit,offset`；返回 `{items:[detail],total}`。
- `GET /{id}`：返回 detail（见下）。
- `PUT /{id}/prepare`：仅处理尚无字段的自由文本候选；同 POST 内容，必须带 preview_token；建立结构化字段，不入正式库。
- `POST /{id}/sources/{proposal_id}/verify`：`{preview_token,note}`。必须有可追踪的来源；由服务端设置核验人/时间，更新 preview_token。
- `POST /{id}/review`：`{preview_token,note,decisions:[{field_name,action:approve|reject|defer,proposal_id?,confirm_delete?:boolean}]}`。approve 必须明确选择 proposal_id；缺省字段保持待处理；拒绝=保留原值；删除另需 confirm_delete。冲突不自动选取。拒绝重复处理字段、过期预览和重复完成审核。
- `POST /bulk-review`：`{items:[{id,preview_token,field_names:[]}],note}`。服务端只允许无冲突、同来源、同实体目标/届次、来源已核验、没有覆盖非空值的字段；整个批量原子提交。UI 仅给符合条件的单候选低风险字段提供批量入口。

detail 为 `{id,title,description,entity_type,competition_id,competition_name,edition_id,year,university_id,submitter_id,origin,status,created_at,preview_token,fields:[{field_name,display_name,current_value,candidate_value,changed,change_type:add|modify|delete|unchanged,verification_state,source,source_url,source_type,confidence,last_verified_at,decision,proposals:[{id,candidate_value,source:{source_type,source_title,source_url,publisher,published_at,collected_at,verified_at,verified_by,verification_state},confidence}]}],flags:[],history:[],bulk_eligible_fields:[]}`。

历史包含 reviewer_id/reviewed_at/note/decisions/before/after/sources，来源核验也保留审核记录。CONFLICT 同时考虑本候选及其他未结束候选对同目标字段提出的不同值，不自动删除任何证据。旧正式来源没有时间/核验人时明确缺失。

## 事务与边界

实现补充：POST `/{id}/reject-unstructured` 使用 `{preview_token,note}`，只允许拒绝零字段待处理材料，保留原证据和未核验来源，关联提交、队列及审计同事务更新。`detail.origin_source_url` 展示原始来源，不充当字段核验；链接变化使旧预览失效。POST `/api/admin/field-review-origins/{kind}/{item_id}` 转入历史材料，先对原提交执行无值变化的UPDATE取得事务写锁，再查询已有候选，从而在SQLite和PostgreSQL中保持并发幂等。

preview_token 覆盖当前正式值及候选版本；审核同时检查队列版本和正式值版本，防止过期页面覆盖后来变化。正式值、来源、修订、关联提交状态、通知/事件与审计必须在一个事务提交，失败全回滚。候选创建、核验、字段审核均通过服务，不允许用户设置 verified_by/verified_at/状态字段。

现有纠错与赛事补充自动产生字段候选；不能可靠提取的自由文本保留为待结构化，管理员先明确实体/字段/届次。旧截止直接批准入口停止写正式表，改为引导字段审核。普通采集通过候选服务；历史导入入口逐步封堵，并增加运行时正式写入保护，未审核不得写 competition/edition 的事实字段。测试 fixture 仅在隔离测试库中设立数据。

## 前端

新增 `/admin/field-review` 并从审核中心进入。列表具备状态/冲突/来源及实体、赛事、学校、提交人、时间筛选。详情每行显示当前值/候选值、变化文字、来源/时间/核验人、冲突替代值和审核选择，默认暂不处理。来源核验与正式批准分两步。显示审核历史并可前往准确届次正式详情。复用会话边界及过期请求保护。

## 验收

测试覆盖用户列出的 15 类情况，补充过期预览、来源伪造、字段白名单、空值删除确认、跨候选冲突、批量限制和原子回滚。真实浏览器完成管理员部分批准、保留原值、正式详情仅显示批准字段。完整后端/前端测试、lint/typecheck/build；正式库 SHA256 前后相同。完成报告后停止，不扩展学校通知、政策或会议审核实体。
