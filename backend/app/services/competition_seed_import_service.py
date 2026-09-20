from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionAlias, CompetitionSource
from app.services.competition_normalization_service import CompetitionNormalizationService


GITHUB_REPOSITORY = "Tomzkl/college-competitions-skill"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}"


@dataclass(slots=True)
class CompetitionSeedRecord:
    name: str
    category: str | None = None
    organizer: str | None = None
    official_website: str | None = None
    typical_schedule: str | None = None
    team_type: str | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None
    description: str | None = None
    aliases: list[str] = field(default_factory=list)
    raw_content: str | None = None


class CompetitionSeedImportService:
    """Import discovery seeds without treating them as policy or official evidence."""

    canonical_rules = (
        ("中国国际互联网+大学生创新创业大赛", "中国国际大学生创新大赛", ["互联网+", "中国“互联网+”大学生创新创业大赛"]),
        ("挑战杯全国大学生课外学术科技作品竞赛大挑", "“挑战杯”全国大学生课外学术科技作品竞赛", ["挑战杯大挑", "大挑"]),
        ("挑战杯中国大学生创业计划竞赛小挑", "“挑战杯”中国大学生创业计划竞赛", ["挑战杯小挑", "小挑"]),
        ("全国大学生电子商务创新创意及创业挑战赛三创赛", "全国大学生电子商务“创新、创意及创业”挑战赛", ["三创赛"]),
        ("acmicpc国际大学生程序设计竞赛", "ACM-ICPC国际大学生程序设计竞赛", ["ACM-ICPC", "ICPC"]),
        ("蓝桥杯全国软件和信息技术专业人才大赛", "蓝桥杯全国软件和信息技术专业人才大赛", ["蓝桥杯"]),
        ("中国软件杯大学生软件设计大赛", "“中国软件杯”大学生软件设计大赛", ["中国软件杯"]),
        ("中国高校计算机大赛cccc", "中国高校计算机大赛", ["CCCC"]),
        ("全国大学生数学建模竞赛cumcm国赛", "全国大学生数学建模竞赛", ["CUMCM", "数模国赛"]),
        ("美国大学生数学建模竞赛mcmicm", "美国大学生数学建模竞赛", ["MCM/ICM", "数模美赛"]),
        ("全国大学生电子设计竞赛电赛", "全国大学生电子设计竞赛", ["电赛"]),
        ("全国大学生智能汽车竞赛智能车", "全国大学生智能汽车竞赛", ["智能车"]),
        ("robomaster机甲大师赛", "RoboMaster机甲大师赛", ["RoboMaster"]),
        ("全国大学生机械创新设计大赛", "全国大学生机械创新设计大赛", ["机械创新设计大赛"]),
        ("全国大学生结构设计竞赛", "全国大学生结构设计竞赛", ["结构设计竞赛"]),
        ("西门子杯中国智能制造挑战赛", "“西门子杯”中国智能制造挑战赛", ["西门子杯"]),
        ("全国大学生英语竞赛neccs大英赛", "全国大学生英语竞赛", ["NECCS", "大英赛"]),
        ("外研社国才杯全国英语系列赛", "外研社·国才杯“理解当代中国”全国大学生外语能力大赛", ["外研社·国才杯", "外研社英语系列赛"]),
        ("全国大学生广告艺术大赛大广赛", "全国大学生广告艺术大赛", ["大广赛"]),
        ("全国大学生生命科学竞赛", "全国大学生生命科学竞赛", []),
        ("全国大学生化学实验创新设计大赛", "全国大学生化学实验创新设计大赛", []),
        ("华为ict大赛", "华为ICT大赛", ["Huawei ICT Competition"]),
        ("全国大学生数学竞赛", "全国大学生数学竞赛", []),
        ("中美青年创客大赛", "中美青年创客大赛", []),
    )
    legacy_series_tokens = {
        "外研社·国才杯“理解当代中国”全国大学生外语能力大赛": "外研社全国大学生英语系列赛",
        "中国高校计算机大赛": "中国高校计算机大赛",
    }

    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()

    def import_file(
        self,
        db: Session,
        path: Path,
        *,
        source_repository: str = GITHUB_REPOSITORY,
        source_file: str | None = None,
        commit_sha: str | None = None,
    ) -> dict[str, int]:
        records = self.parse_file(path)
        stats = self.import_records(
            db,
            records,
            source_repository=source_repository,
            source_file=source_file or path.name,
            commit_sha=commit_sha,
        )
        stats["parsed"] = len(records)
        return stats

    def parse_file(self, path: Path) -> list[CompetitionSeedRecord]:
        suffix = path.suffix.lower()
        if suffix in {".md", ".markdown"}:
            return self._parse_markdown(path.read_text(encoding="utf-8"))
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("competitions", payload) if isinstance(payload, dict) else payload
            return [self._record_from_mapping(item) for item in items]
        if suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                return [self._record_from_mapping(item) for item in csv.DictReader(source)]
        raise ValueError(f"Unsupported competition seed format: {suffix}")

    def import_records(
        self,
        db: Session,
        records: list[CompetitionSeedRecord],
        *,
        source_repository: str,
        source_file: str,
        commit_sha: str | None = None,
    ) -> dict[str, int]:
        stats = {"created": 0, "matched": 0, "enriched": 0, "sources_created": 0, "aliases_created": 0}
        for record in records:
            canonical_name, rule_aliases = self._canonical_name(record.name)
            competition = self._find_exact(db, canonical_name, [record.name, *record.aliases, *rule_aliases])
            if competition is None:
                competition = Competition(
                    name=canonical_name,
                    category=record.category,
                    description=record.description,
                    organizer=record.organizer,
                    official_website=record.official_website,
                    typical_schedule=record.typical_schedule,
                    team_type=record.team_type,
                    min_team_size=record.min_team_size,
                    max_team_size=record.max_team_size,
                    competition_type="competition",
                    status="active",
                    is_demo=False,
                )
                db.add(competition)
                db.flush()
                stats["created"] += 1
            else:
                stats["matched"] += 1
                if self._enrich(competition, record):
                    stats["enriched"] += 1

            for alias in self._unique([record.name, *record.aliases, *rule_aliases]):
                if not alias or self.normalizer._normalize_text(alias) == self.normalizer._normalize_text(competition.name):
                    continue
                before = len(competition.aliases)
                self.normalizer.ensure_alias(
                    db,
                    competition,
                    alias,
                    source="github_seed",
                    confidence=0.9,
                    is_verified=False,
                )
                if len(competition.aliases) > before:
                    stats["aliases_created"] += 1

            source = db.execute(
                select(CompetitionSource).where(
                    CompetitionSource.competition_id == competition.id,
                    CompetitionSource.source_repository == source_repository,
                    CompetitionSource.source_file == source_file,
                )
            ).scalar_one_or_none()
            source_url = f"https://github.com/{source_repository}/blob/main/{source_file}"
            metadata = {"license": "MIT", "commit_sha": commit_sha, "record": asdict(record)}
            if source is None:
                db.add(
                    CompetitionSource(
                        competition_id=competition.id,
                        source_type="github_seed",
                        source_name="大学生竞赛生存手册竞赛图鉴",
                        source_url=source_url,
                        source_repository=source_repository,
                        source_file=source_file,
                        source_platform="github",
                        is_official=False,
                        is_verified=False,
                        credibility_score=45,
                        raw_title=record.name,
                        raw_content=record.raw_content,
                        content_hash=hashlib.sha256((record.raw_content or record.name).encode("utf-8")).hexdigest(),
                        metadata_json=metadata,
                        is_demo=False,
                    )
                )
                stats["sources_created"] += 1
            else:
                source.metadata_json = metadata
                source.raw_content = record.raw_content
                source.content_hash = hashlib.sha256((record.raw_content or record.name).encode("utf-8")).hexdigest()

        db.commit()
        return stats

    def _parse_markdown(self, text: str) -> list[CompetitionSeedRecord]:
        category: str | None = None
        current_name: str | None = None
        current_lines: list[str] = []
        records: list[CompetitionSeedRecord] = []

        def flush() -> None:
            if current_name:
                records.append(self._record_from_section(current_name, category, current_lines))

        for line in text.splitlines():
            category_match = re.match(r"^##\s+([^#].+?)\s*$", line)
            competition_match = re.match(r"^###\s+\d+\.\s+(.+?)\s*$", line)
            if competition_match:
                flush()
                current_name = competition_match.group(1).strip()
                current_lines = []
                continue
            if category_match and not current_name:
                title = category_match.group(1).strip()
                if title not in {"目录", "创新创业类"} and not title.startswith("附录"):
                    category = title.removesuffix("类")
                elif title == "创新创业类":
                    category = "创新创业"
                continue
            if category_match and current_name:
                flush()
                current_name = None
                current_lines = []
                title = category_match.group(1).strip()
                category = None if title.startswith("附录") else title.removesuffix("类")
                continue
            if current_name:
                current_lines.append(line)
        flush()
        return records

    def _record_from_section(self, name: str, category: str | None, lines: list[str]) -> CompetitionSeedRecord:
        body = "\n".join(lines).strip()
        values: dict[str, str] = {}
        for line in lines:
            match = re.match(r"^-\s+\*\*(.+?)\*\*[：:]\s*(.+)$", line.strip())
            if match:
                values[match.group(1).strip()] = match.group(2).strip()
        schedule = values.get("周期")
        format_text = values.get("赛制")
        min_size, max_size = self._team_sizes(format_text)
        team_type = None
        if format_text:
            if "团队" in format_text or max_size and max_size > 1:
                team_type = "团队赛"
            elif "个人" in format_text:
                team_type = "个人赛"
        description_parts = [f"{category}方向" if category else None, schedule, format_text]
        description = "；".join(part.rstrip("。") for part in description_parts if part)
        website = values.get("官网")
        if website and not website.startswith(("http://", "https://")):
            website = f"https://{website}"
        return CompetitionSeedRecord(
            name=name,
            category=category,
            organizer=values.get("主办方"),
            official_website=website,
            typical_schedule=schedule,
            team_type=team_type,
            min_team_size=min_size,
            max_team_size=max_size,
            description=f"{description}。" if description else None,
            aliases=self._heading_aliases(name),
            raw_content=body,
        )

    def _record_from_mapping(self, item: dict[str, Any]) -> CompetitionSeedRecord:
        aliases = item.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [value.strip() for value in re.split(r"[,，;；]", aliases) if value.strip()]
        return CompetitionSeedRecord(
            name=str(item["name"]).strip(),
            category=item.get("category"),
            organizer=item.get("organizer"),
            official_website=item.get("official_website") or item.get("website"),
            typical_schedule=item.get("typical_schedule") or item.get("schedule"),
            team_type=item.get("team_type"),
            min_team_size=self._optional_int(item.get("min_team_size")),
            max_team_size=self._optional_int(item.get("max_team_size")),
            description=item.get("description"),
            aliases=aliases,
            raw_content=item.get("raw_content"),
        )

    def _find_exact(self, db: Session, canonical_name: str, aliases: list[str]) -> Competition | None:
        normalized_candidates = {
            self.normalizer._normalize_text(value)
            for value in [canonical_name, *aliases]
            if value
        }
        competitions = list(db.execute(select(Competition)).scalars().all())
        for competition in competitions:
            if self.normalizer._normalize_text(competition.name) in normalized_candidates:
                return competition
        legacy_token = self.legacy_series_tokens.get(canonical_name)
        if legacy_token:
            normalized_token = self.normalizer._normalize_text(legacy_token)
            legacy_matches = [
                competition
                for competition in competitions
                if normalized_token in self.normalizer._normalize_text(competition.name)
            ]
            if len(legacy_matches) == 1:
                return legacy_matches[0]
        alias_rows = list(db.execute(select(CompetitionAlias)).scalars().all())
        matches = {row.competition for row in alias_rows if row.normalized_alias in normalized_candidates}
        return next(iter(matches)) if len(matches) == 1 else None

    def _canonical_name(self, raw_name: str) -> tuple[str, list[str]]:
        normalized = self._normalize_rule(raw_name)
        for token, canonical, aliases in self.canonical_rules:
            if token in normalized:
                return canonical, aliases
        return re.sub(r"[（(][^）)]{1,40}[）)]\s*$", "", raw_name).strip(), []

    def _enrich(self, competition: Competition, record: CompetitionSeedRecord) -> bool:
        changed = False
        values = {
            "organizer": record.organizer,
            "official_website": record.official_website,
            "typical_schedule": record.typical_schedule,
            "team_type": record.team_type,
            "min_team_size": record.min_team_size,
            "max_team_size": record.max_team_size,
        }
        for field_name, value in values.items():
            if value and not getattr(competition, field_name):
                setattr(competition, field_name, value)
                changed = True
        if record.category and competition.category in {None, "学科竞赛"}:
            competition.category = record.category
            changed = True
        if record.description and (not competition.description or competition.description.startswith("由已验证高校政策")):
            competition.description = record.description
            changed = True
        return changed

    def _heading_aliases(self, name: str) -> list[str]:
        aliases: list[str] = []
        for group in re.findall(r"[（(]([^）)]+)[）)]", name):
            aliases.extend(value.strip() for value in re.split(r"[/／·、]", group) if 2 <= len(value.strip()) <= 30)
        return aliases

    def _team_sizes(self, value: str | None) -> tuple[int | None, int | None]:
        if not value:
            return None, None
        range_match = re.search(r"(\d+)\s*[-—~至]\s*(\d+)\s*人", value)
        if range_match:
            return int(range_match.group(1)), int(range_match.group(2))
        upper_match = re.search(r"[≤不超过]{1,4}\s*(\d+)\s*人", value)
        if upper_match:
            return 1, int(upper_match.group(1))
        exact_match = re.search(r"(\d+)\s*人", value)
        if exact_match:
            size = int(exact_match.group(1))
            return size, size
        return None, None

    def _normalize_rule(self, value: str) -> str:
        return re.sub(r"[^a-z0-9\u4e00-\u9fff+]", "", value.lower())

    def _optional_int(self, value: Any) -> int | None:
        return int(value) if value not in (None, "") else None

    def _unique(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
