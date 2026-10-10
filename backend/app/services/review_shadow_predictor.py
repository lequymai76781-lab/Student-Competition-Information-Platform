"""Observational rule baseline: no database, human labels, training, or approvals.

The only filesystem reads fingerprint this module and its rule dependencies at
import time. Scores remain rule strengths, not calibrated probabilities.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from app.services.hierarchical_source_classifier import classify_source_document
from app.services.policy_safety_classifier import classify_policy


_SOURCE_KEYS = frozenset({
    "title", "source_title", "source_url", "url", "publisher", "section",
    "content_preview", "content_text", "body", "attachment_titles",
    "source_type", "content_is_complete", "content_truncated",
})
_FEATURE_KEYS = frozenset({
    "candidate_id", "source_id", "title", "publisher", "school", "competition",
    "edition", "source_type", "source_url", "document_preview", "entity_type", "kind", "flags",
})
_LABEL_KEYS = frozenset({
    "classification", "classifications", "decisions", "decision", "verification",
    "labels", "history", "review", "note", "notes", "confidence", "risk_level",
    "primary_type", "secondary_type", "is_policy", "policy_assessment",
})


def _without_labels(value):
    if isinstance(value, dict):
        return {key: _without_labels(item) for key, item in value.items()
                if isinstance(key, str) and key not in _LABEL_KEYS
                and not key.startswith(("human_", "shadow_", "review_", "verification_", "classification_"))}
    if isinstance(value, list):
        return [_without_labels(item) for item in value]
    return deepcopy(value)


def _model_version() -> str:
    directory = Path(__file__).resolve().parent
    fingerprint = hashlib.sha256()
    for name in (
        "review_shadow_predictor.py", "hierarchical_source_classifier.py",
        "policy_safety_classifier.py", "source_document_classifier.py",
        "document_taxonomy.py", "document_calibration_policy.py",
    ):
        fingerprint.update(name.encode("utf-8") + b"\0")
        fingerprint.update(hashlib.sha256((directory / name).read_bytes()).digest())
    return "shadow-rules-v1+sha256-" + fingerprint.hexdigest()


MODEL_VERSION = _model_version()


def _safe_source(source: dict) -> dict:
    safe = {key: value for key, value in source.items() if key in _SOURCE_KEYS and (
        type(value) is bool if key in {"content_is_complete", "content_truncated"}
        else isinstance(value, str) and key != "attachment_titles")}
    titles = source.get("attachment_titles") or []
    if isinstance(titles, str):
        titles = [titles]
    titles = [item for item in titles if isinstance(item, str)] if isinstance(titles, list) else []
    if isinstance(source.get("attachment_title"), str):
        titles.append(source["attachment_title"])
    attachments = source.get("attachments")
    if isinstance(attachments, list):
        titles.extend(item["title"] for item in attachments
                      if isinstance(item, dict) and isinstance(item.get("title"), str))
    if titles:
        safe["attachment_titles"] = list(dict.fromkeys(titles))
    return safe


def prediction_features(input_features: dict) -> dict:
    """Make an isolated allowlisted input for baseline and replay challengers.

    Original source text is evidence. Historical classifications, review notes,
    verification status, and saved human decisions are never model features.
    """
    result = {key: _without_labels(value) for key, value in input_features.items() if key in _FEATURE_KEYS}
    source = input_features.get("source")
    result["source"] = _safe_source(source if isinstance(source, dict) else input_features)
    if not result["source"].get("title") and isinstance(input_features.get("title"), str):
        result["source"]["title"] = input_features["title"]
    if not result["source"].get("content_preview") and isinstance(input_features.get("document_preview"), str):
        result["source"]["content_preview"] = input_features["document_preview"]
    proposals = input_features.get("proposals") or []
    result["proposals"] = []
    if isinstance(proposals, list):
        for proposal in proposals:
            if not isinstance(proposal, dict):
                continue
            saved = {key: _without_labels(proposal[key]) for key in ("id", "field_name", "candidate_value", "current_value")
                     if key in proposal}
            if isinstance(proposal.get("source"), dict):
                saved["source"] = _safe_source(proposal["source"])
            result["proposals"].append(saved)
    return result


def predict_shadow(input_features: dict) -> dict:
    """Predict independently of human review; suggestions confer no authority."""
    features = prediction_features(input_features)
    source = features["source"]
    flags = features.get("flags") or []
    has_conflicts = any(isinstance(flag, str) and ("CONFLICT" in flag.upper() or flag.upper() == "HIGH_RISK")
                        for flag in flags) if isinstance(flags, (list, tuple)) else False
    classification = classify_source_document(
        source, has_fact_changes=bool(features["proposals"]), has_conflicts=has_conflicts,
    )
    policy = classify_policy(source)
    field_names = dict.fromkeys(proposal["field_name"] for proposal in features["proposals"]
                               if isinstance(proposal.get("field_name"), str) and proposal["field_name"].strip())
    return {
        "shadow_primary_type": classification["primary_type"],
        "shadow_secondary_type": classification["secondary_type"],
        "shadow_policy_prediction": policy["is_policy"],
        "shadow_risk_level": classification["risk_level"],
        "shadow_suggested_action": "defer",
        "shadow_field_decisions": {name: "defer" for name in field_names},
        "shadow_confidence": classification["confidence"],
        "shadow_reason": classification["classification_reason"] + "；" + policy["policy_reason"]
                         + "；仅观察预测，字段与关系等待人工审核，不产生批准或写入。",
        "shadow_model_version": MODEL_VERSION,
        "shadow_created_at": datetime.now(timezone.utc).isoformat(),
    }
