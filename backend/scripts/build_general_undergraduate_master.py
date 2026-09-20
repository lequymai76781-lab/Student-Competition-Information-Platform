"""Build the internal ordinary-undergraduate master and A/B work queues.

The A/B label is collection metadata only. It is never written to the public
University schema and must not be interpreted as an admissions tier or rank.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

import xlrd


ROOT = Path(__file__).resolve().parents[2]
SOURCE_XLS = ROOT / "data/seeds/2026_national_regular_higher_education_institutions.xls"
SOURCE_JSON = ROOT / "data/seeds/2026_national_regular_higher_education_institutions.json"
MASTER = ROOT / "data/seeds/general_undergraduate_master.json"
QUEUE = ROOT / "data/seeds/general_undergraduate_batches.json"
REPORT = ROOT / "data/reports/general_undergraduate_master.json"
DB = ROOT / "data/v02.sqlite"

# A deliberately bounded nationwide pilot of high-attention, public,
# provincially administered universities. Membership is an internal scheduling
# choice only, not a public classification. Every entry is explicitly reviewed.
BATCH_A_SCHOOLS = {
    "北京工商大学": "https://www.btbu.edu.cn/",
    "天津师范大学": "https://www.tjnu.edu.cn/",
    "河北大学": "https://www.hbu.edu.cn/",
    "山西师范大学": "https://www.sxnu.edu.cn/",
    "内蒙古师范大学": "https://www.imnu.edu.cn/",
    "东北财经大学": "https://www.dufe.edu.cn/",
    "长春理工大学": "https://www.cust.edu.cn/",
    "黑龙江大学": "https://www.hlju.edu.cn/",
    "上海理工大学": "https://www.usst.edu.cn/",
    "江苏大学": "https://www.ujs.edu.cn/",
    "浙江工业大学": "https://www.zjut.edu.cn/",
    "安徽师范大学": "https://www.ahnu.edu.cn/",
    "福建师范大学": "https://www.fjnu.edu.cn/",
    "江西师范大学": "https://www.jxnu.edu.cn/",
    "山东师范大学": "https://www.sdnu.edu.cn/",
    "河南师范大学": "https://www.htu.edu.cn/",
    "湖北大学": "https://www.hubu.edu.cn/",
    "长沙理工大学": "https://www.csust.edu.cn/",
    "深圳大学": "https://www.szu.edu.cn/",
    "广西师范大学": "https://www.gxnu.edu.cn/",
    "海南师范大学": "https://www.hainnu.edu.cn/",
    "重庆邮电大学": "https://www.cqupt.edu.cn/",
    "四川师范大学": "https://www.sicnu.edu.cn/",
    "贵州师范大学": "https://www.gznu.edu.cn/",
    "昆明理工大学": "https://www.kmust.edu.cn/",
    "西藏民族大学": "https://www.xzmu.edu.cn/",
    "西安理工大学": "https://www.xaut.edu.cn/",
    "西北师范大学": "https://www.nwnu.edu.cn/",
    "青海师范大学": "https://www.qhnu.edu.cn/",
    "宁夏医科大学": "https://www.nxmu.edu.cn/",
    "新疆师范大学": "https://www.xjnu.edu.cn/",
    "塔里木大学": "https://www.taru.edu.cn/",
}

# Non-211 universities in the second-round Double First-Class list. 211/985
# institutions are removed from the existing authoritative project seeds.
ADDITIONAL_DOUBLE_FIRST_CLASS = {
    "首都师范大学", "外交学院", "中国人民公安大学", "中国科学院大学",
    "天津工业大学", "天津中医药大学", "山西大学", "上海海洋大学",
    "上海中医药大学", "上海科技大学", "南京邮电大学", "南京林业大学",
    "南京信息工程大学", "南京医科大学", "南京中医药大学", "中国美术学院",
    "宁波大学", "河南大学", "湘潭大学", "广州医科大学", "华南农业大学",
    "广州中医药大学", "南方科技大学", "成都理工大学", "西南石油大学",
    "成都中医药大学",
}


def read_source() -> list[dict]:
    book = xlrd.open_workbook(str(SOURCE_XLS))
    sheet = book.sheet_by_index(0)
    header_row = next(i for i in range(sheet.nrows) if sheet.cell_value(i, 0) == "序号")
    headers = [str(sheet.cell_value(header_row, i)).strip() for i in range(sheet.ncols)]
    rows: list[dict] = []
    for index in range(header_row + 1, sheet.nrows):
        values = [sheet.cell_value(index, i) for i in range(sheet.ncols)]
        if not isinstance(values[0], (int, float)) or not str(values[1]).strip():
            continue
        row = dict(zip(headers, values))
        row["序号"] = int(row["序号"])
        row["学校标识码"] = str(int(row["学校标识码"]))
        for key in ("学校名称", "主管部门", "所在地", "办学层次", "备注"):
            row[key] = str(row.get(key) or "").strip()
        rows.append(row)
    return rows


def seed_names(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("universities", payload) if isinstance(payload, dict) else payload
    names = set()
    for row in rows:
        names.add(row.get("university_name") or row.get("name"))
    return {name for name in names if name}


def relation_counts(db: sqlite3.Connection, university_id: int) -> dict[str, int]:
    recognition = db.execute(
        "SELECT COUNT(*) FROM competition_policy_recognitions WHERE university_id=? AND is_demo=0",
        (university_id,),
    ).fetchone()[0]
    relation_rows = db.execute(
        "SELECT notice_type FROM university_competition_edition_relations WHERE university_id=? AND is_demo=0",
        (university_id,),
    ).fetchall()
    notification = sum(row[0] not in {"participation_news", "award_news"} for row in relation_rows)
    participation = len(relation_rows) - notification
    return {"recognition": recognition, "notification": notification, "participation": participation}


def main() -> None:
    source = read_source()
    SOURCE_JSON.write_text(json.dumps({
        "as_of": "2026-06-17",
        "source_url": "https://www.moe.gov.cn/jyb_xxgk/s5743/s5744/A03/202606/t20260618_1441074.html",
        "rows": source,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    undergraduate = [row for row in source if row["办学层次"] == "本科"]
    priority = seed_names(ROOT / "data/seeds/985_universities.json") | seed_names(
        ROOT / "data/seeds/211_non_985_universities.json"
    ) | ADDITIONAL_DOUBLE_FIRST_CLASS
    specialized = seed_names(ROOT / "data/seeds/specialized_institutions.json") | seed_names(
        ROOT / "data/seeds/specialized_institutions_02.json"
    )
    excluded = priority | specialized
    existing = {}
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        for row in db.execute("SELECT id,name,official_website FROM universities WHERE is_demo=0"):
            existing[row["name"]] = dict(row)
        master = []
        for row in undergraduate:
            name = row["学校名称"]
            if name in excluded:
                continue
            db_row = existing.get(name)
            counts = relation_counts(db, db_row["id"]) if db_row else {
                "recognition": 0, "notification": 0, "participation": 0
            }
            batch = "general_a" if name in BATCH_A_SCHOOLS else "general_b"
            master.append({
                "school_code": row["学校标识码"], "name": name,
                "province": row["所在地"], "authority": row["主管部门"],
                "education_level": "普通本科高校", "public_note": row["备注"] or None,
                "existing_school_id": db_row["id"] if db_row else None,
                "official_url": (db_row or {}).get("official_website") or BATCH_A_SCHOOLS.get(name),
                "collection_batch": batch,
                "relation_counts": counts,
                "coverage_state": "has_relation_data" if any(counts.values()) else (
                    "existing_empty" if db_row else "absent"
                ),
            })
    names = {row["name"] for row in master}
    missing_a = sorted(set(BATCH_A_SCHOOLS) - names)
    if missing_a:
        raise ValueError(f"Batch A schools missing from current MOE master: {missing_a}")
    master.sort(key=lambda row: (row["province"], row["school_code"]))
    batches = {
        "general_a": [row["name"] for row in master if row["collection_batch"] == "general_a"],
        "general_b": [row["name"] for row in master if row["collection_batch"] == "general_b"],
    }
    MASTER.write_text(json.dumps({
        "task": "GENERAL_UNDERGRADUATE_MASTER", "source_as_of": "2026-06-17",
        "internal_only_fields": ["collection_batch"], "institutions": master,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    QUEUE.write_text(json.dumps({
        "task": "GENERAL_UNDERGRADUATE_COVERAGE",
        "warning": "A/B are internal collection queues, not public university levels.",
        "batches": batches,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    states = Counter(row["coverage_state"] for row in master)
    summary = {
        "source_total": len(source), "source_undergraduate": len(undergraduate),
        "excluded_priority_or_specialized": len([r for r in undergraduate if r["学校名称"] in excluded]),
        "target_total": len(master), "database_existing": sum(row["existing_school_id"] is not None for row in master),
        "with_relation_data": states["has_relation_data"],
        "completely_blank": states["existing_empty"] + states["absent"],
        "batch_a": len(batches["general_a"]), "batch_b": len(batches["general_b"]),
        "states": dict(states),
    }
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
