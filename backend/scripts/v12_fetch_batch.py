"""Resilient v12 evidence fetcher: tries multiple URLs, continues on errors."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.fetch_authority_page import fetch  # noqa: E402


TARGETS: list[tuple[str, str]] = [
    # comp99 数学竞赛官方通知原文（18/17/16届 + 2025初赛获奖名单）
    (
        "https://www.cmathc.org.cn/tzgg/545.html",
        "data/raw/authority/cmathc_18th_notice.html",
    ),
    (
        "https://www.cmathc.org.cn/tzgg/201.html",
        "data/raw/authority/cmathc_17th_notice.html",
    ),
    (
        "https://www.cmathc.org.cn/tzgg/88.html",
        "data/raw/authority/cmathc_16th_notice.html",
    ),
    (
        "https://www.cmathc.org.cn/csmd/390.html",
        "data/raw/authority/cmathc_17th_prelim_result.html",
    ),
    # comp2 2025 (19th) 挑战杯官方动态页
    (
        "https://www.tiaozhanbei.net/article/15795/",
        "data/raw/authority/official_sites/tiaozhanbei_2025_19th_article.html",
    ),
    # comp5 2025 获奖名单（正式，上次连接被重置，重试）
    (
        "https://www.nuedc-training.com.cn/index/news/details/new_id/340",
        "data/raw/authority/official_sites/nuedc_2025_result.html",
    ),
    # comp99 数学竞赛公告第2/3页（17届/16届通知入口）
    (
        "https://www.cmathc.org.cn/tzgg_2/",
        "data/raw/authority/cmathc_tzgg_list_2.html",
    ),
    (
        "https://www.cmathc.org.cn/tzgg_3/",
        "data/raw/authority/cmathc_tzgg_list_3.html",
    ),
    # comp1 2024 教育部通知镜像（河南省教育厅转载）
    (
        "https://jyt.henan.gov.cn/2024/05-15/2991257.html",
        "data/raw/authority/moe_2024_innovation_notice_henan_mirror.html",
    ),
    # comp1 2024 教育部通知镜像（国家24365平台）
    (
        "https://24365.smartedu.cn/ncss/jydt/cy/202405/20240514/2293291765.html",
        "data/raw/authority/moe_2024_innovation_notice_24365_mirror.html",
    ),
    # comp1 2024 MOE notice (try https/www/http in order)
    (
        "https://www.moe.gov.cn/srcsite/A08/s5672/202405/t20240513_1130304.html",
        "data/raw/authority/moe_2024_innovation_notice.html",
    ),
    (
        "http://www.moe.gov.cn/srcsite/A08/s5672/202405/t20240513_1130304.html",
        "data/raw/authority/moe_2024_innovation_notice.html",
    ),
    (
        "http://www.moe.gov.cn:8080/srcsite/A08/s5672/202405/t20240513_1130304.html",
        "data/raw/authority/moe_2024_innovation_notice.html",
    ),
    # comp4 2025 first notice list page on mcm.edu.cn
    (
        "https://www.mcm.edu.cn/html_cn/node/26a645851659040725c2892fb1935f95.html",
        "data/raw/authority/mcm_2025_notice_list.html",
    ),
    # comp4 2025 first notice PDF (直接附件)
    (
        "https://www.mcm.edu.cn/upload_cn/node/745/ogFWOgXVc36c27bb3ee3adf21e06f53146b03585.pdf",
        "data/raw/authority/mcm_2025_first_notice.pdf",
    ),
    # comp99 通知公告列表（18届/17届/16届官方通知入口）
    (
        "https://www.cmathc.org.cn/tzgg/",
        "data/raw/authority/cmathc_tzgg_list.html",
    ),
    # comp5 2025 国赛组织通知 / 获奖名单 / 2026 专题赛第一次通知
    (
        "https://www.nuedc-training.com.cn/index/news/details/new_id/330",
        "data/raw/authority/official_sites/nuedc_2025_org_notice.html",
    ),
    (
        "https://www.nuedc-training.com.cn/index/news/details/new_id/340",
        "data/raw/authority/official_sites/nuedc_2025_result.html",
    ),
    (
        "https://www.nuedc-training.com.cn/index/news/details/new_id/345",
        "data/raw/authority/official_sites/nuedc_2026_notice.html",
    ),
    # comp24/107/108 2026 官方通知（大赛官网）
    (
        "https://ucc.fltrp.com/c/2026-04-15/541569.shtml",
        "data/raw/authority/official_sites/fltrp_2026_notice.html",
    ),
]


def main() -> None:
    results: list[dict] = []
    for url, out in TARGETS:
        out_path = BACKEND_DIR.parent / out
        if out_path.exists() and out_path.stat().st_size > 100:
            results.append({"url": url, "out": out, "status": "already_exists"})
            continue
        try:
            result = fetch(url, out_path)
            results.append({"url": url, "out": out, "status": "ok", **result})
        except Exception as exc:  # noqa: BLE001
            results.append({"url": url, "out": out, "status": "error", "error": str(exc)})
    for row in results:
        print(f"{row['status']}\t{row['url']}\t{row.get('size', row.get('error', ''))}\t{row['out']}")


if __name__ == "__main__":
    main()
