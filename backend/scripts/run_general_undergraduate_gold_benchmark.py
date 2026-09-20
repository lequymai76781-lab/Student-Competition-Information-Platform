"""Run the deterministic Gold Set discovery/evidence benchmark.

The frozen search snapshot contains only URLs returned by policy-specific
queries. Search snippets are never evidence: every accepted document is fetched
from the school's official domain and parsed locally.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

import httpx

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.crawler.base import DiscoveredLink
from app.crawler.discovery.attachment_discovery import AttachmentDiscoveryService
from app.crawler.discovery.url_normalizer import OfficialUrlNormalizer
from app.crawler.extractors.policy_classifier import PolicyClassifier
from app.crawler.parsers.docx_parser import DocxParser
from app.crawler.parsers.pdf_parser import PdfParser
from app.crawler.parsers.html_parser import HtmlContentParser

GOLD = ROOT / "data/seeds/general_undergraduate_gold_set.json"
SNAPSHOT = ROOT / "data/seeds/general_undergraduate_gold_set_search_snapshot.json"
REPORT = ROOT / "data/reports/general_undergraduate_gold_benchmark.json"
RAW = ROOT / "data/raw/general_undergraduate_gold_set"
TARGET_CATEGORIES = {
    "competition_policy",
    "competition_catalog",
    "innovation_credit_policy",
    "second_classroom_policy",
}


def canonical(url: str) -> str:
    return OfficialUrlNormalizer().normalize(url)


def official(url: str, domain: str) -> bool:
    return OfficialUrlNormalizer().is_official(url, domain)


def fetch(client: httpx.Client, url: str, referer: str | None = None, retries: int = 2) -> tuple[httpx.Response | None, str | None]:
    headers = {"Referer": referer} if referer else {}
    last_error: str | None = None
    for attempt in range(retries + 1):
        try:
            response = client.get(url, headers=headers)
            if response.status_code >= 400:
                return None, f"HTTP {response.status_code}"
            return response, None
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(1.5 ** attempt)
    return None, last_error


def save_and_parse(response: httpx.Response, document_type: str, url: str) -> tuple[str, str | None]:
    RAW.mkdir(parents=True, exist_ok=True)
    digest = sha256(response.content).hexdigest()
    path = RAW / f"{digest[:20]}.{document_type}"
    if not path.exists():
        path.write_bytes(response.content)
    if document_type == "pdf":
        parsed = PdfParser().parse(path)
    elif document_type == "docx":
        parsed = DocxParser().parse(path)
    else:
        return "", f"benchmark parser unsupported: {document_type}"
    return parsed.text, parsed.error


def main() -> None:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["results"]
    parser = HtmlContentParser()
    attachments = AttachmentDiscoveryService()
    classifier = PolicyClassifier()
    school_reports: list[dict] = []
    all_expected: list[tuple[str, dict]] = []
    all_found: set[tuple[str, str]] = set()
    accepted_predictions: list[tuple[str, str]] = []
    predicted_recognition: list[tuple[str, str]] = []
    expected_lookup: dict[tuple[str, str], dict] = {}
    discovered_attachment_keys: set[tuple[str, str]] = set()
    false_negatives: list[dict] = []
    transport_types: set[str] = set()

    headers = {
        "User-Agent": "StudentCompetitionIntelligenceBot/0.2 (+policy-research; contact: local-dev)",
        "Accept": "text/html,application/pdf,application/msword,application/vnd.ms-excel,*/*",
    }
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        for school in gold["schools"]:
            name = school["school"]
            domain = school["official_domain"]
            expected = school["expected_evidence"]
            discovered: dict[str, dict] = {}
            failures: list[dict] = []
            for item in snapshot.get(name, []):
                url = canonical(item["url"])
                if not url or not official(url, domain):
                    continue
                discovered[url] = {"title": item["title"], "source": "external_site_search"}
                path_suffix = Path(urlsplit(url).path).suffix.lower()
                if path_suffix in AttachmentDiscoveryService.extensions:
                    transport_types.add(path_suffix.lstrip("."))
                    discovered_attachment_keys.add((name, url))
                    continue
                response, error = fetch(client, url)
                if error:
                    failures.append({"url": url, "stage": "search_result_fetch", "error": error})
                    continue
                page = parser.parse(response.text, str(response.url))
                for attachment in attachments.discover(page.links):
                    attachment_url = canonical(attachment.url)
                    if not attachment_url or not official(attachment_url, domain):
                        continue
                    discovered[attachment_url] = {
                        "title": attachment.link_text or attachment.filename or attachment_url,
                        "source": canonical(str(response.url)),
                    }
                    if attachment.extension:
                        transport_types.add(attachment.extension)
                    discovered_attachment_keys.add((name, attachment_url))

            school_found = 0
            school_accepted = 0
            school_recognition = 0
            expected_by_url = {canonical(item["expected_source_url"]): item for item in expected}
            for item in expected:
                key = (name, canonical(item["expected_source_url"]))
                all_expected.append((name, item))
                expected_lookup[key] = item
                if key[1] not in discovered:
                    false_negatives.append({
                        "school": name,
                        "target": item["expected_title"],
                        "expected_url": item["expected_source_url"],
                        "actual": sorted(discovered),
                        "failure_stage": "search_or_attachment_discovery",
                    })
                    continue
                all_found.add(key)
                school_found += 1
                response, error = fetch(client, key[1], referer=item.get("parent_url"))
                if error:
                    false_negatives.append({
                        "school": name,
                        "target": item["expected_title"],
                        "expected_url": item["expected_source_url"],
                        "actual": "URL discovered",
                        "failure_stage": f"official_fetch: {error}",
                    })
                    failures.append({"url": key[1], "stage": "official_fetch", "error": error})
                    continue
                if item["document_type"] == "html":
                    page = parser.parse(response.text, str(response.url))
                    text = page.text
                    title = page.title or item["expected_title"]
                    parse_error = None
                else:
                    text, parse_error = save_and_parse(response, item["document_type"], key[1])
                    title = item["expected_title"]
                if parse_error:
                    false_negatives.append({
                        "school": name,
                        "target": item["expected_title"],
                        "expected_url": item["expected_source_url"],
                        "actual": "URL discovered and downloaded",
                        "failure_stage": f"parse: {parse_error}",
                    })
                    failures.append({"url": key[1], "stage": "parse", "error": parse_error})
                    continue
                classification = classifier.classify(title, text)
                if classification.category in TARGET_CATEGORIES:
                    accepted_predictions.append(key)
                    school_accepted += 1
                else:
                    false_negatives.append({
                        "school": name,
                        "target": item["expected_title"],
                        "expected_url": item["expected_source_url"],
                        "actual": f"classified {classification.category}",
                        "failure_stage": "classifier",
                    })
                if classification.recognition_eligible:
                    predicted_recognition.append(key)
                    school_recognition += 1

            school_reports.append({
                "school": name,
                "expected_documents": len(expected),
                "discovered_documents": school_found,
                "accepted_evidence": school_accepted,
                "recognition_evidence_documents": school_recognition,
                "discovered_urls": sorted(discovered),
                "failures": failures,
            })

    expected_count = len(all_expected)
    expected_attachments = sum(item["document_type"] != "html" for _, item in all_expected)
    found_attachments = sum(
        (name, canonical(item["expected_source_url"])) in discovered_attachment_keys
        for name, item in all_expected
        if item["document_type"] != "html"
    )
    valid_accepted = sum(key in expected_lookup for key in accepted_predictions)
    valid_recognition = sum(expected_lookup[key]["recognition_evidence"] for key in predicted_recognition)
    metrics = {
        # A document only counts as recalled after official fetch, parse, and policy classification.
        "document_recall": round(valid_accepted / expected_count, 4) if expected_count else 0,
        "discovery_url_recall": round(len(all_found) / expected_count, 4) if expected_count else 0,
        "attachment_recall": round(found_attachments / expected_attachments, 4) if expected_attachments else 0,
        "evidence_precision": round(valid_accepted / len(accepted_predictions), 4) if accepted_predictions else 0,
        "recognition_precision": round(valid_recognition / len(predicted_recognition), 4) if predicted_recognition else 0,
        "counts": {
            "expected_documents": expected_count,
            "found_documents": valid_accepted,
            "discovered_document_urls": len(all_found),
            "expected_attachments": expected_attachments,
            "found_attachments": found_attachments,
            "accepted_evidence": len(accepted_predictions),
            "predicted_recognition_documents": len(predicted_recognition),
            "valid_predicted_recognition_documents": valid_recognition,
        },
    }
    thresholds = {
        "document_recall": 0.80,
        "attachment_recall": 0.75,
        "evidence_precision": 0.90,
        "recognition_precision": 0.95,
    }
    passed = all(metrics[key] >= value for key, value in thresholds.items())
    payload = {
        "task": "GENERAL_UNDERGRADUATE_DISCOVERY_FIX_01_GOLD_BENCHMARK",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "frozen policy-query discovery snapshot; official-domain refetch and local parse",
        "school_count": len(gold["schools"]),
        "metrics": metrics,
        "thresholds": thresholds,
        "passed": passed,
        "transport_types_observed": sorted(transport_types),
        "schools": school_reports,
        "false_negatives": false_negatives,
        "status_counts": dict(Counter("VERIFIED_DATA" if row["accepted_evidence"] else "DISCOVERY_FAILED" for row in school_reports)),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "metrics": metrics, "false_negatives": len(false_negatives)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
