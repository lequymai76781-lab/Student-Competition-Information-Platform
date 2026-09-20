"""Academic Conference V1.2 curated student opportunities (per real Edition).

Every row traces back to the official page already curated in V1.1/V1.1.1
edition seeds (official labels, deadlines and student-facing programmes).
Generic "paper submission" rows carry no audience claim; audience is recorded
only when the official page states it (no auto-expansion of "students").
"""

from __future__ import annotations


def _opp(
    series_key: str,
    year: int,
    opportunity_type: str,
    *,
    title: str,
    official_label: str | None = None,
    description: str | None = None,
    audience: list[str] | None = None,
    deadline: str | None = None,
    open_date: str | None = None,
    participation_mode: str | None = None,
    official_url: str,
    evidence: str,
    evidence_status: str = "full_page_verified",
    source_type: str = "conference_official_site",
    source_name: str | None = None,
    official_domain: str | None = None,
    notes: str | None = None,
) -> dict:
    return {
        "series_key": series_key,
        "year": year,
        "opportunity_type": opportunity_type,
        "title": title,
        "official_label": official_label,
        "description": description,
        "audience": audience,
        "deadline": deadline,
        "open_date": open_date,
        "participation_mode": participation_mode,
        "official_url": official_url,
        "evidence": evidence,
        "evidence_status": evidence_status,
        "notes": notes,
        "source": {
            "source_type": source_type,
            "source_name": source_name or f"{title} 官方来源",
            "source_url": official_url,
            "official_domain": official_domain or _domain(official_url),
            "notes": evidence,
        },
    }


def _domain(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0].lower()


OPPORTUNITIES_V12: dict[tuple[str, int], list[dict]] = {
    ("neurips", 2026): [
        _opp(
            "neurips", 2026, "paper_submission",
            title="NeurIPS 2026 论文投稿",
            official_label="Call for Papers",
            description="NeurIPS 2026 官方论文投稿（官方 Dates 页记录 paper deadline）。",
            deadline="2026-05-06",
            official_url="https://neurips.cc/Conferences/2026",
            evidence="NeurIPS 2026 官方会议页 Dates 区域写明论文投稿截止。",
            notes="投稿面向全体研究者开放；未从官方页获得学生专属限制，不写 audience。",
        ),
    ],
    ("splash", 2026): [
        _opp(
            "splash", 2026, "paper_submission",
            title="OOPSLA 研究论文投稿",
            official_label="OOPSLA Research Papers",
            description="SPLASH 2026（OOPSLA）官方研究论文投稿环节。",
            official_url="https://2026.splashcon.org/",
            evidence="SPLASH 2026 官方页面列明 OOPSLA 研究论文、海报与博士生研讨会等环节。",
        ),
        _opp(
            "splash", 2026, "poster",
            title="SPLASH 2026 海报",
            official_label="Posters",
            description="官方海报环节（面向全体投稿人，具体截止以官网当年页为准）。",
            official_url="https://2026.splashcon.org/",
            evidence="SPLASH 2026 官方页面列明海报环节。",
        ),
        _opp(
            "splash", 2026, "doctoral_consortium",
            title="SPLASH 2026 博士生研讨会",
            official_label="Doctoral Consortium",
            description="面向在读博士生的官方博士生研讨会。",
            audience=["phd"],
            official_url="https://2026.splashcon.org/",
            evidence="SPLASH 2026 官方页面列明 doctoral symposium/consortium 环节。",
        ),
    ],
    ("issta", 2026): [
        _opp(
            "issta", 2026, "paper_submission",
            title="ISSTA 2026 论文投稿",
            official_label="Call for Papers",
            description="ISSTA 2026 官方研究论文投稿（与 SPLASH 2026 同期同址）。",
            official_url="https://conf.researchr.org/home/issta-2026",
            evidence="ISSTA 2026 官方会议页确认研究论文投稿环节。",
        ),
    ],
    ("emnlp", 2026): [
        _opp(
            "emnlp", 2026, "paper_submission",
            title="EMNLP 2026 论文投稿",
            official_label="Call for Papers",
            description="EMNLP 2026 官方研究论文投稿。",
            official_url="https://2026.emnlp.org/",
            evidence="EMNLP 2026 官方会议页列明论文投稿环节。",
        ),
    ],
    ("uist", 2026): [
        _opp(
            "uist", 2026, "paper_submission",
            title="UIST 2026 论文投稿",
            official_label="Call for Papers",
            description="UIST 2026 官方研究论文投稿。",
            official_url="https://uist.acm.org/2026/",
            evidence="UIST 2026 官方页面列明论文投稿与海报环节。",
        ),
        _opp(
            "uist", 2026, "poster",
            title="UIST 2026 海报",
            official_label="Posters",
            description="官方海报环节。",
            official_url="https://uist.acm.org/2026/",
            evidence="UIST 2026 官方页面列明海报环节。",
        ),
    ],
    ("aejmc", 2026): [
        _opp(
            "aejmc", 2026, "paper_submission",
            title="AEJMC 2026 论文投稿",
            official_label="Call for Papers",
            description="AEJMC 2026 官方论文投稿（division 投稿日期以各分会为准，年会总页 deadline 为 2026-04-01）。",
            deadline="2026-04-01",
            official_url="https://www.aejmc.org/aejmc-events/conference",
            evidence="AEJMC 官方年会页写明论文投稿截止 2026-04-01。",
        ),
    ],
    ("ecrea_ecc", 2026): [
        _opp(
            "ecrea_ecc", 2026, "poster",
            title="ECC 2026 Poster & Mentoring Programme",
            official_label="Poster & Mentoring Programme",
            description="ECREA ECC 2026 官方海报与导师计划，面向在读博士与硕士；官方提交截止 2026-01-08。",
            audience=["master", "phd"],
            deadline="2026-01-08",
            official_url="https://ecrea2026brno.eu/",
            evidence="ECC 2026 官网 Poster & Mentoring Programme 页面写明面向研究生与截止日期。",
        ),
    ],
    ("easm", 2026): [
        _opp(
            "easm", 2026, "student_forum",
            title="EASM 2026 Student Seminar（学士/硕士）",
            official_label="Student Seminar (bachelor/master)",
            description="EASM 官网大会历史页写明会期含面向学士/硕士的 Student Seminar，作为大会正式议程。",
            audience=["undergraduate", "master"],
            official_url="https://easm.net/easm-european-sport-management-conference/",
            evidence="EASM 官方大会页/历史页写明 student seminar（bachelor/master）安排。",
        ),
        _opp(
            "easm", 2026, "doctoral_consortium",
            title="EASM 2026 PhD Seminar",
            official_label="PhD Student Seminar",
            description="EASM 官网大会历史页写明会期含面向博士生的 PhD Seminar。",
            audience=["phd"],
            official_url="https://easm.net/easm-european-sport-management-conference/",
            evidence="EASM 官方大会页/历史页写明 PhD seminar 安排。",
        ),
    ],
    ("ecer", 2026): [
        _opp(
            "ecer", 2026, "young_scholar_forum",
            title="ECER 2026 Emerging Researchers' Conference",
            official_label="Emerging Researchers' Conference (ERC)",
            description="ECER 2026 官方新兴研究者会议（ERC，2026/8/17-18），面向博士与早期研究者。",
            audience=["phd", "early_career"],
            official_url="https://eera-ecer.de/conferences/ecer-2026-tampere",
            evidence="ECER 2026 官方会议页写明 ERC 为官方新兴研究者/博士会议。",
        ),
    ],
    ("ieee_bigdata", 2026): [
        _opp(
            "ieee_bigdata", 2026, "undergraduate_forum",
            title="IEEE BigData 2026 Undergraduate and REU Consortium",
            official_label="Undergraduate and REU Consortium",
            description="面向本科生与 REU 学生的官方联合研讨会，学生可在会议上汇报工作。",
            audience=["undergraduate"],
            official_url="https://bigdataieee.org/BigData2026",
            evidence="IEEE BigData 2026 官方 Undergraduate and REU Consortium 页面。",
        ),
    ],
    ("cahe_hef", 2026): [
        _opp(
            "cahe_hef", 2026, "abstract_submission",
            title="2026 高等教育国际论坛年会长摘要投稿",
            official_label="大会预通知（长摘要/预报名）",
            description="中国高等教育学会官方预通知：2026 年 12 月初上海举行，预报名与长摘要截止 2026-09-30。",
            deadline="2026-09-30",
            official_url="https://www.cahe.edu.cn/site/content/19528.html",
            evidence="中国高等教育学会官网预通知写明预报名与长摘要截止 2026-09-30。",
            source_type="association_official_notice",
            source_name="中国高等教育学会官网通知",
            official_domain="cahe.edu.cn",
            notes="具体会期与地点以正式通知为准。",
        ),
    ],
}
