"""CLI integration tests use isolated synthetic files, never live review samples."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "replay_review_learning.py"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def annotation(identity="one", primary="registration_notice", secondary=None, **extra):
    return {"source_id": identity, "human_primary_type": primary,
            "human_secondary_types": [] if secondary is None else secondary,
            "label_provenance": "human", "status": "annotated", "skipped": False,
            "annotated_at": "2026-10-01T01:00:00+00:00", "annotated_by": "test:human",
            "predicted_type": "registration_notice", "predicted_confidence": .94,
            "prediction_exposed": False, "revision": 1, "note": "", **extra}


def golden_inputs(tmp_path, annotations=None, sources=None):
    snapshot = write_json(tmp_path / "human.json", {
        "dataset_id": "isolated-test-not-live", "annotations": annotations or [annotation()],
    })
    source_path = write_json(tmp_path / "sources.json", sources if sources is not None else [
        {"source_id": "one", "title": "竞赛报名通知", "source_url": "https://example.test/one",
         "classification": {"document_type": "policy_recognition_document"}},
    ])
    return snapshot, source_path


def run_cli(*arguments):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                          capture_output=True, text=True, encoding="utf-8", timeout=20)


def test_cli_requires_explicit_output_and_does_not_write_a_default_file(tmp_path):
    snapshot, sources = golden_inputs(tmp_path)
    before = set(tmp_path.iterdir())
    result = run_cli("--golden-snapshot", snapshot, "--source-snapshot", sources)
    assert result.returncode == 2
    assert "--output" in result.stderr
    assert set(tmp_path.iterdir()) == before


def test_golden_cli_preserves_raw_labels_and_does_not_create_current_human_samples(tmp_path):
    rows = [annotation(secondary=["organization_notice"], note="竞赛奖励管理办法 第一条"),
            annotation("two", "award_policy_document")]
    source_rows = [
        {"source_id": "one", "title": "竞赛结果公示", "source_url": "https://example.test/one",
         "classification": {"document_type": "registration_notice"}},
        {"source_id": "two", "title": "大学学科竞赛奖励管理办法", "publisher": "大学教务处",
         "content_preview": "第一条 本办法适用于学科竞赛奖励。第二条 遵照执行。"},
    ]
    snapshot, sources = golden_inputs(tmp_path, rows, source_rows)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (snapshot, sources)}
    output = tmp_path / "new-report.json"
    result = run_cli("--golden-snapshot", snapshot, "--source-snapshot", sources, "--output", output)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["historical_human_n"] == 2
    assert report["source_pool_n"] == 2
    assert report["current_loop_human_n"] == report["learning_samples_created"] == report["training_batches_created"] == 0
    assert report["counts_toward_current_human_reviews"] is False
    assert report["evaluation_mode"] == "historical_replay"
    assert report["model_updated"] is False
    assert report["input_hashes_unchanged"] is True
    first = next(row for row in report["records"] if row["source_id"] == "one")
    assert first["original_annotation"] == rows[0]
    assert first["human_primary_type_raw"] == "registration_notice"
    assert first["human_secondary_types_raw"] == ["organization_notice"]
    assert first["human_primary7"] == "participation"
    assert first["human_secondary_primary7"] == ["participation"]
    assert first["human_ground_truth"]["human_secondary_type"] is None
    assert first["human_ground_truth"]["human_risk_level"] is None
    assert first["human_ground_truth"]["human_action"] is None
    assert first["human_ground_truth"]["human_field_decisions"] is None
    assert "classification" not in first["input_features"]["source"]
    assert first["prediction"]["shadow_primary_type"] == "result"
    window = report["replay_performance"]["windows"]["all"]
    assert window["primary_accuracy"] == .5
    assert window["primary_denominator"] == 2
    assert window["secondary_denominator"] == window["risk_denominator"] == window["field_denominator"] == 0
    assert window["policy_precision"] == window["policy_recall"] == 1
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in before.items())


def test_missing_source_is_an_explicit_abstention_and_remains_in_human_denominator(tmp_path):
    snapshot, sources = golden_inputs(tmp_path, [annotation(), annotation("missing")])
    output = tmp_path / "missing-source-report.json"
    result = run_cli("--golden-snapshot", snapshot, "--source-snapshot", sources, "--output", output)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["historical_human_n"] == 2
    assert report["missing_source_ids"] == ["missing"]
    assert report["failure_count"] == 1
    window = report["replay_performance"]["windows"]["all"]
    assert window["primary_accuracy"] == .5
    assert window["primary_denominator"] == 2
    missing = next(row for row in report["records"] if row["source_id"] == "missing")
    assert missing["source_evidence_status"] == "missing"
    assert missing["prediction"] == {}
    assert missing["prediction_error"]


def test_cli_excludes_unrecorded_or_nonhuman_annotations_with_reasons(tmp_path):
    snapshot, sources = golden_inputs(tmp_path, [annotation(), annotation("machine", label_provenance="automation"),
                                               annotation("unfinished", status="pending")])
    output = tmp_path / "filtered.json"
    result = run_cli("--golden-snapshot", snapshot, "--source-snapshot", sources, "--output", output)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["historical_human_n"] == 1
    assert len(report["excluded_records"]) == 2
    assert {row["source_id"] for row in report["excluded_records"]} == {"machine", "unfinished"}


@pytest.mark.parametrize("duplicate_target", ["annotations", "sources"])
def test_cli_rejects_ambiguous_duplicate_id_evidence(tmp_path, duplicate_target):
    rows = [annotation(), annotation()] if duplicate_target == "annotations" else [annotation()]
    sources_data = [{"source_id": "one", "title": "报名通知"}]
    if duplicate_target == "sources":
        sources_data.append({"source_id": "one", "title": "获奖结果"})
    snapshot, sources = golden_inputs(tmp_path, rows, sources_data)
    output = tmp_path / "must-not-exist.json"
    result = run_cli("--golden-snapshot", snapshot, "--source-snapshot", sources, "--output", output)
    assert result.returncode == 2
    assert "duplicate" in result.stderr.lower()
    assert not output.exists()


@pytest.mark.parametrize("target", ["existing", "input", "database"])
def test_cli_refuses_to_overwrite_old_evidence_or_use_database_output(tmp_path, target):
    snapshot, sources = golden_inputs(tmp_path)
    existing = write_json(tmp_path / "old-evidence.json", {"protected": True})
    output = {"existing": existing, "input": snapshot, "database": tmp_path / "learning.sqlite"}[target]
    before = {path: path.read_bytes() for path in (snapshot, sources, existing)}
    result = run_cli("--golden-snapshot", snapshot, "--source-snapshot", sources, "--output", output)
    assert result.returncode == 2
    assert "refusing" in result.stderr.lower()
    assert all(path.read_bytes() == value for path, value in before.items())
    assert not (tmp_path / "learning.sqlite").exists()


def test_learning_examples_input_preserves_answers_and_excludes_superseded_rows(tmp_path):
    row = {
        "id": "sample-1", "created_at": "2026-10-01T00:00:00+00:00", "learning_status": "active",
        "provenance": {"origin": "real_candidate", "actor_mode": "human", "source": "review_audit"},
        "input_features": {"source": {"title": "竞赛报名通知"}},
        "human_ground_truth": {"human_primary_type": "participation", "human_policy": False,
                               "human_secondary_type": None, "human_risk_level": None,
                               "human_action": "reject", "human_field_decisions": {"organizer": "reject"}},
        "shadow_prediction": {"shadow_primary_type": "information", "shadow_model_version": "old-test"},
    }
    superseded = {**deepcopy(row), "id": "superseded", "learning_status": "superseded"}
    path = write_json(tmp_path / "examples.json", {"examples": [row, superseded]})
    before = path.read_bytes()
    output = tmp_path / "examples-report.json"
    result = run_cli("--input", path, "--output", output)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["historical_human_n"] == 1
    assert report["records"][0]["human_ground_truth"] == row["human_ground_truth"]
    assert report["replay_performance"]["windows"]["all"]["primary_accuracy"] == 1
    assert report["baseline_performance"]["windows"]["all"]["primary_accuracy"] == 0
    assert report["current_loop_human_n"] == 0
    assert path.read_bytes() == before


def test_learning_input_requires_recorded_human_provenance(tmp_path):
    path = write_json(tmp_path / "not-human.json", [{"id": "fake", "input_features": {},
                                                  "human_ground_truth": {"human_primary_type": "policy"}}])
    output = tmp_path / "rejected.json"
    result = run_cli("--input", path, "--output", output)
    assert result.returncode == 2
    assert "provenance" in result.stderr.lower()
    assert not output.exists()
