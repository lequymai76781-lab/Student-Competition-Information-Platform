import json
from pathlib import Path

from app.models import University


ROOT = Path(__file__).resolve().parents[2]


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_master_and_internal_batches_are_complete_and_disjoint():
    master = load("data/seeds/general_undergraduate_master.json")["institutions"]
    batches = load("data/seeds/general_undergraduate_batches.json")["batches"]
    assert len(master) == 1228
    assert len({row["name"] for row in master}) == 1228
    assert len(batches["general_a"]) == 32
    assert len(batches["general_b"]) == 1196
    assert not (set(batches["general_a"]) & set(batches["general_b"]))
    assert set(batches["general_a"]) | set(batches["general_b"]) == {row["name"] for row in master}


def test_batch_is_not_part_of_public_university_schema():
    columns = {column.name for column in University.__table__.columns}
    assert "collection_batch" not in columns
    assert "is_yiben" not in columns
    assert "is_erben" not in columns
    assert "university_level" not in columns


def test_checkpoint_has_terminal_status_for_every_batch_a_school():
    checkpoint = load("data/checkpoints/general_undergraduate_batch_a.json")
    batch_a = set(load("data/seeds/general_undergraduate_batches.json")["batches"]["general_a"])
    terminal = {"VERIFIED_DATA", "VERIFIED_NO_PUBLIC_DATA", "ACCESS_LIMITED", "DEEP_PASS_REQUIRED", "AMBIGUOUS"}
    assert len(checkpoint["schools"]) == 32
    assert {row["school"] for row in checkpoint["schools"]} == batch_a
    assert all(row["final_status"] in terminal for row in checkpoint["schools"])
    assert all(row["checked_sources"] for row in checkpoint["schools"])


def test_checkpoint_resume_and_idempotency_audits_pass():
    result = load("data/reports/general_undergraduate_batch_a_idempotency.json")
    assert result["pass"] is True
    assert result["resume_pass"] is True
    assert result["resume"] == {"total": 32, "completed": 32, "next": None}


def test_duplicate_relation_source_recognition_and_orphan_audits_pass():
    audit = load("data/reports/general_undergraduate_batch_a_audit.json")
    required = {
        "duplicate_competition_audit", "relation_audit", "source_audit",
        "recognition_audit", "orphan_audit", "false_positive_cleanup",
    }
    assert all(audit["checks"][name] for name in required)
    assert audit["summary"] == {"PASS": 14}


def test_qa_records_population_shortfall_without_fabricating_passes():
    qa = load("data/reports/general_undergraduate_batch_a_qa.json")
    assert qa["requested_sample_size"] == 30
    assert qa["available_formal_relations"] == 0
    assert qa["summary"] == {"PASS": 0, "FAIL": 0, "UNCERTAIN": 30}
