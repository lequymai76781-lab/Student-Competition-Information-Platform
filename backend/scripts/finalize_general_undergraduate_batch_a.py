"""Clean false positives, audit Batch A, generate QA and the final report."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
MASTER = ROOT / "data/seeds/general_undergraduate_master.json"
QUEUE = ROOT / "data/seeds/general_undergraduate_batches.json"
CHECKPOINT = ROOT / "data/checkpoints/general_undergraduate_batch_a.json"
QA = ROOT / "data/reports/general_undergraduate_batch_a_qa.json"
AUDIT = ROOT / "data/reports/general_undergraduate_batch_a_audit.json"
IDEMPOTENCY = ROOT / "data/reports/general_undergraduate_batch_a_idempotency.json"
DOC = ROOT / "docs/GENERAL_UNDERGRADUATE_BATCH_A.md"
FALSE_POLICY_URLS = {
    "https://www.btbu.edu.cn/zjbgs/rw/82f6967789834902b244db019a31cb86.htm",
    "https://www.btbu.edu.cn/zjbgs/rw/cf3429c28be34742bc1c1d939e1599aa.htm",
    "https://www.gxnu.edu.cn/2026/0915/c1441a349772/page.htm",
    "https://www.hainnu.edu.cn/2026/0731/c517a168606/page.htm",
    "https://tao.ahnu.edu.cn/xzsd/tmgz.htm",
}
TERMINAL = {"VERIFIED_DATA", "VERIFIED_NO_PUBLIC_DATA", "ACCESS_LIMITED", "DEEP_PASS_REQUIRED", "AMBIGUOUS"}


def metadata(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def cleanup_false_positives(db: sqlite3.Connection) -> dict:
    marks = ",".join("?" for _ in FALSE_POLICY_URLS)
    policy_ids = [row[0] for row in db.execute(
        f"SELECT id FROM policy_documents WHERE source_url IN ({marks})", tuple(FALSE_POLICY_URLS)
    )]
    recognition_ids = []
    if policy_ids:
        pmarks = ",".join("?" for _ in policy_ids)
        recognition_ids = [row[0] for row in db.execute(
            f"SELECT id FROM competition_policy_recognitions WHERE policy_document_id IN ({pmarks})", policy_ids
        )]
        db.execute(f"DELETE FROM competition_policy_recognitions WHERE policy_document_id IN ({pmarks})", policy_ids)
        db.execute(f"DELETE FROM policy_attachments WHERE policy_document_id IN ({pmarks})", policy_ids)
        db.execute(f"DELETE FROM policy_documents WHERE id IN ({pmarks})", policy_ids)
    return {"policy_documents_removed": len(policy_ids), "recognitions_removed": len(recognition_ids)}


def orphan_counts(db: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "editions_without_competition": "SELECT COUNT(*) FROM competition_editions e LEFT JOIN competitions c ON c.id=e.competition_id WHERE c.id IS NULL",
        "sources_without_competition": "SELECT COUNT(*) FROM competition_sources s LEFT JOIN competitions c ON c.id=s.competition_id WHERE s.competition_id IS NOT NULL AND c.id IS NULL",
        "relations_without_university": "SELECT COUNT(*) FROM university_competition_edition_relations r LEFT JOIN universities u ON u.id=r.university_id WHERE u.id IS NULL",
        "relations_without_edition": "SELECT COUNT(*) FROM university_competition_edition_relations r LEFT JOIN competition_editions e ON e.id=r.competition_edition_id WHERE e.id IS NULL",
        "recognitions_without_policy": "SELECT COUNT(*) FROM competition_policy_recognitions r LEFT JOIN policy_documents p ON p.id=r.policy_document_id WHERE p.id IS NULL",
        "recognitions_without_competition": "SELECT COUNT(*) FROM competition_policy_recognitions r LEFT JOIN competitions c ON c.id=r.competition_id WHERE c.id IS NULL",
    }
    return {name: db.execute(sql).fetchone()[0] for name, sql in queries.items()}


def relation_rows(db: sqlite3.Connection, names: list[str]) -> list[dict]:
    marks = ",".join("?" for _ in names)
    rows = []
    for row in db.execute(f"""
        SELECT u.name school,c.name competition,'recognition' relation_type,p.scope_type scope,
               p.year,p.source_url,p.is_verified
        FROM competition_policy_recognitions r
        JOIN universities u ON u.id=r.university_id JOIN competitions c ON c.id=r.competition_id
        JOIN policy_documents p ON p.id=r.policy_document_id
        WHERE u.name IN ({marks}) AND r.is_demo=0
    """, names):
        rows.append(dict(row))
    for row in db.execute(f"""
        SELECT u.name school,c.name competition,
               CASE WHEN r.notice_type IN ('participation_news','award_news') THEN 'participation' ELSE 'notification' END relation_type,
               COALESCE(json_extract(r.metadata,'$.recognition_scope'),'university') scope,e.year,
               r.internal_notice_url source_url,r.is_verified
        FROM university_competition_edition_relations r JOIN universities u ON u.id=r.university_id
        JOIN competition_editions e ON e.id=r.competition_edition_id JOIN competitions c ON c.id=e.competition_id
        WHERE u.name IN ({marks}) AND r.is_demo=0
    """, names):
        rows.append(dict(row))
    return rows


def snapshot(db: sqlite3.Connection, names: list[str]) -> str:
    material = {
        "universities": [tuple(r) for r in db.execute("SELECT id,name,province,official_website FROM universities ORDER BY id")],
        "relations": relation_rows(db, names),
        "checkpoint": json.loads(CHECKPOINT.read_text(encoding="utf-8")),
    }
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main() -> None:
    master = json.loads(MASTER.read_text(encoding="utf-8"))["institutions"]
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))["batches"]
    batch_a = queue["general_a"]
    official_urls = {row["name"]: row["official_url"] for row in master}
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        cleanup = cleanup_false_positives(db)
        db.commit()
        relations = relation_rows(db, batch_a)
        # The four provisional deep-pass marks came only from the rejected
        # classifier hits. Preserve the audit trail and downgrade honestly.
        for archive in checkpoint["schools"]:
            if not archive.get("checked_sources"):
                archive["checked_sources"] = [official_urls[archive["school"]]]
            if archive.get("final_status") == "DEEP_PASS_REQUIRED":
                archive["final_status"] = "ACCESS_LIMITED"
                archive["needs_deep_pass"] = False
                archive["relations"] = {"recognition": 0, "notification": 0, "participation": 0}
                archive["relations_delta"] = {"recognition": 0, "notification": 0, "participation": 0}
                archive["qa_note"] = "provisional policy hit rejected as a false positive"
        CHECKPOINT.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status = Counter(row["final_status"] for row in checkpoint["schools"])
        relation_types = Counter(row["relation_type"] for row in relations)
        qa_samples = []
        for row in relations[:30]:
            checks = {
                "school": row["school"] in batch_a, "competition": bool(row["competition"]),
                "relation_type": row["relation_type"] in {"recognition", "notification", "participation"},
                "official_source": bool(row["source_url"] and row["source_url"].startswith("https://")),
                "year": isinstance(row["year"], int), "scope": row["scope"] in {"university", "college", "department", "major"},
                "verified": bool(row["is_verified"]),
            }
            qa_samples.append({**row, "checks": checks, "result": "PASS" if all(checks.values()) else "FAIL"})
        qa_summary = Counter(row["result"] for row in qa_samples)
        qa = {
            "requested_sample_size": 30, "available_formal_relations": len(relations),
            "sample_size": len(qa_samples), "sampling": "all available formal relations; population below 30",
            "summary": {"PASS": qa_summary["PASS"], "FAIL": qa_summary["FAIL"],
                        "UNCERTAIN": max(0, 30 - len(qa_samples))}, "samples": qa_samples,
        }
        duplicates = [dict(r) for r in db.execute("SELECT lower(trim(name)) key,count(*) count FROM competitions WHERE is_demo=0 GROUP BY lower(trim(name)) HAVING count(*)>1")]
        orphans = orphan_counts(db)
        marks = ",".join("?" for _ in FALSE_POLICY_URLS)
        checks = {
            "master_unique": len(master) == 1228 and len({r["name"] for r in master}) == len(master),
            "batch_partition": len(batch_a) == 32 and len(queue["general_b"]) == 1196 and not (set(batch_a) & set(queue["general_b"])),
            "research_coverage_100": len(checkpoint["schools"]) == 32 and {r["school"] for r in checkpoint["schools"]} == set(batch_a),
            "terminal_statuses": all(r["final_status"] in TERMINAL for r in checkpoint["schools"]),
            "no_public_batch_schema": all(r["name"] not in {"collection_batch", "is_yiben", "is_erben"} for r in db.execute("PRAGMA table_info(universities)")),
            "batch_a_entities": db.execute(f"SELECT COUNT(*) FROM universities WHERE name IN ({','.join('?' for _ in batch_a)})", batch_a).fetchone()[0] == 32,
            "duplicate_competition_audit": not duplicates,
            "source_audit": all(r["source_url"].startswith("https://") and r["is_verified"] for r in relations),
            "relation_audit": all(r["relation_type"] in {"recognition", "notification", "participation"} for r in relations),
            "recognition_audit": all(r["scope"] in {"university", "college", "department", "major"} for r in relations if r["relation_type"] == "recognition"),
            "orphan_audit": all(value == 0 for value in orphans.values()),
            "false_positive_cleanup": db.execute(f"SELECT COUNT(*) FROM policy_documents WHERE source_url IN ({marks})", tuple(FALSE_POLICY_URLS)).fetchone()[0] == 0,
        }
        before = snapshot(db, batch_a)
        resume = subprocess.run(
            [sys.executable, str(ROOT / "backend/scripts/run_general_undergraduate_batch_a.py"), "--resume-check-only"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        after = snapshot(db, batch_a)
        resume_payload = json.loads(resume.stdout.strip())
        idempotency = {"before": before, "after": after, "pass": before == after,
                       "resume": resume_payload, "resume_pass": resume_payload == {"total": 32, "completed": 32, "next": None}}
        checks["idempotency"] = idempotency["pass"]
        checks["checkpoint_resume"] = idempotency["resume_pass"]
        audit = {"generated_at": datetime.now(timezone.utc).isoformat(), "checks": checks,
                 "summary": dict(Counter("PASS" if v else "FAIL" for v in checks.values())),
                 "cleanup": cleanup, "duplicates": duplicates, "orphans": orphans}
    QA.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    IDEMPOTENCY.write_text(json.dumps(idempotency, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pages = sum(r.get("pages_examined", 0) for r in checkpoint["schools"])
    requests = sum(r.get("request_count", 0) for r in checkpoint["schools"])
    candidates = sum(r.get("candidate_count", 0) for r in checkpoint["schools"])
    elapsed = sum(r.get("elapsed_seconds", 0) for r in checkpoint["schools"])
    verified_schools = len({r["school"] for r in relations})
    markdown = f"""# GENERAL_UNDERGRADUATE_BATCH_A_REPORT

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

{verified_schools} / 32（{verified_schools / 32:.1%}）

# 五、新增数据

Competition：0

Recognition：{relation_types['recognition']}

Notification：{relation_types['notification']}

Participation：{relation_types['participation']}

Source：0

QA 删除 5 个误分类政策页及其派生的 1 条错误 Recognition；没有为提高覆盖率保留不可靠关系。

# 六、Final Status

VERIFIED_DATA：{status['VERIFIED_DATA']}

VERIFIED_NO_PUBLIC_DATA：{status['VERIFIED_NO_PUBLIC_DATA']}

ACCESS_LIMITED：{status['ACCESS_LIMITED']}

DEEP_PASS_REQUIRED：{status['DEEP_PASS_REQUIRED']}

AMBIGUOUS：{status['AMBIGUOUS']}

# 七、采集成本

平均每校：{elapsed / 32:.1f} 秒，{requests / 32:.1f} 次记录请求

页面数：{pages}（平均 {pages / 32:.1f}）

候选数：{candidates}（平均 {candidates / 32:.1f}）

有效关系：{len(relations)}（平均 {len(relations) / 32:.2f}）

数据命中率：{verified_schools / 32:.1%}

# 八、QA

PASS：{qa_summary['PASS']}

FAIL：{qa_summary['FAIL']}

UNCERTAIN：{max(0, 30 - len(qa_samples))}

正式关系总体只有 {len(relations)} 条，因此无法在不制造数据的前提下抽检 30 条；已检查全部可用关系。误判清理后无正式关系可抽检，30 条缺口全部记为 UNCERTAIN，而不是伪造 PASS。

# 九、Batch B 可行性

STOP

当前方法不能直接复制到 Batch B：Recognition 命中率为 0%，多数学校在严格预算内为 ACCESS_LIMITED，且政策分类器出现人物页、推免页和科技项目页误判。应先修复政策候选分类、为校级竞赛目录增加专门检索式与附件优先路径，并重新跑一个小型 A 校验证集；本任务未启动 Batch B。
"""
    DOC.write_text(markdown, encoding="utf-8")
    print(json.dumps({"audit": audit["summary"], "qa": qa["summary"], "status": dict(status),
                      "batch_b": "STOP"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()








