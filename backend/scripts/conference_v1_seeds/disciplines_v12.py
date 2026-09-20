"""Academic Conference V1.2 series-level discipline facts (V1.2 enrichment).

Only high-confidence official positioning is recorded. Each entry keeps the
official source page that supports the discipline claim; no AI inference.
"""

from __future__ import annotations


def _evidence_row(
    *,
    discipline: str,
    role: str,
    basis: str,
    source_url: str,
    official_domain: str,
) -> dict:
    return {
        "discipline": discipline,
        "role": role,
        "basis": basis,
        "source_url": source_url,
        "official_domain": official_domain,
        "retrieved_at": "2026-09-06",
    }


SERIES_DISCIPLINE_V12: dict[str, dict] = {
    "isoj": {
        "secondary_disciplines": ["data_science"],
        "discipline_evidence": [
            _evidence_row(
                discipline="journalism_communication",
                role="primary",
                basis="官方定位为在线/数字新闻国际研讨会（德克萨斯大学奥斯汀分校主办）。",
                source_url="https://isoj.org/",
                official_domain="isoj.org",
            ),
            _evidence_row(
                discipline="data_science",
                role="secondary",
                basis="官方议程长期覆盖数据新闻、新闻自动化与受众数据研究主题。",
                source_url="https://isoj.org/",
                official_domain="isoj.org",
            ),
        ],
    },
    "websci": {
        "secondary_disciplines": ["computer_science"],
        "discipline_evidence": [
            _evidence_row(
                discipline="data_science",
                role="primary",
                basis="官方定位为 Web/网络科学与计算社会科学交叉国际会议。",
                source_url="https://websci26.org/",
                official_domain="websci26.org",
            ),
            _evidence_row(
                discipline="computer_science",
                role="secondary",
                basis="ACM 主办并覆盖 Web 系统、人机交互与算法研究主题。",
                source_url="https://websci26.org/",
                official_domain="websci26.org",
            ),
        ],
    },
    "lak": {
        "secondary_disciplines": ["data_science"],
        "discipline_evidence": [
            _evidence_row(
                discipline="education",
                role="primary",
                basis="官方定位为学习分析方向国际会议（SoLAR 主办）。",
                source_url="https://www.solaresearch.org/",
                official_domain="solaresearch.org",
            ),
            _evidence_row(
                discipline="data_science",
                role="secondary",
                basis="会议核心为教育数据挖掘与学习分析算法/方法研究。",
                source_url="https://www.solaresearch.org/",
                official_domain="solaresearch.org",
            ),
        ],
    },
    "wapor": {
        "secondary_disciplines": ["data_science"],
        "discipline_evidence": [
            _evidence_row(
                discipline="journalism_communication",
                role="primary",
                basis="官方定位为舆论研究国际年会（与传播研究交叉）。",
                source_url="https://wapor.org/",
                official_domain="wapor.org",
            ),
            _evidence_row(
                discipline="data_science",
                role="secondary",
                basis="学会核心领域为调查方法、统计与民意数据研究。",
                source_url="https://wapor.org/",
                official_domain="wapor.org",
            ),
        ],
    },
}
