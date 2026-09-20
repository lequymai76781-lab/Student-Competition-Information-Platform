# Academic Conference V1.2 验收报告

## 结论

- 是否引入 ConferenceOpportunity：True
- 原因：现有 ConferenceEdition 只能保存一组会议级 deadline/student tags，无法表达同一届多个学生机会各自独立的 audience/deadline/official_url/evidence（如 EASM 的 bachelor/master Student Seminar 与 PhD Seminar 并存）；故引入轻量 ConferenceOpportunity，避免 Edition 字段爆炸为 has_xxx。

## 验收统计

- conference_series_total：206
- conference_edition_total：132
- opportunity_total：15
- opportunity_2026：15
- opportunity_2027：0
- major_discipline_mapping_total：54

- opportunity_type 分布：{"abstract_submission": 1, "doctoral_consortium": 2, "paper_submission": 6, "poster": 3, "student_forum": 1, "undergraduate_forum": 1, "young_scholar_forum": 1}
- audience 分布：{"early_career": 1, "master": 2, "phd": 4, "undergraduate": 2, "unknown_or_not_stated": 9}
- status 分布：{"open": 1, "closing_soon": 0, "upcoming": 0, "closed": 3, "held": 1, "unknown": 10}
- Student Opportunity 覆盖率：{'editions_total': 132, 'editions_with_opportunity': 11, 'coverage_ratio': 0.0833}
- 2026/2027 Opportunity 覆盖率：{'editions_2026_2027_total': 122, 'editions_2026_2027_with_opportunity': 11, 'coverage_ratio': 0.0902}
- 各学科 actionable opportunity：{"education": 1}
- recognition：{"recognition_records": 36, "records_with_direct_source_url": 36, "by_system_level": {"CCF-A": 26, "CCF-B": 9, "CCF-C": 1}}
- evidence：{"opportunities_total": 15, "full_page_verified": 15, "pending_or_limited": 0, "verified_opportunities": 15}

## 遗留来源债务

- BEA/SCMS/IRE/ECSS/NASPSPA/SC26 等既有 Edition 来源仍为 access_limited/snippet_only 或会期 NULL；本轮未据此创建任何机会。
- 无新增机会证据债务：15/15 机会均 full_page_verified，来源为 S/A 官方页。

## API 修改

- GET /api/conferences/opportunities（edition_id/series_id/opportunity_type/audience/status/year/discipline/actionable/verified_only）
- GET /api/conferences/discipline-mappings
- GET /api/conferences/actionable（Series+Edition+Opportunity+Discipline+Recognition+Evidence 结构化只读）
- GET /api/conferences/actionable-summary（current_actionable_editions/opportunities，按 status/type/audience/discipline 统计）
- GET /api/conferences/summary 增加 opportunities_total 与 actionable
- Series/Edition 列表新增 has_opportunity/opportunity_type/opportunity_audience/actionable 过滤（全部向后兼容）

## pytest：142/142 通过

## 前端就绪判定

- ready：True
- basis：已有 Series/Edition/Opportunity/Discipline/Recognition/Organization/Evidence结构化只读数据与 /actionable、/actionable-summary 聚合；前端可展示‘为什么相关/为什么对学生有价值’的事实与来源。
- 说明：按任务要求，本轮不开始 Conference 前端开发。
