import re

from app.crawler.base import ExtractedCompetitionCandidate


class CompetitionExtractor:
    generic_name_pattern = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9“”\"+·\-]{2,40}(?:大赛|竞赛|挑战杯|创新大赛)")

    def extract(self, text: str, known_names: list[str]) -> list[ExtractedCompetitionCandidate]:
        candidates: list[ExtractedCompetitionCandidate] = []
        seen: set[str] = set()
        for name in sorted(known_names, key=len, reverse=True):
            if not name or name in seen:
                continue
            index = text.find(name)
            if index >= 0:
                seen.add(name)
                candidates.append(
                    ExtractedCompetitionCandidate(
                        raw_name=name,
                        normalized_name=name,
                        confidence=0.9,
                        evidence_text=self._window(text, index, len(name)),
                        needs_manual_review=False,
                    )
                )

        for match in self.generic_name_pattern.finditer(text):
            name = self._clean(match.group(0))
            if not name or name in seen or len(name) < 4:
                continue
            seen.add(name)
            candidates.append(
                ExtractedCompetitionCandidate(
                    raw_name=name,
                    normalized_name=None,
                    confidence=0.45,
                    evidence_text=self._window(text, match.start(), len(name)),
                    needs_manual_review=True,
                )
            )
        return candidates

    def _window(self, text: str, start: int, length: int, radius: int = 120) -> str:
        left = max(0, start - radius)
        right = min(len(text), start + length + radius)
        return text[left:right].strip()

    def _clean(self, value: str) -> str:
        return value.strip(" \n\t，。；;：《》()（）[]【】")
