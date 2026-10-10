"""Candidate-only ingestion and explicit, atomic field-level administration.

No method commits. Mutations use a savepoint so a caller cannot accidentally
commit part of a failed review; HTTP handlers own the outer transaction.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import math
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from app.models import (
    AdminAuditLog, BetaFeedback, Competition, CompetitionEdition,
    CompetitionFactRevision, CompetitionFactSource, CompetitionUpdateEvent,
    ReviewQueue, University, User, UserCorrectionSubmission,
)
from app.schemas.field_review import (
    FieldBulkReviewIn, FieldCandidateIn, FieldPrepareIn, FieldReviewIn,
    FieldSourceVerifyIn, FieldDetailItemIn, FieldHistoryItemIn, FieldProcessItemIn,
)


# Explicitly excludes identities, verification flags, rankings and derived data.
COMPETITION_FIELDS = {
    "name": ("赛事名称", "string"), "short_name": ("简称", "string"),
    "english_name": ("英文名称", "string"), "former_names": ("曾用名", "list"),
    "description": ("赛事介绍", "string"), "organizer": ("主办方", "string"),
    "co_organizers": ("联合主办", "list"), "guiding_organizations": ("指导单位", "list"),
    "undertakers": ("承办单位", "list"), "official_website": ("官网", "url"),
    "official_account": ("官方账号", "string"), "founded_year": ("创办年份", "integer"),
    "first_held_year": ("首届年份", "integer"), "frequency": ("举办频率", "string"),
    "edition_count": ("举办届数", "integer"), "development_history": ("发展历史", "string"),
    "history_timeline": ("历史时间线", "list"), "participation_requirements": ("参赛条件", "list"),
    "competition_process": ("赛事流程", "list"), "submission_requirements": ("提交要求", "list"),
    "award_settings": ("奖项设置", "list"), "competition_format": ("赛事形式", "string"),
    "competition_scope": ("赛事范围", "string"), "country_or_region": ("国家地区", "string"),
    "category": ("类别", "string"), "competition_level": ("赛事级别", "string"),
    "team_type": ("组队形式", "string"), "min_team_size": ("最少人数", "integer"),
    "max_team_size": ("最多人数", "integer"), "difficulty_level": ("难度", "string"),
    "target_students": ("参赛对象", "string"), "recommended_grade": ("推荐年级", "string"),
    "typical_schedule": ("常规赛程", "string"),
    "is_cross_major_supported": ("支持跨专业", "boolean"),
    "is_cross_university_supported": ("支持跨校", "boolean"),
}
EDITION_FIELDS = {
    "edition_name": ("届次名称", "string"), "host_location": ("举办地点", "string"),
    "edition_rules_url": ("届次规则链接", "url"), "edition_status": ("届次状态", "string"),
    "registration_start": ("报名开始", "datetime"),
    "registration_deadline": ("报名截止", "datetime"),
    "official_registration_deadline": ("官方报名截止", "datetime"),
    "university_registration_deadline": ("校内报名截止", "datetime"),
    "submission_deadline": ("作品提交截止", "datetime"),
    "official_submission_deadline": ("官方作品截止", "datetime"),
    "competition_start": ("比赛开始", "datetime"), "competition_end": ("比赛结束", "datetime"),
    "official_competition_date": ("官方比赛日期", "datetime"),
    "announcement_date": ("结果公布日期", "datetime"), "edition_number": ("届数", "integer"),
    "registration_fee": ("报名费用", "number"), "fee_notes": ("费用说明", "string"),
    "official_url": ("当届官网", "url"), "official_notice_url": ("官方通知", "url"),
    "official_registration_url": ("官方报名入口", "url"), "source_url": ("届次来源", "url"),
    "current_status": ("当前状态", "string"),
}
FIELDS = {"competition": COMPETITION_FIELDS, "edition": EDITION_FIELDS}
SOURCE_TYPES = [
    ("official_website", "赛事官网", 1), ("organizer_notice", "主办方通知", 2),
    ("government_document", "政府文件", 3), ("university_notice", "高校通知", 4),
    ("university_policy", "高校政策", 5), ("industry_organization", "行业组织", 6),
    ("user_submission", "用户提交", 7), ("third_party", "第三方", 8),
    ("ai_assisted", "AI 辅助", 9), ("crawler", "采集线索", 8), ("manual_entry", "人工录入", 7),
]
RELIABILITY = {"official_website": 1, "organizer_notice": 1, "government_document": 1,
    "university_notice": 2, "university_policy": 2, "industry_organization": 2,
    "user_submission": 3, "manual_entry": 3, "third_party": 4, "crawler": 5, "ai_assisted": 5}
STRUCTURED_FIELDS = {"history_timeline": FieldHistoryItemIn, "competition_process": FieldProcessItemIn,
    "participation_requirements": FieldDetailItemIn, "submission_requirements": FieldDetailItemIn,
    "award_settings": FieldDetailItemIn}
PROVENANCE_KEYS = {"source_url", "source_name", "verification_status", "verified_at", "verified_by"}
PRIVATE_REVIEW_KEYS = {"verified_by", "reviewer_id", "review_id", "candidate_id", "proposal_id", "submitter_id", "review_note"}
FINAL = {"approved", "rejected"}


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    if isinstance(value, datetime):
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _dump(value):
    return json.dumps(_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _error(message, status=422):
    raise HTTPException(status_code=status, detail=message)


def _input(model, payload):
    try:
        return model.model_validate(payload.model_dump() if hasattr(payload, "model_dump") else payload)
    except ValidationError as error:
        _error(str(error))


def _atomic(method):
    @wraps(method)
    def wrapped(db, *args, **kwargs):
        try:
            connection = db.connection()
            # Python's legacy sqlite mode does not BEGIN for a SELECT or a
            # SAVEPOINT. Releasing that savepoint would otherwise commit it,
            # defeating the caller's later rollback/failed outer commit.
            if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN")
            with db.begin_nested():
                return method(db, *args, **kwargs)
        except Exception:
            # Core CAS updates are not tracked as ORM dirty objects. A rolled
            # back savepoint must also invalidate their refreshed cached state.
            db.expire_all()
            raise
    return wrapped


def _admin(db, actor):
    if not isinstance(actor, User) or inspect(actor).identity is None:
        _error("需要有效管理员身份", 403)
    actor_id = getattr(actor, "id", None)
    # Read persisted flags, not caller-supplied booleans or identity-map values.
    actual = db.execute(select(User.id, User.is_admin, User.is_active).where(User.id == actor_id)).first()
    if actual is None or not actual.is_admin or not actual.is_active:
        _error("需要有效管理员身份", 403)
    return actual.id


def _row(db, identity):
    identity = identity.id if isinstance(identity, ReviewQueue) else identity
    cache = db.info.get("field_review_read_context")
    row = cache["rows"].get(identity) if cache is not None else db.scalar(select(ReviewQueue).where(ReviewQueue.id == identity).execution_options(populate_existing=True))
    if row is None or row.item_type != "field_candidate":
        _error("字段候选不存在", 404)
    return row


def _document(row):
    try:
        doc = json.loads(row.raw_value or "")
        if doc["schema_version"] != 1:
            raise ValueError()
        return doc
    except (ValueError, KeyError, TypeError):
        _error("候选数据格式无效", 409)


def _target(db, doc):
    cache = db.info.get("field_review_read_context")
    if cache is not None:
        competition = cache["competitions"].get(doc.get("competition_id"))
        if doc.get("competition_id") and competition is None:
            _error("赛事不存在", 404)
        if doc["entity_type"] == "competition":
            return competition
        edition = cache["editions"].get(doc.get("edition_id")) if doc.get("edition_id") else cache["years"].get((doc.get("competition_id"), doc.get("year")))
        if edition and (edition.competition_id != doc.get("competition_id") or doc.get("year") and edition.year != doc["year"]):
            _error("赛事、届次与年份不一致")
        return edition
    if doc.get("competition_id") is not None:
        competition = db.scalar(select(Competition).where(Competition.id == doc["competition_id"]).execution_options(populate_existing=True))
        if competition is None:
            _error("赛事不存在", 404)
    else:
        competition = None
    if doc["entity_type"] == "competition":
        return competition
    if doc.get("edition_id"):
        edition = db.scalar(select(CompetitionEdition).where(CompetitionEdition.id == doc["edition_id"]).execution_options(populate_existing=True))
        if edition is None:
            _error("届次不存在", 404)
        if edition.competition_id != doc.get("competition_id") or (doc.get("year") and edition.year != doc["year"]):
            _error("赛事、届次与年份不一致")
        return edition
    if doc.get("year") and competition:
        return db.scalar(select(CompetitionEdition).where(CompetitionEdition.competition_id == competition.id, CompetitionEdition.year == doc["year"]).execution_options(populate_existing=True))
    return None


def _coerce(kind, name, value):
    definitions = FIELDS[kind]
    if name not in definitions:
        _error(f"{kind} 不允许修改字段 {name}")
    model = Competition if kind == "competition" else CompetitionEdition
    column = model.__table__.columns[name]
    if value is None:
        if not column.nullable:
            _error(f"{name} 不允许为空")
        return None
    value_type = definitions[name][1]
    if value_type in {"string", "url"}:
        if not isinstance(value, str) or not value.strip():
            _error(f"{name} 必须是非空文字；删除请使用 null")
        max_length = getattr(column.type, "length", None) or 30000
        if len(value) > max_length:
            _error(f"{name} 超过长度限制")
        if value_type == "url":
            from app.schemas.field_review import FieldSourceIn
            _input(FieldSourceIn, {"source_type": "manual_entry", "source_url": value})
    elif value_type == "integer":
        if type(value) is not int or value < 0 or value > 100000:
            _error(f"{name} 必须是有效非负整数")
        if name in {"founded_year", "first_held_year"} and not 1000 <= value <= 2200:
            _error("年份超出允许范围")
    elif value_type == "number":
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            _error(f"{name} 必须是有效非负数")
    elif value_type == "boolean":
        if type(value) is not bool:
            _error(f"{name} 必须为布尔值")
    elif value_type == "list":
        if not isinstance(value, list):
            _error(f"{name} 必须是数组")
        try:
            if len(_dump(value)) > 50000:
                _error(f"{name} 内容过长")
        except (TypeError, ValueError):
            _error(f"{name} 必须包含有效 JSON 数据")
        if name in STRUCTURED_FIELDS:
            return [_input(STRUCTURED_FIELDS[name], item).model_dump(mode="json", exclude_none=True) for item in value]
        if any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in value):
            _error(f"{name} 必须是非空文字组成的数组")
    elif value_type == "datetime":
        try:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, AttributeError):
            _error(f"{name} 必须是包含时区的 ISO 日期时间")
    return value


def validate_candidate_value(entity_type, field_name, value):
    """Validate/normalize a producer value without writing any row.

    Import adapters can retain rejected legacy values in the raw description
    instead of stripping their provenance or guessing at malformed dates.
    """
    if entity_type not in FIELDS:
        _error("仅支持赛事和届次字段")
    return _json(_coerce(entity_type, field_name, value))


def _new_document(db, payload, **overrides):
    data = payload.model_dump(mode="json", exclude={"preview_token"})
    data.update({key: value for key, value in overrides.items() if value is not None})
    if data["entity_type"] == "competition" and (data.get("edition_id") or data.get("year")):
        _error("赛事本体不能携带届次身份")
    if data["entity_type"] == "edition" and (not data.get("competition_id") or (data["fields"] and not (data.get("edition_id") or data.get("year")))):
        _error("届次候选需要赛事和明确届次或年份")
    target = _target(db, data)
    if isinstance(target, CompetitionEdition):
        data["edition_id"], data["year"] = target.id, target.year
    if data.get("university_id") and db.get(University, data["university_id"]) is None:
        _error("学校不存在", 404)
    proposals = []
    for field in data.pop("fields"):
        field["candidate_value"] = _json(_coerce(data["entity_type"], field["field_name"], field["candidate_value"]))
        source = field.get("source") or {"source_type": None}
        for key in ("source_title", "source_url", "publisher", "published_at"):
            source.setdefault(key, None)
        source.update(collected_at=_json(_now()), verified_at=None, verified_by=None,
                      verification_state="UNVERIFIED" if _traceable(source) else "NO_SOURCE")
        proposals.append({**field, "source": source, "id": uuid4().hex})
    data.update(schema_version=1, revision=1, proposals=proposals, decisions={}, history=[])
    return data


def _traceable(source):
    return bool(source.get("source_url") or (source.get("source_title") and source.get("publisher")))


def _snapshot(doc, target):
    return {"id": target.id if target else None, "updated_at": _json(target.updated_at) if target else None,
            "values": {name: _json(getattr(target, name)) if target else None for name in FIELDS[doc["entity_type"]]}}


def _fact_content(name, value):
    if name in STRUCTURED_FIELDS and isinstance(value, list):
        return [{key: item for key, item in entry.items() if key not in PROVENANCE_KEYS}
                if isinstance(entry, dict) else entry for entry in value]
    return value


def _empty_value(value):
    return value is None or value == [] or value == ""


def _public_fact_value(value):
    """Historical structured values may contain private review identifiers.

    Keep exact before/after values in admin audit, but omit those identifiers
    from public fact sources, revisions, and update-event payloads.
    """
    if isinstance(value, dict):
        return {key: _public_fact_value(item) for key, item in value.items() if key not in PRIVATE_REVIEW_KEYS}
    if isinstance(value, list):
        return [_public_fact_value(item) for item in value]
    return value


def _token(row, doc, snapshot):
    # Bind same-entity/year/field evidence, not unrelated queue activity.
    db = inspect(row).session
    names = {p["field_name"] for p in doc["proposals"]}
    external = []
    if db is not None and names and _identity(doc):
        cache = db.info.get("field_review_read_context")
        if cache is not None:
            external = [p for name, proposals in cache["external"].get(_identity(doc), {}).items()
                        if name in names for p in proposals if p["candidate_id"] != row.id]
        else:
            for other in db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate",
                    ReviewQueue.id != row.id, ReviewQueue.competition_id == doc["competition_id"],
                    ReviewQueue.status.in_(["pending", "partially_approved"]))):
                other_doc = _document(other)
                if _identity(other_doc) != _identity(doc):
                    continue
                for p in other_doc["proposals"]:
                    if p["field_name"] in names and other_doc["decisions"].get(p["field_name"], {}).get("action") not in FINAL:
                        external.append({"candidate_id": other.id, "proposal_id": p["id"],
                            "candidate_value": p["candidate_value"], "source": p["source"]})
    external.sort(key=lambda p: (p["candidate_id"], p["proposal_id"]))
    return hashlib.sha256(_dump({"id": row.id, "raw": row.raw_value, "status": row.status,
        "origin_source_url": row.source_url, "fact": snapshot, "external": external}).encode()).hexdigest()


def _assert_preview(row, doc, snapshot, token):
    if _token(row, doc, snapshot) != token:
        _error("预览已过期，请刷新后重新确认", 409)


def _claim(db, row):
    changed = db.execute(update(ReviewQueue).where(ReviewQueue.id == row.id, ReviewQueue.raw_value == row.raw_value,
        ReviewQueue.status == row.status, ReviewQueue.source_url == row.source_url)
        .values(updated_at=_now()).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        _error("候选已被其他管理员处理，请刷新", 409)


def _group(doc):
    grouped = defaultdict(list)
    for proposal in doc["proposals"]:
        grouped[proposal["field_name"]].append(proposal)
    return grouped


def _identity(doc):
    if not doc.get("competition_id"):
        return None
    return (doc["entity_type"], doc["competition_id"], doc.get("year") if doc["entity_type"] == "edition" else None)


def _history(db, row, doc, admin_id, action, note, before, after, decisions=None, sources=None):
    entry = {"action": action, "reviewer_id": admin_id, "reviewed_at": _json(_now()), "note": note,
             "decisions": decisions or [], "before": before, "after": after, "sources": sources or []}
    doc["history"].append(entry)
    db.add(AdminAuditLog(admin_id=admin_id, action=action, object_type="field_candidate", object_id=row.id,
        before=before, after={**after, "review": entry}, created_at=_now()))


def _save(db, row, doc):
    doc["revision"] += 1
    row.raw_value = _dump(doc)
    row.competition_id = doc.get("competition_id")
    db.flush()


class FieldReviewService:
    @staticmethod
    def config():
        return {"fields": {kind: [{"field_name": key, "display_name": label, "value_type": type_} for key, (label, type_) in fields.items()] for kind, fields in FIELDS.items()},
                "source_types": [{"value": key, "label": label, "priority": priority} for key, label, priority in SOURCE_TYPES]}

    @staticmethod
    def create_candidate(db: Session, payload, *, submitter_id=None, origin=None, origin_id=None):
        payload = _input(FieldCandidateIn, payload)
        doc = _new_document(db, payload, submitter_id=submitter_id, origin=origin, origin_id=origin_id)
        doc.setdefault("submitter_id", None)
        row = ReviewQueue(item_type="field_candidate", item_id=doc.get("origin_id"), competition_id=doc.get("competition_id"),
            university_id=doc.get("university_id"), status="pending", reason=doc["title"], raw_value=_dump(doc),
            evidence_text=doc.get("description"))
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def detail(db: Session, row_or_id, *, source_limit=50):
        row = _row(db, row_or_id)
        doc = _document(row)
        target = _target(db, doc)
        snapshot = _snapshot(doc, target)
        external = defaultdict(list)
        cache = db.info.get("field_review_read_context")
        summary = bool(cache and cache.get("summary_mode"))
        if cache is not None:
            for name, proposals in cache["external"].get(_identity(doc), {}).items():
                external[name] = [p for p in proposals if p["candidate_id"] != row.id]
        elif _identity(doc):
            for other in db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate", ReviewQueue.id != row.id,
                    ReviewQueue.competition_id == doc["competition_id"], ReviewQueue.status.in_(["pending", "partially_approved"]))):
                other_doc = _document(other)
                if _identity(other_doc) != _identity(doc):
                    continue
                for item in other_doc["proposals"]:
                    if other_doc["decisions"].get(item["field_name"], {}).get("action") not in FINAL:
                        external[item["field_name"]].append({"candidate_id": other.id, "proposal_id": item["id"], "candidate_value": item["candidate_value"], "source": item["source"]})
        context = doc.get("collection_context") or {}
        flags = set(context.get("flags", []))
        if context and not doc["proposals"] and row.status == "pending":
            flags.add("UNVERIFIED" if row.source_url else "NO_SOURCE")
        fields = []
        eligible = []
        for name, proposals in _group(doc).items():
            decision = doc["decisions"].get(name, {})
            selected = next((p for p in proposals if p["id"] == decision.get("proposal_id")), proposals[0])
            current = snapshot["values"][name]
            value = selected["candidate_value"]
            pending = decision.get("action") not in FINAL
            alternatives = external[name] if pending else []
            conflict = pending and len({_dump(p["candidate_value"]) for p in proposals + alternatives}) > 1
            if conflict:
                flags.add("CONFLICT")
            for item in proposals if pending else []:
                if item["source"]["verification_state"] in {"UNVERIFIED", "NO_SOURCE"}:
                    flags.add(item["source"]["verification_state"])
            changed = _fact_content(name, current) != _fact_content(name, value)
            change_type = "unchanged" if not changed else "delete" if _empty_value(value) else "add" if _empty_value(current) else "modify"
            current_sources = cache["facts"].get((doc.get("competition_id"), target.id if isinstance(target, CompetitionEdition) else None, name), []) if cache is not None else list(db.scalars(select(CompetitionFactSource).where(
                CompetitionFactSource.competition_id == doc.get("competition_id"),
                CompetitionFactSource.competition_edition_id == (target.id if isinstance(target, CompetitionEdition) else None),
                CompetitionFactSource.field_name == name).order_by(CompetitionFactSource.id.desc()))) if target else []
            last_verified = next((s.last_verified_at for s in current_sources if s.fact_value == current), None)
            fields.append({"field_name": name, "display_name": FIELDS[doc["entity_type"]][name][0],
                "current_value": current, "candidate_value": value, "changed": changed, "change_type": change_type,
                "verification_state": selected["source"]["verification_state"], "source": selected["source"],
                "source_url": selected["source"]["source_url"], "source_type": selected["source"]["source_type"],
                "confidence": selected.get("confidence"), "last_verified_at": _json(last_verified),
                "decision": decision.get("action", "pending"), "proposals": proposals, "conflicts": alternatives})
            if target and pending and not conflict and len(proposals) == 1 and current is None and value is not None and selected["source"]["verification_state"] == "VERIFIED":
                eligible.append(name)
        # The UI's one-click set must itself satisfy the same-source restriction.
        identities = {_dump({k: f["source"].get(k) for k in ("source_type", "source_url", "source_title", "publisher")}) for f in fields if f["field_name"] in eligible}
        if len(identities) > 1:
            eligible = []
        competition = (cache["competitions"].get(doc.get("competition_id")) if cache is not None else db.get(Competition, doc.get("competition_id"))) if doc.get("competition_id") else None
        result = {"id": row.id, **{key: doc.get(key) for key in ("title", "description", "entity_type", "competition_id", "edition_id", "year", "university_id", "submitter_id", "origin", "origin_id", "origin_kind")},
                "origin_source_url": row.source_url,
                "collection_context": context or None,
                "edition_id": target.id if isinstance(target, CompetitionEdition) else doc.get("edition_id"),
                "competition_name": competition.name if competition else None, "status": row.status, "created_at": _json(row.created_at),
                "preview_token": "" if summary else _token(row, doc, snapshot), "fields": fields, "flags": sorted(flags), "history": doc["history"], "bulk_eligible_fields": eligible}
        from app.services.review_queue_query import classification, timeline, source_observations
        observations = {} if summary else source_observations(db)
        fields = fields if summary else deepcopy(fields)
        result["fields"] = fields
        for field in fields:
            for proposal in ([] if summary else field["proposals"] + field["conflicts"]):
                proposal["source"]["availability"] = observations.get(proposal["source"].get("source_url"), {"status": "UNKNOWN", "checked_at": None})
            field["timeline"] = timeline(field, candidate_id=row.id, entity_type=doc["entity_type"]) if cache is None else []
        if context.get("kind") == "school_mapping":
            from app.services.school_relation_review_service import SchoolRelationReviewService
            relation = SchoolRelationReviewService.detail(db, row.id)
            relation["source"]["availability"] = observations.get(relation["source"].get("source_url"), {"status": "UNKNOWN", "checked_at": None})
            result["relation"] = relation
            result["flags"] = sorted(set(result["flags"]) | set(relation["flags"]))
        classification(result, target_exists=target is not None)
        from app.services.document_policy_service import classification_for
        result["document_classification"] = classification_for(doc, row)
        if result["document_classification"].get("risk_level") == "HIGH_RISK":
            result["risk_level"] = "HIGH_RISK"
            result["flags"] = sorted((set(result["flags"]) - {"LOW_RISK"}) | {"HIGH_RISK"})
            result["risk_reasons"] = sorted(set(result["risk_reasons"]) | {"DOCUMENT_UPDATE_REVIEW"})
            result["low_risk_fields"] = []
            result["bulk_eligible_fields"] = []
        for field in fields:
            field["timeline_total"] = len(field["timeline"])
            if source_limit is not None:
                field["timeline"] = field["timeline"][:source_limit]
                field["conflicts"] = field["conflicts"][:source_limit]
        return result

    @staticmethod
    def list_candidates(db: Session, *, status=None, flag=None, entity_type=None, competition_id=None,
                        university_id=None, source_type=None, submitter_id=None, created_from=None, created_to=None,
                        risk=None, search=None, relation_type=None, sort="newest", limit=50, offset=0):
        from app.services.review_queue_query import list_candidates
        return list_candidates(db, status=status, flag=flag, entity_type=entity_type, competition_id=competition_id,
            university_id=university_id, source_type=source_type, submitter_id=submitter_id,
            created_from=created_from, created_to=created_to, risk=risk, search=search,
            relation_type=relation_type, sort=sort, limit=limit, offset=offset)

    @staticmethod
    @_atomic
    def reject_unstructured(db: Session, identity, payload, *, admin):
        """Close invalid free text without inventing or approving any fields."""
        admin_id = _admin(db, admin)
        payload = _input(FieldSourceVerifyIn, payload)
        row = _row(db, identity)
        doc = _document(row)
        snapshot = _snapshot(doc, _target(db, doc))
        _assert_preview(row, doc, snapshot, payload.preview_token)
        if doc["proposals"] or row.status != "pending":
            _error("仅尚未结构化的待处理候选可以直接拒绝", 409)
        evidence = {key: doc.get(key) for key in ("title", "description", "origin", "origin_id", "origin_kind", "submitter_id")}
        evidence["origin_source_url"] = row.source_url
        before = {**snapshot, "status": row.status, "candidate": evidence}
        _claim(db, row)
        row.status = "rejected"
        row.reviewed_at, row.reviewer_notes = _now(), payload.note
        _history(db, row, doc, admin_id, "field_reject_unstructured", payload.note, before,
            {**snapshot, "status": "rejected", "candidate": evidence},
            decisions=[{"action": "reject_unstructured"}], sources=[{
                "source_url": row.source_url, "verification_state": "UNVERIFIED" if row.source_url else "NO_SOURCE",
                "verified_by": None, "verified_at": None,
            }])
        FieldReviewService._sync_origin(db, row, doc, admin_id, payload.note)
        _save(db, row, doc)
        from app.services.review_telemetry_service import ReviewTelemetryService
        ReviewTelemetryService.complete(db, row.id, admin_id, "reject")
        return FieldReviewService.detail(db, row)

    @staticmethod
    @_atomic
    def prepare(db: Session, identity, payload, *, admin):
        admin_id = _admin(db, admin)
        payload = _input(FieldPrepareIn, payload)
        row = _row(db, identity)
        old = _document(row)
        if (old.get("collection_context") or {}).get("kind") == "school_mapping":
            _error("学校映射材料不能转成赛事本体字段；请保留待审或拒绝材料", 409)
        before = _snapshot(old, _target(db, old))
        _assert_preview(row, old, before, payload.preview_token)
        if old["proposals"] or row.status != "pending":
            _error("只有尚未结构化的待处理候选可以准备字段", 409)
        if not payload.fields:
            _error("准备候选必须提供结构化字段")
        doc = _new_document(db, payload)
        for key in ("submitter_id", "origin", "origin_id", "origin_kind", "collection_context", "collection_key"):
            doc[key] = old.get(key)
        doc["description"] = payload.description or old.get("description")
        doc["history"] = old["history"]
        doc["revision"] = old["revision"]
        _claim(db, row)
        _history(db, row, doc, admin_id, "field_prepare", "自由文本结构化", before, _snapshot(doc, _target(db, doc)), sources=doc["proposals"])
        row.reason, row.university_id = doc["title"], doc.get("university_id")
        _save(db, row, doc)
        return FieldReviewService.detail(db, row)

    @staticmethod
    @_atomic
    def verify_source(db: Session, identity, proposal_id, payload, *, admin):
        admin_id = _admin(db, admin)
        payload = _input(FieldSourceVerifyIn, payload)
        row = _row(db, identity)
        doc = _document(row)
        snapshot = _snapshot(doc, _target(db, doc))
        _assert_preview(row, doc, snapshot, payload.preview_token)
        proposal = next((p for p in doc["proposals"] if p["id"] == proposal_id), None)
        if proposal is None:
            _error("候选来源不存在", 404)
        if doc["decisions"].get(proposal["field_name"], {}).get("action") in FINAL:
            _error("字段已处理，不能重复核验", 409)
        source = proposal["source"]
        if not _traceable(source):
            _error("来源缺失：需链接或明确的资料标题与发布单位")
        if source["verification_state"] == "VERIFIED":
            _error("来源已核验", 409)
        before = deepcopy(source)
        _claim(db, row)
        source.update(verification_state="VERIFIED", verified_by=admin_id, verified_at=_json(_now()))
        _history(db, row, doc, admin_id, "field_source_verify", payload.note, {"source": before}, {"source": deepcopy(source)}, sources=[deepcopy(proposal)])
        _save(db, row, doc)
        return FieldReviewService.detail(db, row)

    @staticmethod
    @_atomic
    def review(db: Session, identity, payload, *, admin):
        admin_id = _admin(db, admin)
        payload = _input(FieldReviewIn, payload)
        row = _row(db, identity)
        doc = _document(row)
        target = _target(db, doc)
        before = _snapshot(doc, target)
        _assert_preview(row, doc, before, payload.preview_token)
        if isinstance(target, CompetitionEdition):
            # A different candidate may have created this competition/year
            # since submission. Refresh binds all provenance to that edition.
            doc["edition_id"], doc["year"] = target.id, target.year
        grouped = _group(doc)
        if not grouped or all(doc["decisions"].get(name, {}).get("action") in FINAL for name in grouped):
            _error("候选尚未结构化或已完成审核", 409)
        names = [d.field_name for d in payload.decisions]
        if len(set(names)) != len(names):
            _error("同一字段不能重复处理")
        accepted = {}
        sources = {}
        for decision in payload.decisions:
            name = decision.field_name
            if name not in grouped:
                _error(f"候选中没有字段 {name}")
            if doc["decisions"].get(name, {}).get("action") in FINAL:
                _error(f"字段 {name} 已处理", 409)
            if decision.action != "approve":
                continue
            selected = next((p for p in grouped[name] if p["id"] == decision.proposal_id), None)
            if selected is None:
                _error("批准时必须明确选择此字段的候选来源")
            source = selected["source"]
            if source["verification_state"] != "VERIFIED" or not source.get("verified_by") or not source.get("verified_at"):
                _error("来源尚未经过管理员核验")
            if _empty_value(selected["candidate_value"]) and not _empty_value(before["values"][name]) and not decision.confirm_delete:
                _error("删除非空值必须单独确认")
            accepted[name] = _coerce(doc["entity_type"], name, selected["candidate_value"])
            sources[name] = deepcopy(source)
            if name in STRUCTURED_FIELDS and accepted[name] is not None:
                # Candidate content stays unchanged. Approved structured facts
                # receive the chosen source and verification time here. Real
                # verifier identities remain in admin-only source/history.
                accepted[name] = [{**entry, "source_url": source["source_url"], "source_name": source["source_title"],
                    "verification_status": "verified_manual", "verified_at": source["verified_at"]}
                    for entry in accepted[name]]
        if target is None and accepted:
            if not any(value is not None for value in accepted.values()):
                _error("新实体至少需要一个已批准的非空字段")
            required = {"name"} if doc["entity_type"] == "competition" else set()
            if not all(accepted.get(name) for name in required):
                _error("新实体必须同时批准必需字段：" + "、".join(sorted(required)))
            if doc["entity_type"] == "edition" and not doc.get("year"):
                _error("创建届次必须明确年份")
        _claim(db, row)
        if accepted:
            from app.database.review_guard import reviewed_write
            with reviewed_write(db):
                if target is None:
                    if doc["entity_type"] == "competition":
                        target = Competition(**accepted, verification_status="verified_manual", is_official_verified=False)
                    else:
                        target = CompetitionEdition(competition_id=doc["competition_id"], year=doc["year"], **accepted,
                            verification_status="verified_manual", is_verified=True)
                    db.add(target)
                    db.flush()
                    if isinstance(target, Competition):
                        doc["competition_id"] = target.id
                    else:
                        doc["edition_id"] = target.id
                else:
                    model = type(target)
                    conditions = [model.id == target.id, model.updated_at == target.updated_at]
                    for name in accepted:
                        if FIELDS[doc["entity_type"]][name][1] != "list":
                            conditions.append(getattr(model, name) == getattr(target, name))
                    changed = db.execute(update(model).where(*conditions).values(**accepted, updated_at=_now()).execution_options(synchronize_session=False))
                    if changed.rowcount != 1:
                        _error("正式值已变化，请刷新预览", 409)
                    db.refresh(target)
                db.flush()
            for name, value in accepted.items():
                FieldReviewService._record_fact(db, doc, name, before["values"][name], _json(value), sources[name])
        for decision in payload.decisions:
            doc["decisions"][decision.field_name] = {**decision.model_dump(), "action": {"approve": "approved", "reject": "rejected", "defer": "deferred"}[decision.action],
                "reviewer_id": admin_id, "reviewed_at": _json(_now()), "note": payload.note}
        states = [doc["decisions"].get(name, {}).get("action", "pending") for name in grouped]
        row.status = "approved" if all(s == "approved" for s in states) else "rejected" if all(s == "rejected" for s in states) else "partially_approved" if "approved" in states else "pending"
        row.reviewed_at, row.reviewer_notes = _now(), payload.note
        after = _snapshot(doc, target)
        _history(db, row, doc, admin_id, "field_review", payload.note, before, after,
            decisions=[d.model_dump() for d in payload.decisions],
            sources=[{"field_name": name, "proposal_id": p["id"], "candidate_value": p["candidate_value"], **deepcopy(p["source"])}
                     for name in names for p in grouped[name]])
        FieldReviewService._sync_origin(db, row, doc, admin_id, payload.note)
        _save(db, row, doc)
        if any(d.action in {"approve", "reject"} for d in payload.decisions):
            from app.services.review_telemetry_service import ReviewTelemetryService
            ReviewTelemetryService.complete(db, row.id, admin_id, "approve" if accepted else "reject")
        return FieldReviewService.detail(db, row)

    @staticmethod
    def _record_fact(db, doc, name, old, new, source):
        now = _now()
        # Offline evidence is identified by title/publisher and the audit's
        # review ID. An absent external URL must stay absent in public facts.
        url = source["source_url"] or ""
        edition_id = doc.get("edition_id") if doc["entity_type"] == "edition" else None
        fact = db.scalar(select(CompetitionFactSource).where(CompetitionFactSource.competition_id == doc["competition_id"],
            CompetitionFactSource.competition_edition_id == edition_id, CompetitionFactSource.field_name == name,
            CompetitionFactSource.source_url == url).order_by(CompetitionFactSource.id.desc()).limit(1))
        old, new = _public_fact_value(old), _public_fact_value(new)
        public_note = "来源经管理员人工核验后更新。"
        values = dict(fact_value=new, source_type=source["source_type"], source_name=source["source_title"],
            reliability_tier=RELIABILITY.get(source["source_type"], 5), is_official=False, verification_status="verified_manual",
            published_at=datetime.fromisoformat(source["published_at"]) if source.get("published_at") else None,
            observed_at=datetime.fromisoformat(source["collected_at"]), last_verified_at=datetime.fromisoformat(source["verified_at"]), notes=public_note)
        if fact is None:
            fact = CompetitionFactSource(competition_id=doc["competition_id"], competition_edition_id=edition_id, field_name=name, source_url=url, **values)
            db.add(fact)
        else:
            for key, value in values.items():
                setattr(fact, key, value)
        db.add(CompetitionFactRevision(competition_id=doc["competition_id"], competition_edition_id=edition_id,
            field_name=name, old_value=old, new_value=new, changed_at=now, source_url=url,
            source_name=source["source_title"], verification_status="verified_manual"))
        if old != new:
            from app.services.notification_service import EVENT_TYPE_BY_FIELD, NotificationService
            update_event = CompetitionUpdateEvent(competition_id=doc["competition_id"], competition_edition_id=edition_id,
                event_type=EVENT_TYPE_BY_FIELD.get(name, "field_updated"), field_name=name, old_value=old, new_value=new,
                source_url=url, source_name=source["source_title"], changed_at=now, observed_at=now, notes=public_note,
                metadata_json={"verification_status": "verified_manual"})
            db.add(update_event)
            db.flush()
            if edition_id and name in EVENT_TYPE_BY_FIELD:
                NotificationService()._notify_event(db, update_event)

    @staticmethod
    def _sync_origin(db, row, doc, admin_id, note):
        origin_id, kind = doc.get("origin_id"), doc.get("origin_kind")
        if not origin_id or not kind:
            return
        source = db.get(UserCorrectionSubmission if kind == "user_correction" else BetaFeedback, origin_id)
        if source is None:
            _error("关联提交已不存在", 409)
        source.status = row.status
        if kind == "user_correction":
            source.reviewed_by, source.reviewed_at, source.review_note = admin_id, _now(), note
        for legacy in db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == kind, ReviewQueue.item_id == origin_id)):
            legacy.status, legacy.reviewed_at, legacy.reviewer_notes = row.status, _now(), note

    @staticmethod
    def bulk_preview(db: Session, payload, *, admin):
        from app.services.review_bulk_service import preview
        return preview(db, payload, admin=admin)

    @staticmethod
    @_atomic
    def bulk_review(db: Session, payload, *, admin):
        from app.services.review_bulk_service import execute
        return execute(db, payload, admin=admin)
