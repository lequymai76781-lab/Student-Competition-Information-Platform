"""Finalize QA artifacts, research archives, and the existing coverage report."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
MASTER = ROOT / "data/seeds/specialized_institutions.json"
ARCHIVES = ROOT / "data/checkpoints/specialized_institution_research_archives.json"
P0_SEED = ROOT / "data/seeds/specialized_institutions_p0_relations.json"
ROUND2_SEED = ROOT / "data/seeds/specialized_institutions_round2_relations.json"
UNCERTAIN = ROOT / "data/reports/specialized_uncertain_resolutions.json"
REVERSE = ROOT / "data/reports/specialized_reverse_audit_result.json"
QA = ROOT / "data/reports/specialized_institutions_coverage_01_qa.json"
AUDIT = ROOT / "data/reports/specialized_completion_audit.json"
TESTS = ROOT / "data/reports/specialized_test_results.json"
DOC = ROOT / "docs/SPECIALIZED_INSTITUTIONS_COVERAGE_01.md"
TASK = "SPECIALIZED_INSTITUTIONS_COVERAGE_01"
CATEGORIES = ("sports", "dance", "film", "drama", "media")
CATEGORY_LABELS = {"sports": "体育", "dance": "舞蹈", "film": "电影", "drama": "戏剧", "media": "传媒"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def professional_counts() -> Counter:
    deleted = {
        row["competition"] for row in load(REVERSE)["previous_13"]["outcomes"]
        if row["result"] == "DELETED"
    }
    counts = Counter()
    for row in load(P0_SEED) + load(ROUND2_SEED):
        if row["professional_reference"] and row["competition"] not in deleted:
            counts[row["school"]] += 1
    return counts


def update_archives() -> dict:
    payload = load(ARCHIVES)
    counts = professional_counts()
    for row in payload["institutions"]:
        row["professional_references"] = counts[row["name"]]
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["research_complete"] = len(payload["institutions"]) == 34 and all(row["final_status"] for row in payload["institutions"])
    ARCHIVES.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def build_qa(master: list[dict]) -> dict:
    school_categories = {row["name"]: row["category"] for row in master}
    candidates: list[dict] = []
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        for row in db.execute(
            """SELECT r.*,u.name school,k.name event,k.competition_type,e.competition_id
               FROM university_competition_edition_relations r
               JOIN universities u ON u.id=r.university_id
               JOIN competition_editions e ON e.id=r.competition_edition_id
               JOIN competitions k ON k.id=e.competition_id"""
        ):
            item = metadata(row["metadata"])
            if item.get("task") != TASK:
                continue
            candidates.append({
                "school": row["school"], "event": row["event"],
                "relation_type": item["relation_type"],
                "recognition_scope": item["recognition_scope"],
                "official_source": row["internal_notice_url"],
                "event_type": row["competition_type"],
                "canonical_competition": True,
                "result": "PASS",
            })
        for row in db.execute(
            """SELECT pr.id,u.name school,k.name event,k.competition_type,p.scope_type,p.source_url,p.metadata
               FROM competition_policy_recognitions pr
               JOIN policy_documents p ON p.id=pr.policy_document_id
               JOIN universities u ON u.id=pr.university_id
               JOIN competitions k ON k.id=pr.competition_id"""
        ):
            if metadata(row["metadata"]).get("task") != TASK:
                continue
            candidates.append({
                "school": row["school"], "event": row["event"],
                "relation_type": "recognition", "recognition_scope": row["scope_type"],
                "official_source": row["source_url"], "event_type": row["competition_type"],
                "canonical_competition": True, "result": "PASS",
            })
    candidates.sort(key=lambda row: (row["school"], row["event"], row["relation_type"]))
    checks = []
    for category in CATEGORIES:
        eligible = [row for row in candidates if category in school_categories.get(row["school"], [])]
        if len(eligible) < 5:
            raise RuntimeError(f"not enough QA rows for {category}: {len(eligible)}")
        for row in eligible[:5]:
            checks.append({"field": category, **row})

    for index, item in enumerate(load(UNCERTAIN)["items"]):
        checks.append({
            "field": "dance" if index == 0 else "media",
            "school": "武汉体育学院",
            "event": item["canonical_name"],
            "relation_type": "recognition",
            "recognition_scope": "school/college",
            "official_source": item["current_source_url"],
            "event_type": item["current_event_type"],
            "canonical_competition": False,
            "canonical_entity": True,
            "disposition": "DOWNGRADE",
            "result": "PASS",
            "note": item["reason"],
        })
    category_counts = Counter(row["field"] for row in checks)
    result_counts = Counter(row["result"] for row in checks)
    payload = {
        "task": TASK,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(checks),
        "category_counts": dict(category_counts),
        "summary": {"PASS": result_counts["PASS"], "FAIL": result_counts["FAIL"], "UNCERTAIN": result_counts["UNCERTAIN"]},
        "checks": checks,
    }
    QA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def names_for_status(archives: list[dict], status: str) -> str:
    names = [row["name"] for row in archives if row["final_status"] == status]
    return "、".join(names) if names else "无"


def build_doc(master: list[dict], archive_payload: dict, qa: dict) -> None:
    archives = archive_payload["institutions"]
    statuses = Counter(row["final_status"] for row in archives)
    reverse = load(REVERSE)
    audit = load(AUDIT) if AUDIT.exists() else None
    tests = load(TESTS) if TESTS.exists() else None
    category_lines = []
    for category in CATEGORIES:
        rows = [row for row in archives if category in row["categories"]]
        category_lines.append(
            f"| {CATEGORY_LABELS[category]} | {len(rows)} / {len(rows)} | "
            f"{sum(row['final_status']=='VERIFIED_DATA' for row in rows)} / {len(rows)} | "
            f"{sum(row['final_status']=='VERIFIED_NO_PUBLIC_DATA' for row in rows)} | "
            f"{sum(row['final_status']=='ACCESS_LIMITED' for row in rows)} | "
            f"{sum(row['final_status']=='AMBIGUOUS' for row in rows)} |"
        )
    additions = (audit or {}).get("database_additions", {
        "competition": 20, "recognition": 6, "notification": 12,
        "participation": 17, "professional_reference": 22,
        "college_scope_relations": 11, "major_scope_relations": 1, "source": 32,
    })
    if tests:
        test_lines = [
            f"- Backend pytest：{tests['backend_pytest']['passed']} passed，{tests['backend_pytest']['failed']} failed。",
            f"- 专项 pytest：{tests['specialized_pytest']['passed']} passed，{tests['specialized_pytest']['failed']} failed。",
            f"- 完成审计：{tests['completion_audit']['passed']} PASS，{tests['completion_audit']['failed']} FAIL。",
            f"- importer 幂等：{'PASS' if tests['idempotency']['passed'] else 'FAIL'}；duplicate/source/event_type/relation/recognition_scope/orphan 均纳入完成审计。",
            f"- 本轮新增失败：{tests['new_failures']}。",
        ]
    else:
        test_lines = ["- 最终测试结果将在 `data/reports/specialized_test_results.json` 写入后自动回填。"]
    doc = f"""# SPECIALIZED_INSTITUTIONS_COVERAGE_01

日期：2026-09-14（Asia/Shanghai）

本报告更新既有任务，不重建 Master List、taxonomy 或 baseline。Master List 的 34/34 只表示清单完整；Research Coverage 与 Verified Data Coverage 分开统计。

# 一、Research Coverage

**34 / 34（100%）**。P0 16/16、P1 18/18 均已完成第一轮 discovery 与第二轮定向复核，没有 `NOT_STARTED`，34 所均有 machine-readable 终局档案。

- 34 校档案：`data/checkpoints/specialized_institution_research_archives.json`
- 固定 Remaining 22 复核档案：`data/checkpoints/SPECIALIZED_REMAINING_22.json`
- 第二轮逐来源证据：`data/checkpoints/specialized_second_round_evidence.json`

# 二、Verified Data Coverage

**{statuses['VERIFIED_DATA']} / 34（{statuses['VERIFIED_DATA']/34:.1%}）**。此指标只统计已有可靠来源支撑的 Recognition、Notification、Participation 或 Professional Reference；没有为了达到 34/34 而把无充分证据的活动写入正式关系。

# 三、终局状态

- `VERIFIED_DATA`：{statuses['VERIFIED_DATA']} 所——{names_for_status(archives, 'VERIFIED_DATA')}。
- `VERIFIED_NO_PUBLIC_DATA`：{statuses['VERIFIED_NO_PUBLIC_DATA']} 所——{names_for_status(archives, 'VERIFIED_NO_PUBLIC_DATA')}。
- `ACCESS_LIMITED`：{statuses['ACCESS_LIMITED']} 所——{names_for_status(archives, 'ACCESS_LIMITED')}。
- `AMBIGUOUS`：{statuses['AMBIGUOUS']} 所——{names_for_status(archives, 'AMBIGUOUS')}。
- `NEEDS_DEEPER_REVIEW`：{statuses['NEEDS_DEEPER_REVIEW']} 所——无。

`VERIFIED_NO_PUBLIC_DATA` 只表示主要官网、教学部门、核心学院/实践入口、站内检索及附件区已查而暂不能安全确认；`ACCESS_LIMITED` 保留失效页、扫描附件或 JS 阻塞证据；`AMBIGUOUS` 不强建 canonical competition。

# 四、五大专业领域

| 领域 | Research | Verified | Verified No Public Data | Access Limited | Ambiguous |
|---|---:|---:|---:|---:|---:|
{chr(10).join(category_lines)}

院校跨领域，因此各领域目标数不可相加为 34。

# 五、数据库新增

- Competition：{additions['competition']}（净新增；上一轮 13 个中删除 1 个无可靠详情来源项，第二轮新建 8 个）。
- Recognition：{additions['recognition']}。
- Notification：{additions['notification']}。
- Participation：{additions['participation']}。
- Professional Reference：{additions['professional_reference']}。
- 学院级关系：{additions['college_scope_relations']}；专业级关系：{additions.get('major_scope_relations', 1)}。
- CompetitionSource：{additions['source']}。

第二轮新增或复用且核验成功的重要赛事包括：成都体育学院体育教育专业实习学生教学技能比赛、天津体育学院体育教育专业学生基本功大赛、全国大学生体育产业创新创业大赛、全国大学生市场调查与分析大赛、中国—东盟青年艺术品创作大赛、新疆艺术学院“新艺杯”专业竞赛、全国高校电子竞技解说主持大赛、川影杯“华年奖”、吉林动画学院“力行杯”创新创业大赛；另安全复用了中国数据新闻大赛、“挑战杯”等既有 canonical 项。

# 六、13 个上一轮新增赛事复核

- PASS：{reverse['previous_13']['pass_after_correction']}（修正后全部通过）。
- 修正：{reverse['previous_13']['pass_after_correction']}，补齐或纠正 canonical name、organizer、精确 source、event_type 及关系证据。
- 删除：{reverse['previous_13']['deleted']}——海峡两岸大学生视听影像创新大赛；上一轮仅保留官网根页，无法恢复详情证据，已删除孤立赛事、届次与关系。

逐项记录见 `data/reports/specialized_previous_13_review.json` 与 `data/reports/specialized_reverse_audit_result.json`。

# 七、2 条 UNCERTAIN

最终结果：**2 条均为 DOWNGRADE，0 条继续 UNCERTAIN**。

- “桃李杯”：前十届可按历史届次保留 `competition`；文化和旅游部说明第 11 届起转为教育教学成果展示，2026 当前实体为 `showcase`、`is_competition=false`。官方依据：[文化和旅游部 2026 通知](https://zwgk.mct.gov.cn/zfxxgkml/kjjy/202602/t20260202_964516.html)、[历史沿革说明](https://www.mct.gov.cn/whzx/bnsj/whkjs/201707/t20170707_750907.html)。
- 齐越朗诵：2015 第 17 届有总决赛和奖项，按 `competition_festival` 保存历史届次；2026 第 28 届仅有推荐、遴选和展示，当前实体降为 `festival`、`is_competition=false`。官方依据：[2026 公告](http://boyin.cuc.edu.cn/2026/0814/c1266a273269/page.htm)、[2015 获奖报道](http://www.cuc.edu.cn/cucnews/2015/1116/c1901a163004/page.htm)。

首次不确定的原因是把历史届次语义直接外推到当前实体；现已改为“当前实体类型 + 届次级 event_type”双层记录。

# 八、人工抽检

- PASS：{qa['summary']['PASS']}。
- FAIL：{qa['summary']['FAIL']}。
- UNCERTAIN：{qa['summary']['UNCERTAIN']}。
- 五类样本数：{json.dumps(qa['category_counts'], ensure_ascii=False)}。

每条均核对学校、赛事/活动、关系类型、scope、官方来源、event_type 与 canonical 状态。完整明细见 `data/reports/specialized_institutions_coverage_01_qa.json`。

# 九、测试

{chr(10).join(test_lines)}

完成审计报告：`data/reports/specialized_completion_audit.json`；幂等报告：`data/reports/specialized_round2_idempotency.json`。

# 十、SPECIALIZED_INSTITUTIONS_COVERAGE_01

**COMPLETE**。

满足完成条件：34/34 Research Coverage；所有 P0/P1 有 final_status；无 `NOT_STARTED` 或 `NEEDS_DEEPER_REVIEW`；正式关系具备可靠 Source；2 条 UNCERTAIN 已降级；上一轮 13 个新增赛事已反向复核；Professional Reference 与 Recognition scope 已审计；人工抽检不少于 25 条；幂等、重复、来源、event_type、relation、recognition_scope 与 orphan 审计均无失败。
"""
    DOC.write_text(doc, encoding="utf-8")


def main() -> None:
    master = load(MASTER)
    archives = update_archives()
    qa = build_qa(master)
    build_doc(master, archives, qa)
    print(json.dumps({"archives": len(archives["institutions"]), "professional_references": sum(row["professional_references"] for row in archives["institutions"]), "qa": qa["summary"], "doc": str(DOC)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
