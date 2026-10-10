"""Automation permissions after the first 100 real human primary labels.

At 0.90 the frozen classifier was correct for 39/77 automatic proposals; at
0.95 it was correct for 2/5. No observed cutoff establishes reliable automatic
classification, informational routing, or policy recognition. Scores remain
explanatory rule strengths. None means disabled, never an invented threshold.
"""
VERSION = "golden-20261001-hold-v1"
AUTO_THRESHOLDS = {kind: None for kind in (
    "registration_notice", "organization_notice", "selection_notice", "recommendation_notice",
    "result_notice", "publicity_notice", "completion_news", "competition_intro", "event_news",
    "policy_recognition_document", "award_policy_document", "postgraduate_policy_document",
    "comprehensive_evaluation_policy_document", "innovation_credit_policy_document", "repost",
    "deadline_extension", "correction_notice", "rule_update", "historical_material", "other",
)}
INFORMATIONAL_AUTO_ENABLED = False
POLICY_AUTO_ENABLED = False


def review_status(primary, confidence, *, has_evidence, ambiguous, high_risk):
    threshold = AUTO_THRESHOLDS.get(primary)
    if threshold is not None and confidence >= threshold and not high_risk and not ambiguous:
        return "AUTO_CLASSIFIED"
    if primary != "other" and has_evidence and not ambiguous and not high_risk:
        return "NEEDS_QUICK_CONFIRM"
    return "NEEDS_MANUAL_CLASSIFICATION"

# Hierarchical permissions are distinct from legacy fine-class calibration.
# Same-set evidence supports only clear participation type suggestions; it does
# not authorize any proposed field value, informational archival, or relation.
HIERARCHICAL_POLICY_VERSION = "hierarchical-20261001-conservative-v1"
HIERARCHICAL_AUTO_THRESHOLDS = {
    "participation": 0.90,
    "result": None,
    "information": None,
    "policy": None,
    "update": None,
    "repost": None,
    "other": None,
}
HIERARCHICAL_INFORMATIONAL_ENABLED = False
