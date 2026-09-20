"""Import the verified Nanjing University of the Arts recognition rule."""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import Competition, CompetitionPolicyRecognition, PolicyDocument, University

URL = "https://www.nua.edu.cn/_upload/article/files/41/40/a87c2cfc4877b63b950a4eb5c4b0/a7531b18-f15b-4592-b9b7-6c9806e1b60d.pdf"
TITLE = "南京艺术学院毕业展演优秀奖评选办法（修订）"
EVIDENCE = "学校正式发布毕业展演优秀奖评选办法，设立评选程序和优秀奖；认定范围为全校毕业展演。"


def main():
    created = 0
    with SessionLocal() as db:
        school = db.scalar(select(University).where(University.name == "南京艺术学院"))
        competition = db.scalar(select(Competition).where(Competition.name == "南京艺术学院毕业展演优秀奖"))
        doc = db.scalar(select(PolicyDocument).where(PolicyDocument.source_url == URL))
        if not doc:
            doc = PolicyDocument(
                university_id=school.id, scope_type="university", title=TITLE,
                policy_type="competition_recognition", year=2026, latest_available_year=2026,
                publisher="南京艺术学院", source_url=URL, attachment_url=URL,
                official_domain="nua.edu.cn", authority_level="A2",
                published_at=datetime(2026,4,14,tzinfo=timezone.utc), content_text=EVIDENCE,
                document_hash=hashlib.sha256(URL.encode()).hexdigest(), is_current=True,
                is_verified=True, verification_status="verified_official",
                parser_type="official_pdf", source_type="university_official",
                metadata_json={"task":"SPECIALIZED_INSTITUTIONS_COVERAGE_01","recognition_scope":"university","event_type":"competition_showcase"},
            )
            db.add(doc); db.flush(); created += 1
        evidence_hash = hashlib.sha256(EVIDENCE.encode()).hexdigest()
        rec = db.scalar(select(CompetitionPolicyRecognition).where(
            CompetitionPolicyRecognition.policy_document_id == doc.id,
            CompetitionPolicyRecognition.competition_id == competition.id,
            CompetitionPolicyRecognition.evidence_hash == evidence_hash,
        ))
        if not rec:
            db.add(CompetitionPolicyRecognition(
                competition_id=competition.id, policy_document_id=doc.id, university_id=school.id,
                year=2026, recognition_status="recognized", recognition_level="校级毕业展演优秀奖",
                usage_type="award", evidence_text=EVIDENCE, evidence_hash=evidence_hash,
                evidence_section="评选办法", confidence=1.0, needs_manual_review=False,
            )); created += 1
        db.commit()
    print({"created":created})


if __name__ == "__main__": main()
