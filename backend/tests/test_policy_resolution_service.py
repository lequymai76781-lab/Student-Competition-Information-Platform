from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import College, Competition, CompetitionPolicyRecognition, Major, PolicyDocument, University
from app.services.policy_resolution_service import PolicyResolutionService


def _seed_policy_document(
    db: Session,
    *,
    university_id: int,
    title: str,
    scope_type: str = "university",
    college_id: int | None = None,
    major_id: int | None = None,
    year: int | None = 2026,
) -> PolicyDocument:
    digest = sha256(f"{title}|{scope_type}|{college_id}|{major_id}|{year}".encode("utf-8")).hexdigest()
    document = PolicyDocument(
        university_id=university_id,
        college_id=college_id,
        major_id=major_id,
        scope_type=scope_type,
        title=title,
        policy_type="recommendation",
        year=year,
        latest_available_year=year,
        source_url=f"https://example.edu.cn/{digest}.html",
        official_domain="example.edu.cn",
        authority_level="A1",
        content_text=title,
        document_hash=digest,
        is_current=True,
        is_verified=True,
        verification_status="test",
        parser_type="html",
        source_type="university",
        is_demo=False,
    )
    db.add(document)
    db.flush()
    return document


def _seed_recognition(
    db: Session,
    *,
    competition_id: int,
    document: PolicyDocument,
    status: str,
    evidence: str,
    confidence: float = 0.9,
) -> CompetitionPolicyRecognition:
    recognition = CompetitionPolicyRecognition(
        competition_id=competition_id,
        policy_document_id=document.id,
        university_id=document.university_id,
        college_id=document.college_id,
        major_id=document.major_id,
        year=document.year,
        recognition_status=status,
        usage_type="recommendation",
        evidence_text=evidence,
        evidence_hash=sha256(evidence.encode("utf-8")).hexdigest(),
        confidence=confidence,
        needs_manual_review=False,
        is_demo=False,
    )
    db.add(recognition)
    db.flush()
    return recognition


def test_policy_priority_major_college_university(db_session: Session) -> None:
    university = db_session.execute(select(University)).scalars().first()
    competition = db_session.execute(select(Competition)).scalars().first()
    assert university and competition
    college = College(university_id=university.id, name="测试学院")
    major = Major(name="测试专业")
    db_session.add_all([college, major])
    db_session.flush()

    university_doc = _seed_policy_document(db_session, university_id=university.id, title="学校推免政策")
    college_doc = _seed_policy_document(
        db_session,
        university_id=university.id,
        title="学院推免政策",
        scope_type="college",
        college_id=college.id,
    )
    major_doc = _seed_policy_document(
        db_session,
        university_id=university.id,
        title="专业推免政策",
        scope_type="major",
        college_id=college.id,
        major_id=major.id,
    )
    _seed_recognition(db_session, competition_id=competition.id, document=university_doc, status="recognized", evidence="学校认可")
    _seed_recognition(
        db_session,
        competition_id=competition.id,
        document=college_doc,
        status="explicitly_not_recognized",
        evidence="学院不认可",
    )
    _seed_recognition(db_session, competition_id=competition.id, document=major_doc, status="recognized", evidence="专业认可")

    result = PolicyResolutionService().resolve(
        db_session,
        competition_id=competition.id,
        university_id=university.id,
        college_id=college.id,
        major_id=major.id,
        year=2026,
    )

    assert result.effective_scope == "major"
    assert result.effective_status == "recognized"
    assert result.conflict is True
    assert result.needs_manual_review is True


def test_not_mentioned_is_not_not_recognized(db_session: Session) -> None:
    university = db_session.execute(select(University)).scalars().first()
    competition = db_session.execute(select(Competition)).scalars().first()
    assert university and competition
    document = _seed_policy_document(db_session, university_id=university.id, title="未提及比赛的推免政策")

    result = PolicyResolutionService().resolve(
        db_session,
        competition_id=competition.id,
        university_id=university.id,
        year=2026,
    )

    assert document.id == result.effective_policy_document_id
    assert result.effective_status == "not_mentioned"
    assert "不能推断为不认可" in result.reason


def test_latest_year_wins_unless_year_is_requested(db_session: Session) -> None:
    university = db_session.execute(select(University)).scalars().first()
    competition = db_session.execute(select(Competition)).scalars().first()
    assert university and competition
    old_doc = _seed_policy_document(db_session, university_id=university.id, title="2025推免政策", year=2025)
    new_doc = _seed_policy_document(db_session, university_id=university.id, title="2026推免政策", year=2026)
    _seed_recognition(
        db_session,
        competition_id=competition.id,
        document=old_doc,
        status="explicitly_not_recognized",
        evidence="2025不认可",
    )
    _seed_recognition(db_session, competition_id=competition.id, document=new_doc, status="recognized", evidence="2026认可")

    service = PolicyResolutionService()
    latest = service.resolve(db_session, competition_id=competition.id, university_id=university.id)
    requested_old = service.resolve(db_session, competition_id=competition.id, university_id=university.id, year=2025)

    assert latest.effective_status == "recognized"
    assert latest.effective_policy_document_id == new_doc.id
    assert requested_old.effective_status == "explicitly_not_recognized"
    assert requested_old.effective_policy_document_id == old_doc.id
