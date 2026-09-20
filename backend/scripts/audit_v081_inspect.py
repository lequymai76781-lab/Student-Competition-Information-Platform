"""V0.8.2 helper: dump V0.8.1 leads/relations for precision inspection."""

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    seed = json.loads((root / "data" / "seeds" / "v081_211_radar_fix_discovery.json").read_text(encoding="utf-8"))
    leads = seed["leads"]
    rels = seed["edition_relations"]
    print("== leads:", len(leads), "rels:", len(rels))
    print("== stored classification:", dict(Counter(l.get("classification") for l in leads)))
    print()
    print("== ALL 56 RELATIONS ==")
    for i, r in enumerate(rels, 1):
        print(
            f"{i:02d} [{r.get('notice_type')}] y={r.get('year')} "
            f"dl={r.get('internal_registration_deadline') or '-'}"
        )
        print("    ", (r.get("notice_title") or "")[:120])
        print("     ", r.get("university"), "|", r.get("internal_notice_url", "")[:130])
    print()
    print("== leads per school (top 12) ==")
    for name, count in Counter(l.get("university") for l in leads).most_common(12):
        print(name, count)


if __name__ == "__main__":
    main()
