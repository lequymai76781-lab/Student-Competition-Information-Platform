from app.crawler.base import ExtractedCompetitionCandidate, ExtractedRecognitionCandidate
from app.crawler.extractors.policy_classifier import PolicyClassifier


class PolicyRelationExtractor:
    negative_keywords = ["不予认定", "不认可", "不纳入", "不计入", "排除"]
    recognized_keywords = ["认定", "认可", "计入", "列入", "纳入", "加分", "奖励", "目录", "清单", "A类", "B类", "一等奖", "二等奖", "三等奖"]
    usage_keywords: list[tuple[str, list[str]]] = [
        ("recommendation", ["推免", "推荐免试", "保研"]),
        ("comprehensive_evaluation", ["综合测评", "综合素质评价", "综测"]),
        ("scholarship", ["奖学金"]),
        ("innovation_credit", ["创新创业学分", "创新实践学分", "创新学分"]),
        ("competition_reward", ["竞赛奖励", "奖励分"]),
        ("graduation", ["毕业要求", "毕业"]),
    ]

    def extract(
        self,
        candidates: list[ExtractedCompetitionCandidate],
        policy_text: str,
        policy_type: str,
        *,
        title: str = "",
    ) -> list[ExtractedRecognitionCandidate]:
        if not PolicyClassifier().is_recognition_evidence(policy_type, title, policy_text):
            return []
        recognitions: list[ExtractedRecognitionCandidate] = []
        usage_type = self._usage_type(policy_text, policy_type)
        for candidate in candidates:
            evidence = candidate.evidence_text
            if any(keyword in evidence for keyword in self.negative_keywords):
                status = "explicitly_not_recognized"
                confidence = max(candidate.confidence, 0.75)
                manual = False
            elif any(keyword in evidence for keyword in self.recognized_keywords):
                status = "recognized"
                confidence = min(0.9, candidate.confidence)
                manual = confidence < 0.75 or candidate.needs_manual_review
            else:
                status = "insufficient_evidence"
                confidence = min(0.55, candidate.confidence)
                manual = True
            recognitions.append(
                ExtractedRecognitionCandidate(
                    raw_competition_name=candidate.raw_name,
                    recognition_status=status,
                    usage_type=usage_type,
                    evidence_text=evidence,
                    score_text=self._score_text(evidence),
                    confidence=confidence,
                    needs_manual_review=manual,
                )
            )
        return recognitions

    def _usage_type(self, policy_text: str, policy_type: str) -> str:
        for usage_type, keywords in self.usage_keywords:
            if policy_type.startswith(usage_type) or any(keyword in policy_text[:3000] for keyword in keywords):
                return usage_type
        return "other"

    def _score_text(self, evidence: str) -> str | None:
        for keyword in ["加分", "奖励", "A类", "B类", "一等奖", "二等奖", "三等奖"]:
            if keyword in evidence:
                return evidence[:300]
        return None