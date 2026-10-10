import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.golden_set import AnnotationIn, AuditIn
from app.services.golden_set_service import GoldenSetService, POLICY_CHECKS, RELATION_CHECKS


@pytest.fixture()
def store(tmp_path):
    manifest = {"dataset_id": "unit-real-snapshot", "fixture_only": False, "items": [
        {"source_id": str(n), "title": f"source {n}", "predicted_type": "registration_notice", "predicted_confidence": .91}
        for n in range(1, 4)], "audit_sets": {
            "policies": [{"audit_id": "policy:1", "title": "policy"}],
            "relations": [{"audit_id": "relation:1", "title": "relation"}]}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return GoldenSetService(tmp_path)


def label(revision=0, **kwargs):
    return AnnotationIn(status="annotated", human_primary_type="other", expected_revision=revision, **kwargs)


def test_empty_progress_snapshot_and_resume(store):
    assert store.dataset()["progress"] == dict(annotated=0, draft=0, skipped=0, untouched=3, total=3)
    result = store.save_annotation("1", label(), "admin:7")
    ann = result["annotation"]
    assert ann["annotated_by"] == "admin:7" and ann["annotated_at"]
    assert ann["title"] == "source 1" and ann["predicted_type"] == "registration_notice"
    assert ann["predicted_confidence"] == .91 and ann["label_provenance"] == "human"
    assert ann["revision"] == 1 and not ann["prediction_exposed"]
    assert GoldenSetService(store.directory).dataset()["items"][0]["annotation"] == ann
    assert store.manifest["items"][0].get("human_primary_type") is None


def test_drafts_skips_and_revision_conflict(store):
    store.save_annotation("1", AnnotationIn(status="draft", expected_revision=0), "admin")
    store.save_annotation("2", AnnotationIn(status="skipped", expected_revision=0), "admin")
    assert store.dataset()["progress"] == dict(annotated=0, draft=1, skipped=1, untouched=1, total=3)
    store.save_annotation("1", label(1), "admin")
    with pytest.raises(HTTPException) as error:
        store.save_annotation("1", label(1), "another-admin")
    assert error.value.status_code == 409
    assert store.export()["annotations"][0]["annotated_by"] == "admin"
    with sqlite3.connect(store.directory / "annotations.sqlite") as db:
        assert db.execute("select count(*) from events").fetchone()[0] == 3


def test_validation_no_write_or_client_identity(store):
    for body in [dict(status="annotated", human_primary_type="made-up", expected_revision=0),
                 dict(status="annotated", expected_revision=0),
                 dict(status="draft", expected_revision=-1),
                 dict(status="draft", expected_revision=0, annotated_by="forged"),
                 dict(status="draft", expected_revision=0, human_primary_type="other", human_secondary_types=["other"]),
                 dict(status="draft", expected_revision=0, human_secondary_types=["other", "other"])]:
        with pytest.raises(ValidationError):
            AnnotationIn(**body)
    with pytest.raises(HTTPException) as error:
        store.save_annotation("../../outside", label(), "admin")
    assert error.value.status_code == 404
    assert store.dataset()["progress"]["untouched"] == 3


def test_exposure_is_durable_but_not_retroactive(store):
    blind = store.save_annotation("1", label(), "admin")["annotation"]
    store.expose("1", "admin")
    assert store.dataset()["items"][0]["prediction_exposed"]
    assert not store.dataset()["items"][0]["annotation"]["prediction_exposed"]
    revised = store.save_annotation("1", label(1, prediction_exposed=False), "admin")["annotation"]
    assert revised["prediction_exposed"] and not blind["prediction_exposed"]
    store.expose("2", "admin")
    assert store.dataset()["progress"]["untouched"] == 2


def test_manifest_hash_mismatch_refuses_dataset_swap(store):
    store.save_annotation("1", label(), "admin")
    path = store.directory / "manifest.json"
    altered = json.loads(path.read_text())
    altered["items"][0]["title"] = "changed"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(HTTPException) as error:
        GoldenSetService(store.directory).dataset()
    assert error.value.status_code == 409


@pytest.mark.parametrize("kind,checks", [("policies", POLICY_CHECKS), ("relations", RELATION_CHECKS)])
def test_audits_require_explicit_complete_answers_and_history(store, kind, checks):
    audit_id = store.manifest["audit_sets"][kind][0]["audit_id"]
    with pytest.raises(HTTPException) as error:
        store.save_audit(kind, audit_id, AuditIn(status="annotated", expected_revision=0, answers={}), "admin")
    assert error.value.status_code == 422
    answers = {key: "no" for key in checks}
    result = store.save_audit(kind, audit_id, AuditIn(status="annotated", expected_revision=0, answers=answers), "admin")
    assert result["annotation"]["answers"] == answers
    assert result["progress"]["annotated"] == 1
    assert store.dataset()["progress"]["annotated"] == 0


def test_fixture_label_provenance_cannot_count_as_real_human(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"dataset_id": "fixture", "fixture_only": True,
        "items": [{"source_id": "fixture-1", "title": "fixture", "predicted_type": "other", "predicted_confidence": .95}], "audit_sets": {}}))
    service = GoldenSetService(tmp_path)
    annotation = service.save_annotation("fixture-1", label(), "admin")["annotation"]
    assert annotation["label_provenance"] == "test_fixture"
    assert service.metrics()["human_n"] == 0


def test_api_requires_persisted_admin_and_rejects_extra_fields(client, db_session, store):
    from app.main import app
    from app.services.golden_set_service import get_golden_set_service
    from app.core.config import get_settings
    from app.core.security import create_token
    from app.models import User
    app.dependency_overrides[get_golden_set_service] = lambda: store
    try:
        assert client.get("/api/admin/golden-set").status_code == 403
        user = User(username="golden-test-admin", email="golden@unit.test", hashed_password="unused", is_admin=True, is_active=True)
        db_session.add(user); db_session.commit()
        token = create_token(user.id, get_settings().app_secret)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/admin/golden-set", headers=headers).status_code == 200
        response = client.put("/api/admin/golden-set/annotations/1", headers=headers,
            json={"status": "annotated", "human_primary_type": "other", "expected_revision": 0, "annotated_by": "forged"})
        assert response.status_code == 422
        assert store.dataset()["progress"]["annotated"] == 0
        user.is_active = False; db_session.commit()
        assert client.put("/api/admin/golden-set/annotations/1", headers=headers,
            json={"status": "annotated", "human_primary_type": "other", "expected_revision": 0}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_golden_set_service, None)


def test_config_rejects_production_or_unconfigured_path(monkeypatch):
    from app.services.golden_set_service import get_golden_set_service
    monkeypatch.delenv("GOLDEN_SET_DIR", raising=False)
    with pytest.raises(HTTPException) as error:
        get_golden_set_service()
    assert error.value.status_code == 404
    monkeypatch.setenv("GOLDEN_SET_DIR", str(__import__("pathlib").Path(__file__).resolve().parents[2] / "data"))
    with pytest.raises(HTTPException) as error:
        get_golden_set_service()
    assert error.value.status_code == 503


def test_concurrent_saves_only_one_revision_wins(store):
    from concurrent.futures import ThreadPoolExecutor
    def save(actor):
        try:
            return store.save_annotation("1", label(), actor)["annotation"]["revision"]
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ["one", "two"])) == [1, 409]
    assert store.dataset()["progress"]["annotated"] == 1
