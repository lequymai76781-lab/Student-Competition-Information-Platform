"""Replay a bounded source manifest into an existing isolated candidate DB.

This CLI reuses crawler_jobs checkpoints. It stages researched evidence; it
does not claim a new live fetch or perform any source verification/approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.codex-qa/mid-scale'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--job-id', type=int)
    parser.add_argument('--manifest', action='append', default=[])
    parser.add_argument('--school-manifest')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--max-items', type=int)
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--item-key', action='append')
    parser.add_argument('--probe-links', action='store_true', help='Bounded GET per source; records availability only')
    args = parser.parse_args()
    target = Path(args.database).resolve()
    if target.parent != OUT.resolve() or target.suffix != '.sqlite' or not target.is_file():
        raise SystemExit('An existing .codex-qa/mid-scale/*.sqlite database is required')
    os.environ.update(ENVIRONMENT='test', DATABASE_URL=f'sqlite:///{target.as_posix()}', LOG_DIR=str(OUT/'logs'))
    sys.path.insert(0, str(ROOT/'backend'))
    from sqlalchemy import select
    from app.database.safety import assert_test_sqlite_target_is_safe
    from app.database.session import SessionLocal
    from app.models import Competition, CompetitionEdition, University, UniversityCompetitionEditionRelation
    from app.services.mid_scale_ingestion_service import MidScaleIngestionService as Batch, probe_source
    assert_test_sqlite_target_is_safe(target)

    def digest(db):
        payload = {m.__tablename__: [list(r) for r in db.execute(select(m.__table__).order_by(m.id))]
                   for m in (Competition, CompetitionEdition, University, UniversityCompetitionEditionRelation)}
        return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()

    with SessionLocal() as db:
        before = digest(db)
        job_id = args.job_id
        if job_id is None:
            if args.status:
                raise SystemExit('--status requires --job-id')
            items = []
            for filename in args.manifest:
                for sample in json.loads(Path(filename).read_text(encoding='utf-8-sig')):
                    items.extend({'kind': 'competition', 'competition_id': sample.get('competition_id'),
                                  'competition_name': sample['name'], 'source': source} for source in sample['sources'])
            if args.school_manifest:
                items.extend({'kind': 'school_mapping', **item}
                    for item in json.loads(Path(args.school_manifest).read_text(encoding='utf-8-sig')))
            job_id = Batch.create_job(db, items, source=';'.join(args.manifest+[args.school_manifest or ''])).id
        summary = Batch.summary(db, job_id) if args.status else Batch.run(db, job_id,
            max_items=args.max_items, retry_failed=args.retry_failed, item_keys=args.item_key, recover=args.recover,
            probe=probe_source if args.probe_links else None)
        after = digest(db)
        if before != after:
            raise RuntimeError('Official baseline changed during candidate staging')
    summary.update(official_digest_before=before, official_digest_after=after)
    destination = OUT/f'job-{job_id}.json'
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k != 'items'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
