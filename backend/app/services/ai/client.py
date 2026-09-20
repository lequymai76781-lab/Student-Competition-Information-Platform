from typing import Protocol


class AIExtractionClient(Protocol):
    def extract_competition(self, text: str) -> dict:
        ...

    def extract_policy(self, text: str) -> dict:
        ...

    def deduplicate_competition(self, candidates: list[dict]) -> dict:
        ...

    def generate_recommendation_reason(self, factors: list[str]) -> str:
        ...


class MockAIExtractionClient:
    """No external AI APIs are called in V0.1."""

    def extract_competition(self, text: str) -> dict:
        return {"mock": True, "title_hint": text[:80], "confidence": 0.0}

    def extract_policy(self, text: str) -> dict:
        return {"mock": True, "policy_hint": text[:80], "confidence": 0.0}

    def deduplicate_competition(self, candidates: list[dict]) -> dict:
        return {"mock": True, "duplicate_groups": [], "candidate_count": len(candidates)}

    def generate_recommendation_reason(self, factors: list[str]) -> str:
        if not factors:
            return "当前推荐理由来自规则评分，尚未接入AI解释。"
        return "；".join(factors)

