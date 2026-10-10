"""Production ingestion cannot mutate reviewed competition facts implicitly."""
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import bindparam, create_engine, delete, insert, select, text, update
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionEdition
from app.models.base import Base


@pytest.fixture()
def guarded_db():
    from app.database.review_guard import ReviewGuardedSession
    from app.database.session import SessionLocal

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        competition = Competition(name="Reviewed fixture", organizer="Original")
        seed.add(competition)
        seed.flush()
        seed.add(CompetitionEdition(competition_id=competition.id, year=2026))
        seed.commit()
    # The application factory is exercised with only its database bind replaced.
    with SessionLocal(bind=engine) as db:
        assert isinstance(db, ReviewGuardedSession)
        yield db
        db.rollback()
    engine.dispose()


@pytest.mark.parametrize("operation", ["create", "update", "delete", "verification"])
def test_unreviewed_orm_fact_writes_are_blocked(guarded_db, operation):
    from app.database.review_guard import UnreviewedFactWrite

    row = guarded_db.scalar(select(Competition))
    if operation == "create":
        guarded_db.add(Competition(name="Unreviewed"))
    elif operation == "delete":
        guarded_db.delete(row)
    elif operation == "verification":
        row.is_official_verified = True
    else:
        row.organizer = "Unreviewed"
    with pytest.raises(UnreviewedFactWrite, match="field review"):
        guarded_db.flush()


@pytest.mark.parametrize("statement", [
    update(Competition).values(organizer="Bulk"),
    insert(Competition).values(name="Bulk"),
    delete(CompetitionEdition),
    update(Competition.__table__).values(organizer="Core"),
    update(Competition.__table__.alias("contest_alias")).values(organizer="Aliased Core"),
    text("UPDATE competitions SET organizer='Raw'"),
    text('/* comment */ UPDATE "competition_editions" SET year=2027'),
])
def test_unreviewed_bulk_and_text_writes_are_blocked(guarded_db, statement):
    from app.database.review_guard import UnreviewedFactWrite

    with pytest.raises(UnreviewedFactWrite, match="field review"):
        guarded_db.execute(statement)


def test_legacy_bulk_mapping_api_is_blocked(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite

    with pytest.raises(UnreviewedFactWrite):
        guarded_db.bulk_update_mappings(Competition, [{"id": 1, "organizer": "Bulk"}])
    with pytest.raises(UnreviewedFactWrite):
        guarded_db.bulk_save_objects([Competition(name="Bulk")])


def test_direct_connection_from_guarded_session_cannot_bypass_review(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite

    connection = guarded_db.connection()
    with pytest.raises(UnreviewedFactWrite):
        connection.execute(update(Competition).values(organizer="Connection bypass"))
    with pytest.raises(UnreviewedFactWrite):
        connection.exec_driver_sql("UPDATE competitions SET organizer='Driver bypass'")


@pytest.mark.parametrize("parameters", [{"organizer": "unreviewed"}, [{"organizer": "unreviewed"}]])
def test_connection_execution_parameters_cannot_add_protected_set_column(guarded_db, parameters):
    from app.database.review_guard import UnreviewedFactWrite

    connection = guarded_db.connection()
    statement = update(Competition.__table__).where(Competition.id == 1).values(
        updated_at=datetime(2026, 9, 27, tzinfo=timezone.utc))
    with pytest.raises(UnreviewedFactWrite):
        connection.execute(statement, parameters)
    assert guarded_db.get(Competition, 1).organizer == "Original"


@pytest.mark.parametrize("use_parameters", [False, True])
def test_connection_freshness_update_with_where_parameters_remains_allowed(guarded_db, use_parameters):
    connection = guarded_db.connection()
    if use_parameters:
        statement = update(CompetitionEdition.__table__).where(CompetitionEdition.id == bindparam("target_id")).values(
            freshness_status=bindparam("next_freshness"))
        connection.execute(statement, [{"target_id": 1, "next_freshness": "stale"}])
    else:
        statement = update(CompetitionEdition.__table__).where(CompetitionEdition.id == 1).values(freshness_status="stale")
        connection.execute(statement)
    guarded_db.commit()
    assert guarded_db.get(CompetitionEdition, 1).freshness_status == "stale"


def test_connection_execution_parameters_cannot_reassign_primary_key(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite

    statement = update(Competition.__table__).where(Competition.id == 1).values(
        updated_at=datetime(2026, 9, 27, tzinfo=timezone.utc))
    with pytest.raises(UnreviewedFactWrite):
        guarded_db.connection().execute(statement, {"id": 99})


def test_orm_bulk_freshness_update_uses_primary_key_only_as_selector(guarded_db):
    guarded_db.execute(update(CompetitionEdition), [{"id": 1, "freshness_status": "stale"}])
    guarded_db.commit()
    assert guarded_db.get(CompetitionEdition, 1).freshness_status == "stale"


def test_review_context_failure_does_not_leave_write_permission(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite, reviewed_write

    with pytest.raises(ValueError):
        with reviewed_write(guarded_db):
            raise ValueError("review failed")
    with pytest.raises(UnreviewedFactWrite):
        guarded_db.execute(update(Competition).values(organizer="After failure"))


def test_delete_orphan_relationship_cannot_delete_official_edition(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite

    competition = guarded_db.scalar(select(Competition))
    competition.editions.clear()
    with pytest.raises(UnreviewedFactWrite):
        guarded_db.flush()


def test_relationship_assignment_cannot_change_edition_parent(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite, reviewed_write

    with reviewed_write(guarded_db):
        other = Competition(name="Another approved parent")
        guarded_db.add(other)
    edition = guarded_db.scalar(select(CompetitionEdition))
    edition.competition = other
    with pytest.raises(UnreviewedFactWrite):
        guarded_db.flush()


def test_derived_freshness_bookkeeping_remains_available(guarded_db):
    edition = guarded_db.scalar(select(CompetitionEdition))
    edition.freshness_status = "due_for_check"
    edition.next_check_at = datetime.now(timezone.utc)
    guarded_db.flush()
    guarded_db.execute(update(CompetitionEdition).values(freshness_status="stale"))
    guarded_db.commit()
    assert edition.freshness_status == "stale"


def test_reviewed_scope_flushes_approved_changes_and_does_not_leak(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite, reviewed_write

    row = guarded_db.scalar(select(Competition))
    with reviewed_write(guarded_db):
        row.organizer = "Reviewed"
        guarded_db.flush()
        guarded_db.execute(update(CompetitionEdition).values(edition_name="Reviewed edition"))
    guarded_db.commit()
    assert row.organizer == "Reviewed"
    row.organizer = "Unreviewed after context"
    with pytest.raises(UnreviewedFactWrite):
        guarded_db.flush()


def test_review_scope_cannot_launder_preexisting_dirty_facts(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite, reviewed_write

    row = guarded_db.scalar(select(Competition))
    row.organizer = "Unreviewed before context"
    with pytest.raises(UnreviewedFactWrite):
        with reviewed_write(guarded_db):
            guarded_db.flush()


def test_runtime_session_factory_enforces_review_guard():
    from app.database.review_guard import ReviewGuardedSession
    from app.database.session import SessionLocal

    assert issubclass(SessionLocal.class_, ReviewGuardedSession)


def test_runtime_factory_stages_collected_records_instead_of_official_rows(guarded_db):
    from app.database.session import SessionLocal
    from app.models import ReviewQueue
    from app.services.competition_seed_import_service import CompetitionSeedImportService, CompetitionSeedRecord

    # Exercise the application factory, overriding only its bind with this
    # isolated fixture engine. Never use the configured production engine.
    with SessionLocal(bind=guarded_db.get_bind()) as runtime:
        stats = CompetitionSeedImportService().import_records(runtime,
            [CompetitionSeedRecord(name="Runtime collected event", organizer="Unreviewed organizer")],
            source_repository="test/catalog", source_file="catalog.md")
        assert stats["created"] == 0
        assert stats["candidates_staged"] == 1
        assert runtime.scalar(select(Competition).where(Competition.name == "Runtime collected event")) is None
        queue = runtime.scalar(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate"))
        assert queue is not None and "UNVERIFIED" in queue.raw_value


def test_runtime_factory_rejects_unconverted_legacy_direct_writes(guarded_db):
    from app.database.review_guard import UnreviewedFactWrite
    from app.database.session import SessionLocal

    with SessionLocal(bind=guarded_db.get_bind()) as runtime:
        runtime.add(Competition(name="Legacy direct write"))
        with pytest.raises(UnreviewedFactWrite, match="field review"):
            runtime.flush()
        runtime.rollback()


def test_ingestion_stages_supported_fields_without_writing_official_data(db_session):
    from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService

    competition = db_session.scalar(select(Competition))
    original = competition.organizer
    helper = CompetitionFieldIngestionService()
    queue = helper.stage(
        db_session, entity_type="competition", competition_id=competition.id,
        title="Crawler organizer proposal", fields={"organizer": "New from crawler"},
        source={"source_type": "organizer_notice", "source_url": "https://example.org/notice"},
        producer="test-crawler",
    )
    db_session.flush()
    assert competition.organizer == original
    assert queue.id is not None
    assert queue.status == "pending"
    assert "New from crawler" in queue.raw_value
    assert "UNVERIFIED" in queue.raw_value
    repeated = helper.stage(
        db_session, entity_type="competition", competition_id=competition.id,
        title="Crawler organizer proposal", fields={"organizer": "New from crawler"},
        source={"source_type": "organizer_notice", "source_url": "https://example.org/notice"},
        producer="test-crawler",
    )
    assert repeated.id == queue.id


def test_ingestion_retains_invalid_or_claimed_verified_fields_as_raw_evidence(db_session):
    from app.services.competition_field_ingestion_service import CompetitionFieldIngestionService

    queue = CompetitionFieldIngestionService().stage(db_session,
        entity_type="competition", competition_id=1, title="Legacy structured source",
        fields={"organizer": "Proposed organizer", "official_website": "invalid-no-scheme.example",
            "history_timeline": [{"year": 2020, "title": "Claim", "verification_status": "verified_official"}]},
        producer="legacy-record")
    doc = json.loads(queue.raw_value)
    assert [item["field_name"] for item in doc["proposals"]] == ["organizer"]
    assert "invalid-no-scheme.example" in doc["description"]
    assert "verified_official" in doc["description"]
    assert doc["proposals"][0]["source"]["verification_state"] == "NO_SOURCE"


def test_new_official_record_remains_candidate_until_review(guarded_db):
    from app.models import ReviewQueue
    from app.services.fact_intelligence_service import FactIntelligenceService

    count_before = len(guarded_db.scalars(select(Competition)).all())
    result = FactIntelligenceService()._promote_official_record(
        guarded_db,
        {"competition_name": "New official record", "organizer": "Organizer",
         "source_url": "https://example.org/new", "reliability_tier": 1,
         "edition": {"year": 2027, "edition_name": "2027 new event"}},
        datetime.now(timezone.utc),
    )
    guarded_db.commit()
    assert result["competition_created"] is False
    assert len(guarded_db.scalars(select(Competition)).all()) == count_before
    assert guarded_db.scalar(select(ReviewQueue)) is not None


def test_trusted_policy_normalization_never_auto_creates_in_runtime(guarded_db):
    from app.services.competition_normalization_service import CompetitionNormalizationService

    normalized = CompetitionNormalizationService().normalize_or_create(
        guarded_db, "Policy discovered contest", trusted_policy=True, source_title="University policy",
    )
    guarded_db.commit()
    assert normalized.competition is None
    assert normalized.needs_manual_review is True
    assert guarded_db.scalar(select(Competition).where(Competition.name == "Policy discovered contest")) is None


def test_policy_pipeline_keeps_unknown_competition_as_candidate(guarded_db, tmp_path):
    from app.crawler.base import CrawlerRunResult
    from app.crawler.pipelines.university_policy_pipeline import UniversityPolicyPipeline
    from app.models import CandidateCompetition, PolicyDocument, ReviewQueue, University

    school = University(name="Crawler test university")
    guarded_db.add(school)
    guarded_db.flush()
    document = PolicyDocument(university_id=school.id, title="学科竞赛认定目录", policy_type="competition_catalog",
        source_url="https://example.edu.cn/policy", is_verified=True,
        content_text="全国人工智能创新大赛纳入竞赛奖励目录，获得一等奖予以加分。")
    # Set up an already-approved policy fixture; the runtime pipeline below
    # still must stage the unknown competition rather than create a fact.
    from app.database.review_guard import reviewed_write
    with reviewed_write(guarded_db):
        guarded_db.add(document)
        guarded_db.flush()
    before = len(guarded_db.scalars(select(Competition)).all())
    pipeline = UniversityPolicyPipeline(storage_root=tmp_path)
    pipeline._extract_and_persist_recognitions(
        guarded_db, university=school, document=document,
        result=CrawlerRunResult(target_name=school.name, target_url=document.source_url), dry_run=False,
    )
    guarded_db.commit()
    assert len(guarded_db.scalars(select(Competition)).all()) == before
    assert guarded_db.scalar(select(CandidateCompetition)) is not None
    candidate = guarded_db.scalar(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate"))
    assert candidate is not None
    assert document.source_url in candidate.raw_value


def test_seed_importer_stages_in_runtime_and_does_not_promote_flags(guarded_db):
    from app.models import ReviewQueue
    from app.services.competition_seed_import_service import CompetitionSeedImportService, CompetitionSeedRecord

    result = CompetitionSeedImportService().import_records(guarded_db,
        [CompetitionSeedRecord(name="External catalog contest", organizer="Catalog organizer")],
        source_repository="owner/repo", source_file="catalog.md", commit_sha="123456")
    assert result["created"] == 0
    assert result["candidates_staged"] == 1
    assert guarded_db.scalar(select(Competition).where(Competition.name == "External catalog contest")) is None
    queue = guarded_db.scalar(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate"))
    assert "UNVERIFIED" in queue.raw_value
    assert "/blob/123456/catalog.md" in queue.raw_value


def test_edition_seed_stages_exact_year_and_keeps_formal_values(guarded_db, tmp_path):
    from app.models import ReviewQueue
    from app.services.competition_edition_seed_service import CompetitionEditionSeedService

    path = tmp_path / "editions.json"
    path.write_text(json.dumps({"editions": [{"competition_name": "Reviewed fixture", "year": 2027,
        "edition_name": "New edition", "is_verified": True, "source_url": "https://example.org/2027"}]}), encoding="utf-8")
    result = CompetitionEditionSeedService().import_json(guarded_db, path)
    assert result["created"] == result["updated"] == 0
    assert guarded_db.scalar(select(CompetitionEdition).where(CompetitionEdition.year == 2027)) is None
    queues = list(guarded_db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate")))
    edition_doc = next(json.loads(row.raw_value) for row in queues if json.loads(row.raw_value)["entity_type"] == "edition")
    assert edition_doc["year"] == 2027
    assert all(p["field_name"] != "is_verified" for p in edition_doc["proposals"])
    assert all(p["source"]["verification_state"] == "UNVERIFIED" for p in edition_doc["proposals"])


@pytest.mark.parametrize("target,field,value", [
    ({"entity_type": "competition", "competition_id": 1}, "organizer", "Reviewed organization"),
    ({"entity_type": "edition", "competition_id": 1, "edition_id": 1, "year": 2026}, "edition_name", "Reviewed edition"),
    ({"entity_type": "competition"}, "name", "New human-approved competition"),
])
def test_human_approval_service_can_apply_through_guard(guarded_db, target, field, value):
    from app.models import CompetitionFactRevision, CompetitionFactSource, User
    from app.services.field_review_service import FieldReviewService

    admin = User(email="guard-admin@example.test", username="guard-admin", hashed_password="unused", is_admin=True)
    guarded_db.add(admin)
    guarded_db.commit()
    svc = FieldReviewService()
    row = svc.create_candidate(guarded_db, {**target, "title": "Reviewed guarded write", "fields": [
        {"field_name": field, "candidate_value": value, "source": {
            "source_type": "organizer_notice", "source_url": "https://example.org/verified-notice"}},
    ]})
    detail = svc.detail(guarded_db, row.id)
    proposal_id = detail["fields"][0]["proposals"][0]["id"]
    verified = svc.verify_source(guarded_db, row.id, proposal_id,
        {"preview_token": detail["preview_token"], "note": "Source checked by administrator"}, admin=admin)
    result = svc.review(guarded_db, row.id, {
        "preview_token": verified["preview_token"], "note": "Explicit field approval",
        "decisions": [{"field_name": field, "action": "approve", "proposal_id": proposal_id}],
    }, admin=admin)
    guarded_db.commit()
    assert result["status"] == "approved"
    assert guarded_db.scalar(select(CompetitionFactSource).where(CompetitionFactSource.field_name == field)) is not None
    assert guarded_db.scalar(select(CompetitionFactRevision).where(CompetitionFactRevision.field_name == field)) is not None
