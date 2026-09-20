# CURRENT_TASK

- Project Stage: Competition Discovery Recall Repair
- Current Version: V0.8.2
- Last Completed Step: V0.8.2 helper API repaired; three-school V0.8.2 batch generated
- Current Metrics:
  - Three-school Page Recall: 58.3% (7/12) — historical metric, below 70% target
  - Three-school Candidate Recall: 54.5% (6/11) — historical metric, below 70% target
  - Three-school Lead Precision: 50.0% (23/46, actionable scope) — below 70% target
- Current Blocker: Discovery Recall still insufficient in three-school regression
- Files Being Modified:
  - backend/app/services/university_radar_discovery_service.py
  - backend/tests/test_v082_discovery_helpers.py
  - backend/scripts/run_v082_three_school_regression.py
- Next Exact Step:
  1. Do not run 15-school acceptance or 112-school full run yet.
  2. Inspect the V0.8.2 funnel for HZAU and WHUT.
  3. Fix the largest funnel loss layer: HZAU missed market-research/Four-New pages; WHUT 403 fallback still finds no usable official page.
  4. Re-run the same three-school regression until Page Recall >= 70% and Candidate Recall >= 70%.
- Do Not Do:
  - Do not expand to non-985/211 universities.
  - Do not add 50,000 third-party competitions.
  - Do not change Competition/Edition/Relation data models.
  - Do not write per-university special cases.
  - Do not use 403/412 as `no_competition`.
- Latest Report: data/reports/v082_discovery_regression_report.md
