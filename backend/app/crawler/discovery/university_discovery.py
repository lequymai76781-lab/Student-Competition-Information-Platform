import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class UniversitySeed:
    name: str
    english_name: str | None
    short_name: str | None
    province: str
    city: str
    official_website: str
    official_domain: str
    aliases: list[str]
    is_985: bool
    is_211: bool
    is_double_first_class: bool = False


class UniversitySeedLoader:
    def __init__(self, seed_path: Path) -> None:
        self.seed_path = seed_path

    def load_985(self) -> list[UniversitySeed]:
        rows = json.loads(self.seed_path.read_text(encoding="utf-8"))
        return [
            UniversitySeed(
                name=row["name"],
                english_name=row.get("english_name"),
                short_name=row.get("short_name"),
                province=row["province"],
                city=row["city"],
                official_website=row["official_website"],
                official_domain=row["official_domain"],
                aliases=row.get("aliases", []),
                is_985=bool(row.get("is_985", True)),
                is_211=bool(row.get("is_211", True)),
                is_double_first_class=bool(row.get("is_double_first_class", row.get("is_985", False))),
            )
            for row in rows
        ]

    def first_batch(self) -> list[UniversitySeed]:
        names = {"武汉大学", "华中科技大学", "清华大学", "北京大学", "浙江大学"}
        seeds = self.load_985()
        return [seed for seed in seeds if seed.name in names]
