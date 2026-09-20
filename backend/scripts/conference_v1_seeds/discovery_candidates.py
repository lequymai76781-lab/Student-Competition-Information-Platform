"""V1.1 Discovery queue samples (real C-level pages observed during curation).

These entries document third-party pages that appeared in official-site
searches. They only enter the discovery pool - never Series/Edition - and are
either still pending official cross-check or rejected with a controlled reason
so future search passes do not re-review the same noise.
"""

DISCOVERY_CANDIDATES = [
    {
        "raw_name": "USENIX ATC 2026（会议聚合站条目）",
        "year": 2026,
        "acronym": "ATC '26",
        "english_name": "USENIX Annual Technical Conference 2026 (aggregator listing)",
        "organizer_hint": "USENIX Association（待官方确认）",
        "discipline_hint": "computer_science",
        "source_type": "conference_aggregator",
        "source_name": "hyper.ai 会议目录",
        "source_url": "https://hyper.ai/cn/events/30510",
        "source_domain": "hyper.ai",
        "status": "pending",
        "needs_review": True,
        "risk_flags": ["commercial_intermediary_only"],
        "rejection_reason": None,
        "notes": "官方 USENIX 会议页尚未抓到 ATC '26 完整会期（通知/artifact 页日期不一），先留在发现池待官方交叉核验。",
    },
    {
        "raw_name": "ACM/IFIP Middleware 2026（第三方目录条目）",
        "year": 2026,
        "acronym": "Middleware",
        "english_name": "27th ACM/IFIP International Middleware Conference (wikicfp listing)",
        "organizer_hint": "ACM / IFIP",
        "discipline_hint": "computer_science",
        "source_type": "third_party_directory",
        "source_name": "WikiCFP",
        "source_url": "http://wikicfp.com/cfp/servlet/event.showcfp?eventid=190274",
        "source_domain": "wikicfp.com",
        "status": "pending",
        "needs_review": True,
        "risk_flags": ["commercial_intermediary_only"],
        "rejection_reason": None,
        "notes": "wikicfp 条目显示 2026-11-30 至 12-04（西班牙），但官方会议站（middleware-conf.org）未抓到同等日期，需官方交叉核验后再决定是否建档。",
    },
    {
        "raw_name": "61st DAC 2026（导航站日期不一致，无法确认）",
        "year": 2026,
        "acronym": "DAC",
        "english_name": "Design Automation Conference 2026 (directory-only finding)",
        "organizer_hint": "ACM/IEEE（官方组织待核）",
        "discipline_hint": "engineering",
        "source_type": "third_party_directory",
        "source_name": "WikiCFP 目录页",
        "source_url": "http://wikicfp.com/cfp/program?f=DesignAutomationConference&id=634",
        "source_domain": "wikicfp.com",
        "status": "rejected",
        "needs_review": False,
        "risk_flags": ["official_site_missing", "indexing_claim_unverified"],
        "rejection_reason": "unofficial_source_only",
        "notes": "仅有第三方目录条目且互相矛盾（wikiCFP 显示 07-26~29 Long Beach，另一官方协会页面文本错乱），未抓到 DAC 官方 2026 页，按 C 级仅来源拒绝，避免误建 Edition。",
    },
]
