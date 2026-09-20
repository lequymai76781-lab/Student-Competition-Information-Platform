"""Read-only dump of competition/edition sources + org links for v12 planning."""

from __future__ import annotations

import sys

BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionOrganization,
    CompetitionSource,
    Organization,
)


def main() -> None:
    ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
    with SessionLocal() as db:
        query = select(Competition).where(Competition.is_demo.is_(False))
        if ids:
            query = query.where(Competition.id.in_(ids))
        comps = list(db.execute(query.order_by(Competition.id)).scalars())
        for comp in comps:
            print(f"\n=== {comp.id} :: {comp.name} [{comp.verification_status}] ===")
            print(
                "   permanent: website=%r organizer=%r target=%r first_year=%r desc_source=%r"
                % (
                    comp.official_website,
                    comp.organizer,
                    comp.target_students,
                    comp.first_held_year,
                    comp.description_source_url,
                )
            )
            links = list(
                db.execute(
                    select(CompetitionOrganization).where(
                        CompetitionOrganization.competition_id == comp.id
                    )
                ).scalars()
            )
            for link in links:
                print(
                    "   org[%s] %s (%s) display=%r verified=%s src=%r"
                    % (
                        link.role,
                        link.organization.name if link.organization else link.organization_id,
                        link.organization.org_type if link.organization else "",
                        link.display_name,
                        link.is_verified,
                        link.source_url,
                    )
                )
            sources = list(
                db.execute(
                    select(CompetitionSource).where(
                        CompetitionSource.competition_id == comp.id
                    )
                ).scalars()
            )
            for s in sorted(sources, key=lambda x: (x.authority_level or "Z", x.source_url)):
                ed = None
                if s.competition_edition_id:
                    ed = db.get(CompetitionEdition, s.competition_edition_id)
                print(
                    "   src id=%d L=%s type=%s ed=%s official=%s verified=%s"
                    % (s.id, s.authority_level, s.source_type, ed.year if ed else "-", s.is_official, s.is_verified)
                )
                print(f"       {s.source_url}")
                print(f"       title={s.raw_title!r}")
            editions = list(
                db.execute(
                    select(CompetitionEdition)
                    .where(CompetitionEdition.competition_id == comp.id)
                    .order_by(CompetitionEdition.year.desc())
                ).scalars()
            )
            for e in editions:
                print(
                    "   edition id=%d y=%d status=%s ver=%s notice=%r reg=%r official_url=%r source_url=%r"
                    % (
                        e.id,
                        e.year,
                        e.edition_status,
                        e.verification_status,
                        e.official_notice_url,
                        e.official_registration_url,
                        e.official_url,
                        e.source_url,
                    )
                )


if __name__ == "__main__":
    main()
