# Human-in-the-loop 人机共审设计
日期：2026-10-07。用户已授权本轮正常本地开发，按附件执行，不增加逐阶段批准。现有未提交成果保留，不提交、重置或部署。

## 范围与选择
新增独立 SQLite 学习库（REVIEW_LEARNING_DB）及管理员 API；业务数据库只用于读取输入和读取已提交审核证据。与业务库共表虽简单但扩大业务写入面；仅日志文件不利于幂等和纠正。因此采用独立、追加式 SQLite，生产业务 schema 无改动。
采用既有纯规则分类器作 shadow-v1 基线，版本含规则源码 SHA256；不训练模型、不调分类阈值、不产生网络预测。预留 predictor role 与 model version 可比较 challenger。
学习功能显式配置启用；数据库路径禁止与业务/正式库相同。运行环境区分 human 与 automation，浏览器不可将 automation 自行升级为 human。真实候选由服务端固定 manifest（候选 id 与快照 hash）确认来源；不凭客户端“human=true”收样本。

## 流程
候选打开自动 POST session：只读输入快照，生成 shadow，返回 session_id / started_at / state，不返回预测。训练输入不读取历史人工 classification/decisions/verification 或评审备注。模型没有业务 Session 写权限。
前端在启用共审时隐藏原机器文档分类、模型建议与预填标签；人工一级类型为空，二级和风险可选。来源/正文/正式字段/冲突材料可见，既有事实安全门保留。系统记录 source_open / decision / submit 服务器时间，不要求额外手动计时。
原字段/学校关系审核照常验证和提交；学习完成 API 只接受当前管理员在 session 开始之后的真实业务 audit，核对候选、输入内容和审计动作。human_action/field/relation/note 取已提交 audit，不信客户端伪造。分类标签来自明确的人类输入，不根据模型补全。缺失维度保留 null，统计各自分母。
失败的业务提交不生成学习样本。业务已成功而学习提交失败允许幂等重试和明确提示；不重放事实批准。session 与用户和业务库身份绑定，拒绝他人、陈旧或变更输入。
每条样本不可 UPDATE/DELETE（SQLite triggers）；纠正追加新样本与 supersedes 链。旧记录内容保留，查询视图显示 superseded/corrected；训练只取当前有效版本。

## 模块接口（冻结）
1. app.services.review_shadow_predictor: predict_shadow(input_features:dict)->dict; MODEL_VERSION:string。字段 shadow_primary_type, shadow_secondary_type, shadow_policy_prediction(bool), shadow_risk_level, shadow_suggested_action, shadow_field_decisions(dict), shadow_confidence, shadow_reason, shadow_model_version, shadow_created_at。
2. app.services.review_learning_metrics: compare_prediction(shadow:dict,human:dict)->dict（primary_match/secondary_match/policy_match/risk_match/action_match/field_match_rate、error_types、correction），performance(examples:list[dict])->dict（windows all/recent_50/recent_100，各指标分母，版本分组），replay_examples(examples,predictor=predict_shadow)->dict。human fields: human_primary_type, human_secondary_type, human_policy(bool|null),human_risk_level,human_action,human_field_decisions(dict field->action),human_relation_decision,human_note。
3. app.services.review_learning_store.ReviewLearningStore(path, namespace='default'): start_session(*,admin_id,candidate_id,input_features,shadow_prediction,provenance)->dict; get_session(session_id,admin_id)->dict; event(session_id,admin_id,event,details=None)->dict; complete(session_id,admin_id,*,human_ground_truth,review_context,decision_key)->dict; examples(active_only=True)->list[dict]; correct(example_id,admin_id,*,human_ground_truth,reason)->dict; create_batch(min_samples=100)->dict; batches()->list[dict]。事件仅source_open/decision/submit。表独立且immutable，session新建幂等按同管理员/候选/快照；完成按decision_key幂等，唯一审核证据不可跨session重复计入。provenance origin=real_candidate, actor_mode=human, dataset_id, candidate_sha256, source=review_audit；automation/synthetic均不可complete进入真实样本。store不访问业务DB。
4. root owns API/service integration/config, frontend consumes /api/admin/review-learning endpoints: GET config {enabled,actor_mode,model_version}; POST /sessions {candidate_id}->public session; POST /sessions/{id}/events {event,details?}; POST /sessions/{id}/complete {human_primary_type,human_secondary_type?,human_risk_level?}->example; GET /performance; GET /examples; POST /examples/{id}/correct {human_ground_truth,reason}; POST /batches {min_samples:100|300|500}; GET /batches; POST /replay. Responses existing success_response data envelope. All auth get_current_admin. Disabled config returns enabled false (no file created).
Frontend new ReviewLearningProvider auto-starts selected candidate; context record and complete invoked by existing review controls; no auto-next. Finish needs captured human labels; explicit primary selection required only when learning enabled. Retry learning-only button for successful business audit. New /admin/review-learning status page includes all/50/100 + denominators, model/version/status and corrected samples. Completed predictions only displayed after commit; no prediction fetch endpoint before completion.

## Statistics and batches
Metrics only real immutable samples, same-source repetitions noted; missing dimensions null and separate denominators. Policy precision undefined without predicted positives; recall undefined without actual positives. Error categories are observed disagreements, not invented causal explanations. Correction true on observed mismatch; suggested training weight 2, no automatic model update. Batches require 100/300/500 new effective examples (not historical replay predictions), immutable canonical snapshot/hash/class distribution. States observing/ready_for_evaluation; no invented trained/challenger approval. Replay does not mutate original shadow predictions, datasets or deploy.

## Validation
TDD isolated pytest and frontend tests; no automatic test accesses formal DB. Prepare isolated copy of genuine pending candidates, separate live learning DB and automation learning DB; genuine candidates in automation checks still do not count as human labels. 10 user-performed independent reviews required for PASS; existing Golden Set remains unchanged and may be used only as explicitly historical replay evidence. Zero/less-than-ten real completions => BLOCKED while all authorized engineering work and review entry still delivered.
Formal database and prior 10 protected inputs SHA256 recorded before/after. No schema migration, formal data writes, collection, model promotion or deployment.

## 集成审查后的明确约束
业务审核请求必须携带 X-Review-Learning-Session；后端提交前校验已保存的人类选择和输入，audit.after 在同一业务事务中记录 session_id / submit_event_id / frozen input hash。无绑定的普通业务请求不能消耗旧会话。成功后后端生成样本，客户端完成接口只作幂等确认/重试。
人工准备/补充上下文是审核轨迹，不作为原始模型答案：原始来源内容指纹必须不变，并有真实 prepare/review audit 才允许上下文变化。模型保存最初打开时输入，实际人工判断材料保存在 business_before/business_after，prepared_during_review 明示变化；来源正文变化拒绝绑定。
HTTP纠正只允许primary/secondary/risk；省略字段保留旧值，显式null可清空。不能改审计动作/字段/关系。纠正请求可安全重试。
关闭模式维持原有页面；开启盲审模式还须清除旧采集包装标题中的分类枚举、派生风险提示，显示真实来源标题，保留来源和实际冲突事实。
