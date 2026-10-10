"""Bounded source-manifest ingestion. All writes go through field candidates.

School notices and scoped/unsupported facts stay in raw evidence. This adapter
does not manufacture school recognition, approve sources, or commit.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

from sqlalchemy import select

from app.database.review_guard import is_review_guarded
from app.models import Competition, CompetitionAlias, CompetitionEdition, University
from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService


NOTICE_TYPES = {'registration_notice', 'organization_notice', 'competition_notice',
                'policy_recognition', 'award_policy', 'other'}


def _name(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', str(value or '')).casefold())


def _site(value):
    parsed = urlsplit(str(value or ''))
    return ((parsed.hostname or '').removeprefix('www.'), parsed.path.rstrip('/'))


def _published(value):
    if value and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return value + 'T00:00:00+08:00'
    return value


class RealDataPilotService:
    def identity(self, db, sample):
        """Exact names/known aliases resolve; website/organizer are only hints."""
        competitions = list(db.scalars(select(Competition)))
        names = {row.id: {_name(row.name), _name(row.short_name), _name(row.english_name),
                         *(_name(v) for v in (row.former_names or []))} - {''} for row in competitions}
        for alias in db.scalars(select(CompetitionAlias)):
            if alias.competition_id in names and alias.is_verified:
                names[alias.competition_id].add(_name(alias.alias))
        for edition in db.scalars(select(CompetitionEdition)):
            if edition.competition_id in names and edition.edition_name:
                names[edition.competition_id].add(_name(edition.edition_name))
        query = _name(sample['name'])
        exact = {identity for identity, values in names.items() if query in values}
        websites = { _site(s.get('competition_fields', {}).get('official_website'))
                    for s in sample['sources'] } - {('', '')}
        organizers = {_name(s.get('competition_fields', {}).get('organizer'))
                      for s in sample['sources']} - {''}
        website_ids = {r.id for r in competitions if r.official_website and _site(r.official_website) in websites}
        organizer_ids = {r.id for r in competitions if r.organizer and _name(r.organizer) in organizers}
        first_years = {s.get('competition_fields', {}).get('first_held_year') for s in sample['sources']} - {None}
        first_year_ids = {r.id for r in competitions if r.first_held_year in first_years}
        requested = sample.get('competition_id')
        resolved = next(iter(exact)) if len(exact) == 1 else None
        ambiguous = resolved is None or (requested is not None and requested != resolved)
        evidence = {'normalized_name': query, 'name_and_alias_ids': sorted(exact),
                    'website_ids': sorted(website_ids), 'organizer_ids': sorted(organizer_ids),
                    **({'first_held_year_ids': sorted(first_year_ids)} if first_years else {}),
                    'requested_id': requested, 'status': 'DUPLICATE_SUSPECTED' if ambiguous else 'EXISTING_MATCH'}
        return (None if ambiguous else db.get(Competition, resolved)), evidence

    def stage_sample(self, db, sample):
        if not is_review_guarded(db):
            raise ValueError('Pilot requires the runtime guarded session')
        # Validate the entire sample before any candidate is staged.
        for source in sample['sources']:
            notice = source.get('university_notice')
            if notice:
                if notice.get('notice_type') not in NOTICE_TYPES:
                    raise ValueError('Unknown university notice type')
                if notice.get('is_formal_recognition') and (
                    notice['notice_type'] not in {'policy_recognition', 'award_policy'}
                    or source['source_type'] != 'university_policy'
                    or not notice.get('recognition_evidence')
                ):
                    raise ValueError('Formal recognition requires explicit policy evidence')
            if source.get('edition_fields') and type(source.get('year')) is not int:
                raise ValueError('Edition fields require an explicit year')
            if 'university_registration_deadline' in source.get('edition_fields', {}):
                raise ValueError('School deadlines belong to university_notice evidence')
        competition, dedup = self.identity(db, sample)
        adapter = CompetitionFieldIngestionService()
        rows = []
        for source in sample['sources']:
            notice = source.get('university_notice')
            school = db.scalar(select(University).where(University.name == notice.get('university_name'))) if notice else None
            provenance = {'source_type': source['source_type'], 'source_title': source['title'],
                          'source_url': source['url'], 'publisher': source['publisher'],
                          'published_at': _published(source.get('published_at'))}
            raw = {'sample_name': sample['name'], 'aliases': sample.get('aliases', []),
                   'identity_check': dedup, 'source': source}
            label = f"真实资料 · {sample['name']} · {source['key']}"
            shared = {'source': provenance, 'producer': 'real_data_pilot', 'raw': raw,
                      'competition_id': competition.id if competition else None,
                      'university_id': school.id if school else None}
            if competition is None or source.get('access_status') != 'readable':
                rows.append(adapter.stage(db, entity_type='competition', fields={},
                    title=f"{'DUPLICATE_SUSPECTED' if competition is None else '来源待复核'} · {label}", **shared))
                continue
            fields = {k: v for k, v in source.get('competition_fields', {}).items() if v is not None}
            if fields or not source.get('edition_fields'):
                rows.append(adapter.stage(db, entity_type='competition', fields=fields, title=label, **shared))
            edition_fields = {k: v for k, v in source.get('edition_fields', {}).items() if v is not None}
            if edition_fields:
                year = source['year']
                existing = list(db.scalars(select(CompetitionEdition).where(
                    CompetitionEdition.competition_id == competition.id, CompetitionEdition.year == year)))
                if len(existing) > 1:
                    raw['edition_duplicate_ids'] = [row.id for row in existing]
                    rows.append(adapter.stage(db, entity_type='competition', fields={},
                        title=f'DUPLICATE_SUSPECTED · 届次 {year} · {label}', **shared))
                    continue
                rows.append(adapter.stage(db, entity_type='edition', fields=edition_fields, title=f'{label} / {year}',
                    year=year, edition_id=existing[0].id if existing else None, **shared))
        return rows
