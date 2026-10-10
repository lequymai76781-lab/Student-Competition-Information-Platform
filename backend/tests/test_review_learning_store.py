"""Behavioral tests using only disposable sidecar databases."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


def store_class():
    module_name = "app.services.review_learning_store"
    assert importlib.util.find_spec(module_name) is not None, "append-only learning store must exist"
    return importlib.import_module(module_name).ReviewLearningStore


def provenance(**changes):
    return {
        "origin": "real_candidate", "actor_mode": "human", "dataset_id": "isolated-real-20261007",
        "candidate_sha256": "a" * 64, "source": "review_audit", "max_audit_id": 12,
        **changes,
    }


def shadow():
    return {
        "shadow_primary_type": "competition_notice", "shadow_secondary_type": "registration_notice",
        "shadow_policy_prediction": False, "shadow_risk_level": "low",
        "shadow_suggested_action": "approve", "shadow_field_decisions": {"title": "approve"},
        "shadow_confidence": 0.8, "shadow_reason": "source evidence",
        "shadow_model_version": "shadow-v1-test", "shadow_created_at": "2026-10-07T00:00:00+00:00",
    }


def start(store, candidate_id=101, admin_id=7, **changes):
    return store.start_session(
        admin_id=admin_id, candidate_id=candidate_id,
        input_features=changes.pop("input_features", {"title": "2026 报名通知", "source_url": f"https://example.edu/{candidate_id}"}),
        shadow_prediction=changes.pop("shadow_prediction", shadow()),
        provenance=changes.pop("provenance", provenance()), **changes,
    )


def complete(store, session, *, decision_key=None, human=None):
    return store.complete(
        session["session_id"], session["admin_id"],
        human_ground_truth=human or {"human_primary_type": "competition_notice", "human_action": "approve"},
        review_context={"audit_id": decision_key or f"audit-{session['session_id']}", "submitted_at": "2026-10-07T00:01:00+00:00"},
        decision_key=decision_key or f"audit-{session['session_id']}",
    )


@pytest.fixture
def store(tmp_path):
    return store_class()(tmp_path / "learning.sqlite", namespace="isolated")


def test_session_retries_preserve_first_prediction_and_persist(tmp_path):
    first_store = store_class()(tmp_path / "learning.sqlite", namespace="isolated")
    first = start(first_store)
    retry = start(first_store, shadow_prediction={**shadow(), "shadow_reason": "later result"})
    assert retry["session_id"] == first["session_id"]
    assert retry["shadow_prediction"]["shadow_reason"] == "source evidence"
    reopened = store_class()(tmp_path / "learning.sqlite", namespace="isolated")
    assert reopened.get_session(first["session_id"], 7) == first
    assert first["provenance"]["max_audit_id"] == 12
    assert first["state"] == "observing"
    assert first_store.examples() == []


def test_concurrent_session_start_reuses_one_active_session(store):
    with ThreadPoolExecutor(max_workers=6) as pool:
        sessions = list(pool.map(lambda _: start(store), range(12)))
    assert len({session["session_id"] for session in sessions}) == 1


def test_complete_session_reopens_for_a_new_independent_review(store):
    first = start(store)
    complete(store, first)
    second = start(store)
    assert second["session_id"] != first["session_id"]
    assert start(store)["session_id"] == second["session_id"]
    assert store.get_session(first["session_id"], 7)["state"] == "completed"


def test_session_snapshot_and_trusted_audit_baseline_distinguish_identity(store):
    original = start(store)
    changed_input = start(store, input_features={"title": "changed"})
    changed_audit = start(store, provenance=provenance(max_audit_id=14))
    assert len({s["session_id"] for s in (original, changed_input, changed_audit)}) == 3


def test_owner_and_namespace_are_enforced_for_session_reads_and_events(store, tmp_path):
    session = start(store)
    with pytest.raises(PermissionError):
        store.get_session(session["session_id"], 8)
    with pytest.raises(PermissionError):
        store.event(session["session_id"], 8, "source_open")
    other = store_class()(tmp_path / "learning.sqlite", namespace="other")
    with pytest.raises(KeyError):
        other.get_session(session["session_id"], 7)
    assert other.examples() == []


def test_events_use_server_time_and_only_allowed_actions(store):
    session = start(store)
    event = store.event(session["session_id"], 7, "source_open", {"at": "forged", "url": "https://example.edu/"})
    assert event["at"] != "forged"
    assert event["at"] == event["timestamp"]
    assert event["session_id"] == session["session_id"]
    assert store.get_session(session["session_id"], 7)["events"] == [event]
    with pytest.raises(ValueError):
        store.event(session["session_id"], 7, "approve")
    assert store.examples() == []


@pytest.mark.parametrize("changes", [
    {"origin": "synthetic"}, {"actor_mode": "automation"}, {"source": "browser"},
    {"dataset_id": ""}, {"candidate_sha256": ""}, {"candidate_sha256": "wrong"},
])
def test_untrusted_or_automation_provenance_cannot_make_real_samples(store, changes):
    session = start(store, provenance=provenance(**changes))
    with pytest.raises((PermissionError, ValueError)):
        complete(store, session)
    assert store.examples(active_only=False) == []


def test_completion_preserves_missing_dimensions_and_committed_context(store):
    session = start(store)
    example = complete(store, session, decision_key="audit-20")
    assert example["human_ground_truth"]["human_primary_type"] == "competition_notice"
    for key in ("human_secondary_type", "human_policy", "human_risk_level", "human_field_decisions", "human_relation_decision", "human_note"):
        assert example["human_ground_truth"][key] is None
    assert example["comparison"]["secondary_match"] is None
    assert example["comparison"]["primary_match"] is True
    assert example["review_context"]["audit_id"] == "audit-20"
    assert example["learning_status"] == "active"
    assert len(store.examples()) == 1


def test_completion_requires_explicit_human_primary_and_review_evidence(store):
    session = start(store)
    with pytest.raises(ValueError):
        complete(store, session, human={"human_action": "approve"})
    with pytest.raises(ValueError):
        store.complete(session["session_id"], 7, human_ground_truth={"human_primary_type": "competition_notice"}, review_context={}, decision_key="")
    assert store.examples() == []


def test_concurrent_completion_retry_adds_one_example(store):
    session = start(store)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: complete(store, session, decision_key="audit-unique"), range(12)))
    assert len({example["example_id"] for example in results}) == 1
    assert len(store.examples()) == 1


def test_decision_cannot_be_reused_with_different_labels_or_session(store):
    session = start(store)
    complete(store, session, decision_key="audit-unique")
    with pytest.raises(ValueError):
        complete(store, session, decision_key="audit-unique", human={"human_primary_type": "policy", "human_action": "approve"})
    with pytest.raises(ValueError):
        complete(store, start(store, candidate_id=102), decision_key="audit-unique")
    with pytest.raises(ValueError):
        complete(store, session, decision_key="audit-different")
    assert len(store.examples()) == 1


def test_correction_appends_lineage_and_retry_does_not_duplicate(store):
    original = complete(store, start(store))
    replacement = {"human_primary_type": "policy", "human_policy": True, "human_action": "reject"}
    corrected = store.correct(original["example_id"], 7, human_ground_truth=replacement, reason="Checked source again")
    retry = store.correct(original["example_id"], 7, human_ground_truth=replacement, reason="Checked source again")
    assert retry["example_id"] == corrected["example_id"]
    assert corrected["supersedes_example_id"] == original["example_id"]
    assert corrected["learning_status"] == "corrected"
    assert corrected["comparison"]["correction"] is True
    assert store.examples() == [corrected]
    history = store.examples(active_only=False)
    assert len(history) == 2
    assert history[0]["learning_status"] == "superseded"
    assert history[0]["human_ground_truth"]["human_primary_type"] == "competition_notice"
    with pytest.raises(ValueError):
        store.correct(original["example_id"], 7, human_ground_truth=replacement, reason="Conflicting retry")


def test_concurrent_correction_appends_one_successor(store):
    original = complete(store, start(store))
    with ThreadPoolExecutor(max_workers=6) as pool:
        corrected = list(pool.map(lambda _: store.correct(original["example_id"], 7, human_ground_truth={"human_primary_type": "policy"}, reason="Source checked"), range(10)))
    assert len({row["example_id"] for row in corrected}) == 1
    assert len(store.examples()) == 1


def test_every_learning_table_rejects_update_and_delete(store):
    session = start(store)
    store.event(session["session_id"], 7, "source_open")
    complete(store, session)
    for candidate_id in range(1, 100):
        complete(store, start(store, candidate_id=candidate_id))
    store.create_batch(100)
    with sqlite3.connect(store.path) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        assert tables
        for table in tables:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f'UPDATE "{table}" SET rowid = rowid')
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f'DELETE FROM "{table}"')
            existing = connection.execute(f'SELECT * FROM "{table}" LIMIT 1').fetchone()
            assert existing is not None
            placeholders = ",".join("?" for _ in existing)
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f'INSERT OR REPLACE INTO "{table}" VALUES ({placeholders})', existing)


def test_batches_require_new_effective_examples_and_retain_snapshot(store):
    for candidate_id in range(100):
        complete(store, start(store, candidate_id=candidate_id + 1))
    original = store.examples()[0]
    store.correct(original["example_id"], 7, human_ground_truth={"human_primary_type": "policy"}, reason="Source checked")
    batch = store.create_batch(100)
    assert batch["sample_count"] == 100
    assert batch["class_distribution"] == {"competition_notice": 99, "policy": 1}
    assert batch["status"] == "ready_for_evaluation"
    assert batch["created_at"]
    assert original["example_id"] not in batch["example_ids"]
    canonical = json.dumps(batch["dataset_snapshot"], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert batch["dataset_hash"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError):
        store.create_batch(100)
    store.correct(store.examples()[0]["example_id"], 7, human_ground_truth={"human_primary_type": "policy"}, reason="Later source checked")
    assert store.batches() == [batch]
    with pytest.raises(ValueError):
        store.create_batch(100)


@pytest.mark.parametrize("minimum", [0, 1, 99, 101, 301, True])
def test_batch_minimum_accepts_only_supported_milestones(store, minimum):
    with pytest.raises(ValueError):
        store.create_batch(minimum)


def test_formal_and_known_business_paths_are_refused_without_open(monkeypatch, tmp_path):
    connect_calls = []
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: connect_calls.append(args))
    cls = store_class()
    project = Path(__file__).resolve().parents[2]
    for path in (project / "data" / "v02.sqlite", project / "data" / "dev.sqlite"):
        with pytest.raises(ValueError):
            cls(path)
    configured = tmp_path / "configured-business.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{configured.as_posix()}")
    with pytest.raises(ValueError):
        cls(configured)
    assert connect_calls == []


def test_existing_unrelated_database_is_not_modified(tmp_path):
    path = tmp_path / "business.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE candidates (id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO candidates (title) VALUES ('protected')")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store_class()(path)
    assert path.read_bytes() == before


def test_pending_sessions_return_only_owned_active_submissions(store):
    pending = start(store)
    store.event(pending["session_id"], 7, "submit", {"human_primary_type": "competition_notice"})
    start(store, candidate_id=102)
    foreign = start(store, candidate_id=103, admin_id=8)
    store.event(foreign["session_id"], 8, "submit", {"human_primary_type": "policy"})
    ready = store.pending_sessions(7, candidate_id=101)
    assert [row["session_id"] for row in ready] == [pending["session_id"]]
    assert ready[0]["events"][0]["details"]["human_primary_type"] == "competition_notice"
    complete(store, pending)
    assert store.pending_sessions(7) == []


def test_replace_cannot_rewrite_existing_captured_labels(store):
    original = complete(store, start(store))
    with sqlite3.connect(store.path) as connection:
        row = connection.execute("SELECT * FROM learning_examples WHERE example_id=?", (original["example_id"],)).fetchone()
        columns = [row[1] for row in connection.execute("PRAGMA table_info(learning_examples)")]
        values = list(row)
        values[columns.index("human_ground_truth")] = json.dumps({"human_primary_type": "forged"})
        placeholders = ",".join("?" for _ in values)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(f"INSERT OR REPLACE INTO learning_examples VALUES ({placeholders})", values)
    assert store.examples()[0]["human_ground_truth"]["human_primary_type"] == "competition_notice"


def test_correction_preserves_unspecified_committed_human_dimensions(store):
    original = complete(store, start(store), human={
        "human_primary_type": "competition_notice", "human_action": "approve",
        "human_field_decisions": {"title": "approve"}, "human_note": "Committed source was checked",
    })
    corrected = store.correct(original["example_id"], 7, human_ground_truth={"human_primary_type": "policy"}, reason="Type correction")
    assert corrected["human_ground_truth"]["human_primary_type"] == "policy"
    assert corrected["human_ground_truth"]["human_action"] == "approve"
    assert corrected["human_ground_truth"]["human_field_decisions"] == {"title": "approve"}
    assert corrected["human_ground_truth"]["human_note"] == "Committed source was checked"
