"""Replay saved human evidence without opening a database or changing models.

Examples (run from the repository root):
  backend/venv/Scripts/python.exe backend/scripts/replay_review_learning.py \
    --golden-snapshot .codex-qa/golden-calibration-20261001/human-snapshot.json \
    --output .codex-qa/human-in-loop-20261007/historical-replay.json
  backend/venv/Scripts/python.exe backend/scripts/replay_review_learning.py \
    --input exported-learning-examples.json --output new-replay-report.json

Output must be a new JSON file. Historical annotations never create current
learning samples, training batches, or evidence for the ten live human reviews.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.document_taxonomy import FINE_TO_PRIMARY, HIERARCHY_VERSION, PRIMARY_TYPES
from app.services.review_learning_metrics import replay_examples
from app.services.review_shadow_predictor import MODEL_VERSION, predict_shadow, prediction_features


DEFAULT_SOURCES = ROOT / ".codex-qa/document-policy/replay-verified/source-replay.json"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _primary7(value):
    if value in PRIMARY_TYPES:
        return value
    if value in FINE_TO_PRIMARY:
        return FINE_TO_PRIMARY[value]
    raise ValueError(f"Unrecognized recorded human label: {value!r}")


def _unique_records(rows, key, description):
    if not isinstance(rows, list):
        raise ValueError(f"{description} must be an array")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or row.get(key) in (None, ""):
            raise ValueError(f"{description} record is missing {key}")
        identity = str(row[key])
        if identity in indexed:
            raise ValueError(f"Duplicate {description} {key}: {identity}")
        indexed[identity] = row
    return indexed


def _golden_examples(snapshot, source_rows):
    if not isinstance(snapshot, dict) or snapshot.get("fixture_only"):
        raise ValueError("Golden snapshot must contain recorded human evidence, not a fixture-only manifest")
    annotations = _unique_records(snapshot.get("annotations"), "source_id", "annotation")
    sources = _unique_records(source_rows, "source_id", "source")
    examples, records, excluded, missing = [], [], [], []
    for identity, annotation in annotations.items():
        if annotation.get("label_provenance") != "human":
            excluded.append({"source_id": identity, "reason": "label_provenance is not human"})
            continue
        if (annotation.get("status") != "annotated" or annotation.get("skipped")
                or not annotation.get("annotated_by") or not annotation.get("annotated_at")):
            excluded.append({"source_id": identity, "reason": "No completed recorded human annotation"})
            continue
        primary_raw = annotation.get("human_primary_type")
        secondary_raw = annotation.get("human_secondary_types")
        if secondary_raw is not None and not isinstance(secondary_raw, list):
            raise ValueError(f"Historical secondary labels must be an array or null: {identity}")
        primary = _primary7(primary_raw)
        secondary7 = None if secondary_raw is None else [_primary7(label) for label in secondary_raw]
        source = sources.get(identity)
        if source is None:
            missing.append(identity)
        features = prediction_features({"source_id": identity, "source": source or {}})
        human = {
            "human_primary_type": primary, "human_secondary_type": None,
            "human_policy": primary == "policy", "human_risk_level": None,
            "human_action": None, "human_field_decisions": None,
            "human_relation_decision": None, "human_note": annotation.get("note"),
        }
        old_fine = annotation.get("predicted_type")
        old_primary = (old_fine if old_fine in PRIMARY_TYPES else FINE_TO_PRIMARY.get(old_fine))
        original_prediction = {
            "shadow_primary_type": old_primary,
            "shadow_model_version": "historical-frozen-primary-mapped7",
        }
        examples.append({
            "id": identity, "created_at": annotation["annotated_at"], "learning_status": "active",
            "input_features": features, "human_ground_truth": human,
            "shadow_prediction": original_prediction,
            "review_context": {"evaluation_mode": "historical_replay", "dataset_id": snapshot.get("dataset_id")},
        })
        records.append({
            "example_id": identity, "source_id": identity,
            "original_annotation": deepcopy(annotation),
            "human_primary_type_raw": primary_raw, "human_secondary_types_raw": deepcopy(secondary_raw),
            "human_primary7": primary, "human_secondary_primary7": secondary7,
            "human_ground_truth": human, "input_features": features,
            "source_evidence_status": "available" if source is not None else "missing",
            "full_body_available": bool(features["source"].get("content_text") or features["source"].get("body")),
            "preview_available": bool(features["source"].get("content_preview")),
        })
    return examples, records, {
        "dataset_id": snapshot.get("dataset_id"), "source_pool_n": len(sources),
        "excluded_records": excluded, "missing_source_ids": sorted(missing),
        "original_primary_distribution": dict(sorted(Counter(row["human_primary_type_raw"] for row in records).items())),
        "mapped_primary_distribution": dict(sorted(Counter(row["human_primary7"] for row in records).items())),
        "mapping_version": HIERARCHY_VERSION,
        "human_policy_basis": "Derived only from the explicitly recorded human primary label mapped to policy; "
                              "not an independent historical policy adjudication.",
        "secondary_basis": "Original multilabel secondary values and their seven-class mappings are preserved. "
                           "They do not fill the new singular secondary label or replace primary truth.",
        "baseline_basis": "Only the frozen predicted primary type is mapped to seven classes; "
                          "the historical independent policy/risk/action/field predictions were not recorded.",
    }


def _learning_examples(payload):
    rows = payload.get("examples") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("--input must contain an examples array or be an array of learning examples")
    indexed, examples, records, excluded = {}, [], [], []
    for original in rows:
        if not isinstance(original, dict):
            raise ValueError("Learning examples must be objects")
        identity = original.get("id", original.get("example_id"))
        if identity in (None, ""):
            raise ValueError("Learning example is missing id")
        identity = str(identity)
        if identity in indexed:
            raise ValueError(f"Duplicate learning example id: {identity}")
        indexed[identity] = original
        if original.get("learning_status", "active") not in {"active", "corrected"}:
            excluded.append({"example_id": identity, "reason": "Not an effective learning example"})
            continue
        provenance = original.get("provenance") or {}
        if (provenance.get("actor_mode") != "human" or provenance.get("origin") != "real_candidate"
                or provenance.get("source") != "review_audit"):
            raise ValueError(f"Learning example requires explicit recorded human review provenance: {identity}")
        if not isinstance(original.get("input_features"), dict) or not isinstance(original.get("human_ground_truth"), dict):
            raise ValueError(f"Missing input_features or human_ground_truth: {identity}")
        _primary7(original["human_ground_truth"].get("human_primary_type"))
        sample = deepcopy(original)
        sample["input_features"] = prediction_features(sample["input_features"])
        examples.append(sample)
        features = sample["input_features"]
        records.append({
            "example_id": original.get("id", original.get("example_id")),
            "source_id": features.get("source_id"),
            "human_ground_truth": deepcopy(sample["human_ground_truth"]),
            "input_features": features, "source_evidence_status": "available",
            "full_body_available": bool(features["source"].get("content_text") or features["source"].get("body")),
            "preview_available": bool(features["source"].get("content_preview")),
        })
    return examples, records, {
        "dataset_id": payload.get("dataset_id") if isinstance(payload, dict) else None,
        "source_pool_n": None, "excluded_records": excluded, "missing_source_ids": [],
        "human_policy_basis": "Only the saved human_policy value; absent dimensions remain absent.",
        "secondary_basis": "Only the saved human_secondary_type value; absent dimensions remain absent.",
        "baseline_basis": "The original saved shadow_prediction is compared without modification.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="Exported immutable learning examples JSON")
    inputs.add_argument("--golden-snapshot", type=Path, help="Existing recorded-human Golden Set snapshot JSON")
    parser.add_argument("--source-snapshot", type=Path, help="Original frozen source JSON for --golden-snapshot")
    parser.add_argument("--output", type=Path, required=True, help="A new JSON report path; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.source_snapshot and not args.golden_snapshot:
            raise ValueError("--source-snapshot requires --golden-snapshot")
        output = args.output.resolve()
        if output.suffix.lower() != ".json":
            raise ValueError("Refusing non-JSON output; databases are never replay outputs")
        if output.exists() or output.is_symlink():
            raise ValueError("Refusing to overwrite an existing output or input file")
        paths = [args.input.resolve()] if args.input else [
            args.golden_snapshot.resolve(), (args.source_snapshot or DEFAULT_SOURCES).resolve()]
        before = {path: sha256(path.read_bytes()).hexdigest() for path in paths}
        if args.input:
            examples, records, metadata = _learning_examples(_read(paths[0]))
        else:
            examples, records, metadata = _golden_examples(_read(paths[0]), _read(paths[1]))
        missing = set(metadata["missing_source_ids"])

        def predict_available_source(features):
            if str(features.get("source_id")) in missing:
                raise ValueError("Frozen source evidence is missing; prediction abstains")
            return predict_shadow(features)

        replay = replay_examples(examples, predictor=predict_available_source)
        by_id = {str(row["example_id"]): row for row in replay["predictions"]}
        for record in records:
            prediction = by_id[str(record["example_id"])]
            record.update({
                "original_shadow_prediction": prediction["original_shadow_prediction"],
                "prediction": prediction["replay_shadow_prediction"], "comparison": prediction["comparison"],
                "prediction_error": prediction["error"],
            })
        after = {path: sha256(path.read_bytes()).hexdigest() for path in paths}
        if before != after:
            raise ValueError("Input evidence changed during replay; no output was saved")
        report = {
            **replay, **metadata, "schema_version": "review-learning-historical-replay-v1",
            "created_at": datetime.now(timezone.utc).isoformat(), "model_version": MODEL_VERSION,
            "replay_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "input_kind": "learning_examples" if args.input else "golden_snapshot",
            "historical_human_n": replay["sample_count"], "current_loop_human_n": 0,
            "learning_samples_created": 0, "training_batches_created": 0,
            "counts_toward_current_human_reviews": False, "records": records,
            "input_hashes_unchanged": True,
            "input_files": [{"path": str(path), "sha256_before": before[path], "sha256_after": after[path], "unchanged": True}
                            for path in paths],
            "source_evidence": {"full_body_n": sum(row["full_body_available"] for row in records),
                                "preview_n": sum(row["preview_available"] for row in records),
                                "missing_n": len(missing)},
            "limitations": [
                "Historical replay only; no current human review, training sample, training batch, or model update was created.",
                "These labels were used in earlier development; this is not independent held-out validation.",
                "Historical timing/order windows are not measurements of current review throughput.",
                "Missing sources and failed predictions remain abstentions in the human-label denominators.",
                "Saved source previews may be incomplete; document classification does not approve facts or policy relations.",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    summary = report["replay_performance"]["windows"]["all"]
    print(json.dumps({"output": str(output), "historical_human_n": report["historical_human_n"],
                      "current_loop_human_n": 0, "failure_count": report["failure_count"],
                      "primary_accuracy": summary["primary_accuracy"], "primary_denominator": summary["primary_denominator"],
                      "policy_precision": summary["policy_precision"], "policy_recall": summary["policy_recall"],
                      "input_hashes_unchanged": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
