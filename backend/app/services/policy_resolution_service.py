from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompetitionPolicyRecognition, PolicyDocument


@dataclass(slots=True)
class PolicyResolutionResult:
    competition_id: int
    university_id: int
    college_id: int | None
    major_id: int | None
    year: int | None
    effective_status: str
    effective_scope: str
    effective_policy_document_id: int | None
    effective_recognition_id: int | None
    secondary_policy_document_id: int | None
    conflict: bool
    reason: str
    evidence_text: str | None
    needs_manual_review: bool


class PolicyResolutionService:
    scope_order = ["major", "college", "university"]

    def resolve(
        self,
        db: Session,
        *,
        competition_id: int,
        university_id: int,
        college_id: int | None = None,
        major_id: int | None = None,
        year: int | None = None,
    ) -> PolicyResolutionResult:
        scopes = [
            ("major", major_id),
            ("college", college_id),
            ("university", None),
        ]
        scoped_results = [
            self._scope_result(db, competition_id=competition_id, university_id=university_id, scope_type=scope, scope_id=scope_id, year=year)
            for scope, scope_id in scopes
            if scope == "university" or scope_id is not None
        ]

        effective = next((item for item in scoped_results if item["status"] != "no_policy"), None)
        if effective is None:
            return PolicyResolutionResult(
                competition_id=competition_id,
                university_id=university_id,
                college_id=college_id,
                major_id=major_id,
                year=year,
                effective_status="insufficient_evidence",
                effective_scope="none",
                effective_policy_document_id=None,
                effective_recognition_id=None,
                secondary_policy_document_id=None,
                conflict=False,
                reason="暂未找到公开政策，不能判断认可或不认可。",
                evidence_text=None,
                needs_manual_review=True,
            )

        secondary = next((item for item in scoped_results if item is not effective and item["status"] != "no_policy"), None)
        conflict = bool(secondary and secondary["status"] != effective["status"])
        reason = self._reason(effective["scope"], conflict)
        if effective["status"] == "not_mentioned":
            reason = "当前适用政策未提及该比赛，不能推断为不认可。"

        return PolicyResolutionResult(
            competition_id=competition_id,
            university_id=university_id,
            college_id=college_id,
            major_id=major_id,
            year=year,
            effective_status=effective["status"],
            effective_scope=effective["scope"],
            effective_policy_document_id=effective["policy_document_id"],
            effective_recognition_id=effective["recognition_id"],
            secondary_policy_document_id=secondary["policy_document_id"] if secondary else None,
            conflict=conflict,
            reason=reason,
            evidence_text=effective["evidence_text"],
            needs_manual_review=bool(effective["needs_manual_review"] or conflict),
        )

    def _scope_result(
        self,
        db: Session,
        *,
        competition_id: int,
        university_id: int,
        scope_type: str,
        scope_id: int | None,
        year: int | None,
    ) -> dict:
        recognition_stmt = select(CompetitionPolicyRecognition).where(
            CompetitionPolicyRecognition.competition_id == competition_id,
            CompetitionPolicyRecognition.university_id == university_id,
        )
        policy_stmt = select(PolicyDocument).where(
            PolicyDocument.university_id == university_id,
            PolicyDocument.scope_type == scope_type,
        )
        if scope_type == "major":
            recognition_stmt = recognition_stmt.where(CompetitionPolicyRecognition.major_id == scope_id)
            policy_stmt = policy_stmt.where(PolicyDocument.major_id == scope_id)
        elif scope_type == "college":
            recognition_stmt = recognition_stmt.where(CompetitionPolicyRecognition.college_id == scope_id)
            policy_stmt = policy_stmt.where(PolicyDocument.college_id == scope_id)
        else:
            recognition_stmt = recognition_stmt.where(
                CompetitionPolicyRecognition.college_id.is_(None),
                CompetitionPolicyRecognition.major_id.is_(None),
            )
            policy_stmt = policy_stmt.where(PolicyDocument.college_id.is_(None), PolicyDocument.major_id.is_(None))
        if year is not None:
            recognition_stmt = recognition_stmt.where(CompetitionPolicyRecognition.year == year)
            policy_stmt = policy_stmt.where(PolicyDocument.year == year)

        recognition = db.execute(
            recognition_stmt.order_by(
                CompetitionPolicyRecognition.year.desc().nullslast(),
                CompetitionPolicyRecognition.confidence.desc(),
            )
        ).scalars().first()
        if recognition:
            return {
                "scope": scope_type,
                "status": recognition.recognition_status,
                "policy_document_id": recognition.policy_document_id,
                "recognition_id": recognition.id,
                "evidence_text": recognition.evidence_text,
                "needs_manual_review": recognition.needs_manual_review,
            }

        policy = db.execute(policy_stmt.order_by(PolicyDocument.year.desc().nullslast())).scalars().first()
        if policy:
            return {
                "scope": scope_type,
                "status": "not_mentioned",
                "policy_document_id": policy.id,
                "recognition_id": None,
                "evidence_text": None,
                "needs_manual_review": False,
            }

        return {
            "scope": scope_type,
            "status": "no_policy",
            "policy_document_id": None,
            "recognition_id": None,
            "evidence_text": None,
            "needs_manual_review": True,
        }

    def _reason(self, scope: str, conflict: bool) -> str:
        scope_label = {
            "major": "专业",
            "college": "学院",
            "university": "学校",
        }.get(scope, "政策")
        if conflict:
            return f"当前{scope_label}政策更具体，优先采用，同时保留较低优先级政策差异。"
        return f"当前采用{scope_label}层级政策。"
