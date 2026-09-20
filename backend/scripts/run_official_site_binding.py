"""Bind verified official competition websites / official notices (S-level).

Every entry below was verified this round by fetching the official page,
checking the page title/body against the competition name, and recording a
local snapshot under data/raw/authority/official_sites/. Entries that could
not be verified (JS shells without title match, campus-only events, municipal
events, uncertain domains) are deliberately NOT included.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import Competition, CompetitionSource
from app.services.fact_intelligence_service import FactIntelligenceService


EVIDENCE_DIR = PROJECT_ROOT / "data" / "raw" / "authority" / "official_sites"


OFFICIAL_ENTRIES = [
    {
        "competition_id": 2,
        "source_url": "https://www.tiaozhanbei.net/",
        "source_type": "competition_official_website",
        "evidence": "tiaozhanbei_home.html",
        "raw_title": "挑战杯 全国大学生课外学术科技作品竞赛和创业计划大赛 官方网站",
        "notes": "页面载明主办：共青团中央、教育部、人力资源社会保障部、中国科协、中国科学院、中国社会科学院、中国工程院、全国学联等",
    },
    {
        "competition_id": 3,
        "source_url": "https://www.tiaozhanbei.net/",
        "source_type": "competition_official_website",
        "evidence": "tiaozhanbei_home.html",
        "raw_title": "挑战杯 全国大学生课外学术科技作品竞赛和创业计划大赛 官方网站",
        "notes": "同一官方平台同时服务课外学术科技作品竞赛与创业计划竞赛两个并列项目",
    },
    {
        "competition_id": 5,
        "source_url": "https://www.nuedc-training.com.cn/",
        "source_type": "competition_official_website",
        "evidence": "nuedc_training_home.html",
        "raw_title": "全国大学生电子设计竞赛培训网",
        "notes": "全国大学生电子设计竞赛官方培训与信息平台（全国组委会指定渠道）",
    },
    {
        "competition_id": 21,
        "source_url": "http://www.3chuang.net/",
        "source_type": "competition_official_website",
        "evidence": "3chuang_home.html",
        "raw_title": "三创赛",
        "notes": "官网域名+标题与赛事一致（JS单页，报名系统在官方域名内）",
    },
    {
        "competition_id": 24,
        "source_url": "https://ucc.fltrp.com/",
        "source_type": "competition_official_website",
        "evidence": "ucc_fltrp_home.html",
        "raw_title": "理解当代中国（外研社·国才杯大赛官网）",
        "notes": "页面载明大赛由北京外国语大学主办、外语教学与研究出版社承办，受教育部高等教育司等指导",
    },
    {
        "competition_id": 32,
        "source_url": "http://www.siemenscup-cimc.org.cn/notice/NoticeDetail?id=2431",
        "source_type": "official_notice",
        "evidence": "siemenscup_2026_notice.html",
        "raw_title": "2026年第二十届CIMC“西门子杯”中国智能制造挑战赛竞赛通知",
        "notes": "官网2026年第二十届竞赛通知；官网载明赛事为国家A类赛事",
    },
    {
        "competition_id": 34,
        "source_url": "https://jsjds.blcu.edu.cn/",
        "source_type": "competition_official_website",
        "evidence": "jsjds_blcu_home.html",
        "raw_title": "中国大学生计算机设计大赛",
        "notes": "全国大赛官网（北京语言大学承办页面）；报名平台 jsjds.com.cn",
    },
    {
        "competition_id": 36,
        "source_url": "https://dasai.lanqiao.cn/",
        "source_type": "competition_official_website",
        "evidence": "lanqiao_home.html",
        "raw_title": "蓝桥杯大赛 — 全国大学生TMT行业赛事",
        "notes": "工业和信息化部人才交流中心主办赛事的官方报名平台（JS单页，标题一致）",
    },
    {
        "competition_id": 46,
        "source_url": "https://rcccaa.drct-caa.org.cn/",
        "source_type": "competition_official_website",
        "evidence": "rcccaa_caa_home.html",
        "raw_title": "自动化学会机器人竞赛与培训部（中国机器人大赛暨RoboCup中国赛官网）",
        "notes": "中国自动化学会机器人竞赛与培训部官网，页面含大赛历年通知",
    },
    {
        "competition_id": 47,
        "source_url": "https://www.cnsoftbei.com/content-18-399-1.html",
        "source_type": "competition_official_website",
        "evidence": "cnsoftbei_organizers.html",
        "raw_title": "“中国软件杯”大学生软件设计大赛主办承办执行单位名称",
        "notes": "官网组织机构页载明主办：工业和信息化部、教育部、江苏省人民政府",
    },
    {
        "competition_id": 59,
        "source_url": "https://www.cdec.org.cn/",
        "source_type": "competition_official_website",
        "evidence": "cdec_home.html",
        "raw_title": "好创意大赛官网（中国好创意暨全国数字艺术设计大赛）",
        "notes": "官网载明入选中国高等教育学会《全国普通高校大学生竞赛分析报告》",
    },
    {
        "competition_id": 63,
        "source_url": "http://www.g-ican.com/competition/details?id=78",
        "source_type": "competition_official_website",
        "evidence": "ican_details.html",
        "raw_title": "iCAN大学生创新创业大赛",
        "notes": "官网页面（g-ican.com 官方声明渠道）",
    },
    {
        "competition_id": 65,
        "source_url": "https://jdsxj.eduyun.cn/",
        "source_type": "competition_official_website",
        "evidence": "jdsxj_eduyun_home.html",
        "raw_title": "第八届中华经典诵写讲大赛官网（国家智慧教育平台域名）",
        "notes": "教育部、国家语委通知指定的官方赛事平台",
    },
    {
        "competition_id": 65,
        "source_url": "http://www.moe.gov.cn/srcsite/A18/s3137/202605/t20260528_1437956.html",
        "source_type": "government_official_notice",
        "evidence": "moe_jdsxj_2026_notice.html",
        "raw_title": "教育部 国家语委关于举办第八届中华经典诵写讲大赛的通知",
        "doc_number": "教语用函〔2026〕1号",
        "published_at": "2026-05-28",
        "notes": "教育部正式主办文件",
    },
    {
        "competition_id": 101,
        "source_url": "http://www.chinaneccs.cn/",
        "source_type": "competition_official_website",
        "evidence": "chinaneccs_home.html",
        "raw_title": "全国大学生英语竞赛-NECCS",
        "notes": "NECCS官方竞赛网站（域名+标题一致）",
    },
    {
        "competition_id": 125,
        "source_url": "https://cpipc.acge.org.cn/cw/hp/2c90801786cfa2b60186de4143390279",
        "source_type": "competition_official_website",
        "evidence": "cpipc_2026_event.html",
        "raw_title": "中国研究生创新实践系列大赛管理平台（第四届中国研究生企业管理创新大赛）",
        "notes": "教育部学位管理与研究生教育司指导，中国学位与研究生教育学会等主办的中国研究生创新实践系列大赛官方平台",
    },
    {
        "competition_id": 28,
        "source_url": "http://www.cnrobocon.net/",
        "source_type": "competition_official_website",
        "evidence": "cnrobocon_home.html",
        "raw_title": "首页-全国大学生机器人大赛ROBOCON",
        "notes": "全国大学生机器人大赛（CURC）ROBOCON官方平台，含大赛章程与历届赛事",
    },
    {
        "competition_id": 35,
        "source_url": "http://www.c4best.cn/",
        "source_type": "competition_official_website",
        "evidence": "c4best_home.html",
        "raw_title": "中国高校计算机大赛（C4）官方平台",
        "notes": "官网平台（摩课云竞赛托管域名 c4best.cn，为多校通知与高教学会目录点名的官方报名平台）",
    },
    {
        "competition_id": 56,
        "source_url": "http://www.cubec.org.cn/",
        "source_type": "competition_official_website",
        "evidence": "cubec_home3.html",
        "raw_title": "全国高校商业精英挑战赛赛事一体化管理平台",
        "notes": "全国高校商业精英挑战赛赛事官方平台（站点旧证书主机名不匹配，已降级仅保存页面标题证据）",
    },
    {
        "competition_id": 100,
        "source_url": "https://www.robomaster.com/zh-CN",
        "source_type": "competition_official_website",
        "evidence": "robomaster_home.html",
        "raw_title": "RoboMaster 机甲大师赛",
        "notes": "RoboMaster 官方站",
    },
    {
        "competition_id": 111,
        "source_url": "http://www.cnrobocon.net/",
        "source_type": "competition_official_website",
        "evidence": "cnrobocon_home.html",
        "raw_title": "首页-全国大学生机器人大赛ROBOCON（ABU RoboCon 全国选拔）",
        "notes": "ABU RoboCon 全国大学生机器人大赛官方平台",
    },
    {
        "competition_id": 114,
        "source_url": "http://net.c4best.cn/",
        "source_type": "competition_official_website",
        "evidence": "c4_net_home.html",
        "raw_title": "中国高校计算机大赛-网络技术挑战赛官方站",
        "notes": "C4 网络技术挑战赛官方子站",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Bind verified official competition websites (S)")
    parser.add_argument("--apply", action="store_true", help="write bindings (default dry-run)")
    parser.add_argument(
        "--report-out",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "v10_official_site_binding_report.json",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    with SessionLocal() as db:
        before_statuses = dict(
            db.execute(
                text("SELECT verification_status, COUNT(*) FROM competitions GROUP BY verification_status")
            ).fetchall()
        )
        plan = []
        for entry in OFFICIAL_ENTRIES:
            competition = db.get(Competition, entry["competition_id"])
            if competition is None:
                plan.append({**entry, "action": "skip_competition_missing"})
                continue
            evidence_path = EVIDENCE_DIR / entry["evidence"]
            existing = db.execute(
                select(CompetitionSource).where(
                    CompetitionSource.competition_id == entry["competition_id"],
                    CompetitionSource.source_url == entry["source_url"],
                )
            ).scalars().first()
            plan.append(
                {
                    "competition_id": entry["competition_id"],
                    "competition_name": competition.name,
                    "source_url": entry["source_url"],
                    "source_type": entry["source_type"],
                    "evidence_exists": evidence_path.exists(),
                    "evidence_bytes": evidence_path.stat().st_size if evidence_path.exists() else 0,
                    "source_exists": existing is not None,
                }
            )
        added = 0
        for entry, row in zip(OFFICIAL_ENTRIES, plan):
            if row.get("action") or row["source_exists"] or dry_run:
                continue
            published = (
                datetime.fromisoformat(entry["published_at"])
                if entry.get("published_at")
                else None
            )
            now = datetime.now(timezone.utc)
            db.add(
                CompetitionSource(
                    competition_id=entry["competition_id"],
                    source_type=entry["source_type"],
                    authority_level="S",
                    source_name=entry["raw_title"],
                    source_url=entry["source_url"],
                    source_repository="official-site-registry-v10",
                    source_platform="official_website",
                    published_at=published,
                    crawled_at=now,
                    retrieved_at=now,
                    is_official=True,
                    is_verified=True,
                    credibility_score=100,
                    reliability_tier=1,
                    verification_status="verified_official",
                    raw_title=entry["raw_title"],
                    metadata_json={
                        "evidence_file": f"data/raw/authority/official_sites/{entry['evidence']}",
                        "doc_number": entry.get("doc_number"),
                        "verification_notes": entry.get("notes"),
                        "verified_at": now.isoformat(),
                    },
                    is_demo=False,
                )
            )
            added += 1
        if not dry_run:
            db.flush()
            service = FactIntelligenceService()
            service.refresh_source_tiers(db)
            service.refresh_verification(db)
            db.commit()
        after_statuses = dict(
            db.execute(
                text("SELECT verification_status, COUNT(*) FROM competitions GROUP BY verification_status")
            ).fetchall()
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "entries": len(OFFICIAL_ENTRIES),
        "source_rows_added": added,
        "plan": plan,
        "status_before": dict(before_statuses),
        "status_after": dict(after_statuses),
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
