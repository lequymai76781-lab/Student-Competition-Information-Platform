"""Import the reviewed source manifest into an existing QA-only candidate DB.

Usage: python scripts/import_real_data_pilot.py --database ../.codex-qa/real-data-pilot/candidates.sqlite
This command never creates a schema, accesses production, or approves facts.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--manifest-dir', default=str(ROOT / 'docs/real-data-pilot'))
    args = parser.parse_args()
    target = Path(args.database).resolve()
    allowed = (ROOT / '.codex-qa/real-data-pilot').resolve()
    if target.parent != allowed or target.suffix != '.sqlite' or not target.is_file():
        raise SystemExit('An existing isolated pilot SQLite database is required')
    os.environ.update(ENVIRONMENT='test', DATABASE_URL=f'sqlite:///{target.as_posix()}',
                      LOG_DIR=str(allowed / 'logs'))
    sys.path.insert(0, str(ROOT / 'backend'))
    from sqlalchemy import select
    from app.database.safety import assert_test_sqlite_target_is_safe
    from app.database.session import SessionLocal
    from app.models import Competition, CompetitionEdition
    from app.services.real_data_pilot_service import RealDataPilotService
    from app.services.field_review_service import FieldReviewService
    assert_test_sqlite_target_is_safe(target)
    samples = []
    for part in 'abc':
        samples.extend(json.loads((Path(args.manifest_dir) / f'sources-{part}.json').read_text(encoding='utf-8-sig')))
    if not 20 <= len(samples) <= 30 or len({s['competition_id'] for s in samples}) != len(samples):
        raise SystemExit('Pilot must contain 20–30 distinct selected existing competitions')

    def facts(db):
        values = {m.__tablename__: [list(r) for r in db.execute(select(m.__table__).order_by(m.id))]
                  for m in (Competition, CompetitionEdition)}
        return hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()

    with SessionLocal() as db:
        before = facts(db)
        rows = []
        for sample in samples:
            rows.extend(RealDataPilotService().stage_sample(db, sample))
        db.flush()
        after = facts(db)
        if before != after:
            raise RuntimeError('Candidate import changed official facts; rolling back')
        details = [FieldReviewService.detail(db, r) for r in rows]
        db.commit()
    summary = {'competitions': len(samples), 'candidates': len(details),
               'field_proposals': sum(len(f['proposals']) for d in details for f in d['fields']),
               'candidate_flags': dict(Counter(flag for d in details for flag in d['flags'])),
               'status': dict(Counter(d['status'] for d in details)),
               'official_facts_before': before, 'official_facts_after': after,
               'database': str(target), 'details': details}
    (allowed / 'import-results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'details'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
