from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class PolicyClassification:
    policy_type: str
    scope_type: str
    year: int | None
    latest_available_year: int | None
    confidence: float
    recognition_eligible: bool = False
    reason: str = ""

    @property
    def category(self) -> str:
        return self.policy_type


class PolicyClassifier:
    """Classify student-competition documents before relation extraction."""

    categories = {
        "competition_policy",
        "competition_catalog",
        "competition_notice",
        "competition_result",
        "participation_news",
        "general_policy",
        "innovation_credit_policy",
        "second_classroom_policy",
        "irrelevant",
    }
    policy_document_markers = ("办法", "细则", "规定", "目录", "清单", "分类表", "认定", "学分", "奖励")
    competition_terms = ("学科竞赛", "大学生竞赛", "学生竞赛", "竞赛", "赛事")
    false_positive_terms = (
        "人物风采", "教师风采", "学生风采", "科技特派员", "推荐免试名单",
        "推免名单", "拟录取名单", "申报项目名单", "获奖名单公示",
    )
    non_policy_title_terms = (
        "工作日程", "日程安排", "培养方案", "课程表", "招生简章", "年度报告", "工作总结",
    )
    news_terms = ("喜报", "荣获", "获奖新闻", "再创佳绩", "圆满举行", "成功举办")
    result_terms = ("获奖结果", "比赛结果", "竞赛结果", "成绩公布", "获奖名单")
    notice_terms = ("报名", "组织参加", "参赛通知", "校内选拔", "征集作品", "举办", "申报通知")
    list_terms = ("目录", "清单", "分类表", "分类一览表", "竞赛名单", "分级目录", "赛事库", "竞赛项目")
    recognition_terms = ("认定", "列入", "纳入", "A类", "B类", "I类", "II类", "一级", "二级", "类别", "级别", "分类", "学分", "奖励")
    named_competition_pattern = re.compile(
        r"[^，。；;：:\n]{2,34}(?:大赛|竞赛)|[“\"]?挑战杯[”\"]?"
    )
    signature_terms = ("挑战杯", "互联网+", "数学建模", "电子设计竞赛", "电子竞赛")

    def classify(
        self,
        title: str,
        text: str = "",
        *,
        college_name: str | None = None,
        major_name: str | None = None,
    ) -> PolicyClassification:
        title = title or ""
        corpus = f"{title}\n{text[:12000]}"
        title_competition = any(term in title for term in self.competition_terms)
        body_competition = any(term in corpus for term in self.competition_terms)
        policy_marker = any(term in corpus for term in self.policy_document_markers)

        category = "irrelevant"
        confidence = 0.35
        reason = "no_policy_signal"

        if any(term in title for term in self.non_policy_title_terms):
            category, confidence, reason = "irrelevant", 0.99, "explicit_non_policy_title"
        elif any(term in corpus[:3000] for term in self.false_positive_terms):
            category, confidence, reason = "irrelevant", 0.98, "explicit_false_positive_pattern"
        elif body_competition and any(term in title for term in self.result_terms):
            category, confidence, reason = "competition_result", 0.95, "competition_result_title"
        elif body_competition and any(term in title for term in self.news_terms):
            category, confidence, reason = "participation_news", 0.95, "participation_news_title"
        elif any(term in title for term in self.list_terms) and body_competition:
            category, confidence, reason = "competition_catalog", 0.97, "formal_catalog_title"
        elif any(term in title for term in ("创新创业学分", "创新实践学分", "创新学分")) and policy_marker:
            category, confidence, reason = "innovation_credit_policy", 0.95, "innovation_credit_policy"
        elif "第二课堂" in title and policy_marker:
            category, confidence, reason = "second_classroom_policy", 0.94, "second_classroom_policy"
        elif title_competition and any(term in title for term in ("管理办法", "实施办法", "管理规定", "奖励办法", "奖励方案", "实施细则")):
            category, confidence, reason = "competition_policy", 0.96, "competition_management_policy"
        elif body_competition and any(term in title for term in self.notice_terms + ("通知", "公告", "公示")):
            category, confidence, reason = "competition_notice", 0.91, "competition_action_or_notice"
        elif "第二课堂" in corpus and policy_marker:
            category, confidence, reason = "second_classroom_policy", 0.88, "second_classroom_policy_body"
        elif any(term in corpus for term in ("创新创业学分", "创新实践学分", "创新学分")) and policy_marker:
            category, confidence, reason = "innovation_credit_policy", 0.88, "innovation_credit_policy_body"
        elif policy_marker and body_competition:
            category, confidence, reason = "general_policy", 0.72, "generic_policy_with_competition_reference"

        scope_type = "university"
        if major_name and major_name in corpus:
            scope_type = "major"
        elif college_name or any(keyword in title for keyword in ("学院", "学部", "系")):
            scope_type = "college"

        years = [int(match) for match in re.findall(r"20(?:0\d|1\d|2\d)", corpus)]
        year = max(years) if years else None
        recognition_eligible = self.is_recognition_evidence(category, title, text)
        return PolicyClassification(
            policy_type=category,
            scope_type=scope_type,
            year=year,
            latest_available_year=year,
            confidence=confidence,
            recognition_eligible=recognition_eligible,
            reason=reason,
        )

    def named_competitions(self, text: str) -> set[str]:
        values = {" ".join(match.split()) for match in self.named_competition_pattern.findall(text)}
        return {
            value for value in values
            if value not in {"大学生学科竞赛", "大学生竞赛", "高校学科竞赛", "全国学科竞赛"}
        }

    def is_recognition_evidence(self, policy_type: str, title: str, text: str) -> bool:
        if policy_type not in {
            "competition_catalog", "competition_policy", "innovation_credit_policy", "second_classroom_policy",
        }:
            return False
        corpus = f"{title}\n{text[:30000]}"
        names = self.named_competitions(text)
        has_scope = any(term in corpus for term in self.recognition_terms)
        if policy_type == "competition_catalog":
            return has_scope and len(names) >= 1

        embedded_catalog = bool(
            re.search(
                r"附件\s*\d*\s*[：:]?[\s\S]{0,120}(?:竞赛[\s\S]{0,30}(?:目录|分类一览表)|赛事目录)",
                text,
            )
        ) and len(names) >= 3
        if embedded_catalog:
            return True

        formal_list_density = text.count("全国大学生") + text.count("中国大学生")
        if formal_list_density >= 5 and len(names) >= 5:
            return True

        for marker in ("《目录》", "竞赛认定范围", "赛事认定范围"):
            start = 0
            while True:
                index = text.find(marker, start)
                if index < 0:
                    break
                window = text[max(0, index - 120):index + 600]
                start = index + len(marker)
                if any(example in window for example in ("（如", "(如", "例如", "譬如")):
                    continue
                signature_count = sum(term in window for term in self.signature_terms)
                if signature_count >= 3 and any(term in window for term in ("认定", "加分", "奖励", "计入")):
                    return True
        return False

    def has_policy_document_marker(self, title: str, text: str = "") -> bool:
        classification = self.classify(title, text)
        return classification.policy_type in {
            "competition_policy", "competition_catalog", "general_policy",
            "innovation_credit_policy", "second_classroom_policy",
        }