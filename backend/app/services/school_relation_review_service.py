"""Explicit administrator review for existing school_mapping candidates.

No schema changes, entity-field writes, source auto-verification, or commits.
A school-row lock serializes relation creation across distinct candidates.
"""
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
import hashlib
import re

from sqlalchemy import select, inspect, or_
from app.database.review_guard import reviewed_write
from app.models import (Competition, CompetitionAlias, CompetitionEdition, University, College, Major, ReviewQueue,
    UniversityCompetitionEditionRelation as Relation, PolicyDocument, CompetitionPolicyRecognition as Recognition)
from app.schemas.field_review import FieldSourceIn
from app.schemas.school_relation_review import (
    SchoolRelationPrepareIn, SchoolRelationSourceVerifyIn, SchoolRelationReviewIn)

POLICY_TYPES = {"policy_recognition", "award_policy"}
NOTICE_TYPES = {"registration_notice", "organization_notice", "selection_notice",
    "recommendation_notice", "repost", "other", "competition_notice"}
SCOPE_FIELDS = ("scope_type", "college_id", "major_id", "student_scope", "applicability_text",
    "effective_from", "effective_until", "validity_note", "current_validity_confirmed",
    "recognition_evidence", "revoked")
READ_CONTEXT_KEY = "field_review_read_context"
ENTITY_CACHE_KEYS = {University: "universities", Competition: "competitions", CompetitionEdition: "editions",
    College: "colleges", Major: "majors"}


def _fr():
    # Imported lazily because the parent field-review detail delegates here.
    from app.services import field_review_service
    return field_review_service


def _atomic(method):
    @wraps(method)
    def wrapped(db, *args, **kwargs):
        # A mutation must never inherit a list/statistics preview, even if a
        # caller accidentally invokes it inside a read-only preload scope.
        db.info.pop(READ_CONTEXT_KEY, None)
        return _fr()._atomic(method)(db, *args, **kwargs)
    return wrapped


def _date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        if len(value) == 10:
            value += "T00:00:00+08:00"
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _same_date(left, right):
    try:
        return _date(left) == _date(right)
    except (TypeError, ValueError):
        return False


def _precision(value):
    if isinstance(value, datetime):
        return "second"
    text = str(value or "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "date"
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", text):
        return "second"
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", text):
        return "minute"
    return "unknown"


def _registration_deadline(values):
    raw = values["school_deadline"]
    # Generic legacy competition_notice does not establish registration semantics.
    if values["notice_type"] != "registration_notice" or _precision(raw) not in {"minute", "second"}:
        return None
    # Do not silently interpret an unstated timezone.
    parsed = raw if isinstance(raw, datetime) else datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.utcoffset() is not None else None


def _public_source(source):
    fields = {"source_type", "source_url", "source_title", "publisher", "published_at", "collected_at",
        "access_status", "source_failure_reason", "verification_state", "verified_at"}
    result = {key: deepcopy(value) for key, value in source.items() if key in fields}
    result["published_at_precision"] = _precision(source.get("published_at"))
    return result


def _verification_fingerprint(row, doc):
    evidence = {"context": doc["collection_context"], "source_url": row.source_url,
        "competition_id": doc.get("competition_id"), "university_id": doc.get("university_id"),
        "prepared": (doc.get("relation_review") or {}).get("prepared")}
    return hashlib.sha256(_fr()._dump(evidence).encode()).hexdigest()


def _load(db, identity, cache=None):
    key = identity.id if isinstance(identity, ReviewQueue) else identity
    row = cache["rows"].get(key) if cache is not None else _fr()._row(db, key)
    if row is None:
        _fr()._error("学校关系候选不存在", 404)
    doc = cache["documents"][key] if cache is not None else _fr()._document(row)
    if (doc.get("collection_context") or {}).get("kind") != "school_mapping" or doc["proposals"]:
        _fr()._error("候选不是独立学校关系材料", 409)
    return row, doc


def _lookup(db, model, key, cache=None):
    if not key:
        return None
    return cache[ENTITY_CACHE_KEYS[model]].get(key) if cache is not None else db.get(model, key)


def _read_cache(db):
    parent = db.info.get(READ_CONTEXT_KEY)
    if parent is None:
        return None
    if "school_relations" in parent:
        return parent["school_relations"]
    # The field queue's pending set excludes deferred candidates; those still
    # contain unresolved relation evidence and must participate in conflicts.
    rows = dict(parent["rows"])
    deferred = db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate",
        ReviewQueue.status == "deferred").order_by(ReviewQueue.id))
    rows.update((r.id, r) for r in deferred)
    documents = {key: parent["documents"].get(key) or _fr()._document(row) for key, row in rows.items()}
    school_docs = [d for d in documents.values() if (d.get("collection_context") or {}).get("kind") == "school_mapping"]
    cache = {"rows": rows, "documents": documents, "values": {}, "aliases": defaultdict(list),
        "notices": defaultdict(list), "policies": defaultdict(list), "peers": defaultdict(list)}
    for model, name in ENTITY_CACHE_KEYS.items():
        cache[name] = dict(parent.get(name, {}))
    needed = defaultdict(set)
    for doc in school_docs:
        context = doc["collection_context"]
        prepared = (doc.get("relation_review") or {}).get("prepared") or {}
        for model, field in ((University, "university_id"), (Competition, "competition_id"),
                (CompetitionEdition, "edition_id"), (College, "college_id"), (Major, "major_id")):
            value = prepared.get(field) or doc.get(field) or context.get(field)
            if value:
                needed[model].add(value)
    for model, name in ENTITY_CACHE_KEYS.items():
        missing = needed[model] - set(cache[name])
        if missing:
            cache[name].update((r.id, r) for r in db.scalars(select(model).where(model.id.in_(missing))))
    university_ids = set(cache["universities"])
    for relation in db.scalars(select(Relation).where(Relation.university_id.in_(university_ids)).order_by(Relation.id)):
        cache["notices"][(relation.university_id, relation.competition_edition_id)].append(
            {"record_type": "notice", **_record(relation)})
    for recognition, document in db.execute(select(Recognition, PolicyDocument).join(PolicyDocument).where(
            Recognition.university_id.in_(university_ids)).order_by(Recognition.id)):
        cache["policies"][(recognition.university_id, recognition.competition_id, recognition.usage_type)].append(
            {"record_type": "policy", **_record(recognition), "policy_document": _record(document)})
    for cid, alias in db.execute(select(CompetitionAlias.competition_id, CompetitionAlias.alias).where(
            CompetitionAlias.competition_id.in_(cache["competitions"]), CompetitionAlias.is_verified.is_(True))):
        cache["aliases"][cid].append(alias)
    for row in sorted(rows.values(), key=lambda r: r.id):
        if row.status in {"pending", "deferred", "partially_approved"} and (
                documents[row.id].get("collection_context") or {}).get("kind") == "school_mapping":
            cache["peers"][(row.university_id, row.competition_id)].append(row)
    parent["school_relations"] = cache
    return cache


def _values(db, row, doc, cache=None):
    if cache is not None and row.id in cache["values"]:
        return cache["values"][row.id]
    context = doc["collection_context"]
    state = doc.get("relation_review") or {}
    prepared = deepcopy(state.get("prepared") or {})
    prepared.setdefault("recognition_evidence", context.get("recognition_evidence"))
    prepared.setdefault("current_validity_confirmed", False)
    prepared.setdefault("revoked", bool(context.get("revoked") or context.get("is_revoked")))
    university_id = prepared.get("university_id") or doc.get("university_id") or context.get("university_id")
    competition_id = prepared.get("competition_id") or doc.get("competition_id")
    year = prepared.get("year", context.get("year"))
    edition_id = prepared.get("edition_id", context.get("edition_id"))
    school = _lookup(db, University, university_id, cache)
    competition = _lookup(db, Competition, competition_id, cache)
    notice_type = context.get("notice_type")
    kind = "policy" if notice_type in POLICY_TYPES else "notice"
    if kind == "notice" and school and competition and year is not None and not edition_id:
        editions = [e for e in cache["editions"].values() if e.competition_id == competition_id and e.year == year] if cache is not None else list(db.scalars(select(CompetitionEdition).where(
            CompetitionEdition.competition_id == competition_id, CompetitionEdition.year == year)))
        if len(editions) == 1:
            edition_id = editions[0].id
    verification = state.get("source_verification") or {}
    if verification.get("evidence_fingerprint") != _verification_fingerprint(row, doc):
        verification = {}
    source = dict(source_type=context.get("source_type"), source_url=context.get("source_url") or row.source_url,
        source_title=context.get("source_title"), publisher=context.get("publisher"),
        published_at=context.get("published_at"), collected_at=context.get("accessed_at"),
        access_status=context.get("access_status"), source_failure_reason=context.get("source_failure_reason"),
        verification_state=verification.get("verification_state", "UNVERIFIED"),
        verified_at=verification.get("verified_at"), verified_by=verification.get("verified_by"))
    result = dict(candidate_id=row.id, status=row.status, relation_kind=kind, university_id=university_id,
        school_name=school.name if school else context.get("school_name"), competition_id=competition_id,
        competition_name=competition.name if competition else None, notice_type=notice_type,
        year=year, edition_id=edition_id if kind == "notice" else None, source=source, prepared=prepared,
        school_deadline=context.get("school_deadline"), decision=state.get("decision"))
    if cache is not None:
        cache["values"][row.id] = result
    return result


def _record(row):
    return _fr()._json({a.key: getattr(row, a.key) for a in inspect(row).mapper.column_attrs})


def _scope(values):
    # Explanatory review notes are preserved but are not a change of relation.
    fields = [k for k in SCOPE_FIELDS if k != "validity_note"]
    return {k: values["prepared"].get(k) for k in fields}


def _overlaps(left, right):
    a, b = _date(left.get("effective_from")), _date(left.get("effective_until"))
    c, d = _date(right.get("effective_from")), _date(right.get("effective_until"))
    return not ((b and c and b < c) or (d and a and d < a))


def _existing(db, values, cache=None):
    if not values["university_id"] or not values["competition_id"]:
        return []
    if values["relation_kind"] == "notice":
        if not values["edition_id"]:
            return []
        if cache is not None:
            return [r for r in cache["notices"][(values["university_id"], values["edition_id"])] if
                r["notice_type"] == values["notice_type"] or r["internal_notice_url"] == values["source"]["source_url"]]
        rows = db.scalars(select(Relation).where(Relation.university_id == values["university_id"],
            Relation.competition_edition_id == values["edition_id"],
            or_(Relation.notice_type == values["notice_type"],
                Relation.internal_notice_url == values["source"]["source_url"])).order_by(Relation.id)
            .execution_options(populate_existing=True))
        return [{"record_type": "notice", **_record(r)} for r in rows]
    if cache is not None:
        return cache["policies"][(values["university_id"], values["competition_id"], values["notice_type"])]
    records = db.execute(select(Recognition, PolicyDocument).join(PolicyDocument).where(
        Recognition.university_id == values["university_id"],
        Recognition.competition_id == values["competition_id"],
        Recognition.usage_type == values["notice_type"]).order_by(Recognition.id)
        .execution_options(populate_existing=True)).all()
    return [{"record_type": "policy", **_record(r), "policy_document": _record(p)} for r, p in records]


def _snapshot(db, row, doc, cache=None):
    values = _values(db, row, doc, cache)
    records = _existing(db, values, cache)
    peers = []
    # Include unreviewed competing evidence in the preview token as well.
    if values["university_id"] and values["competition_id"]:
        others = cache["peers"][(values["university_id"], values["competition_id"])] if cache is not None else db.scalars(select(ReviewQueue).where(ReviewQueue.item_type == "field_candidate",
                ReviewQueue.id != row.id, ReviewQueue.university_id == values["university_id"],
                ReviewQueue.competition_id == values["competition_id"],
                ReviewQueue.status.in_(["pending", "deferred", "partially_approved"])).order_by(ReviewQueue.id))
        for other in others:
            if other.id == row.id:
                continue
            other_doc = cache["documents"][other.id] if cache is not None else _fr()._document(other)
            if (other_doc.get("collection_context") or {}).get("kind") != "school_mapping":
                continue
            peer = _values(db, other, other_doc, cache)
            if peer["notice_type"] == values["notice_type"] and (
                    values["relation_kind"] == "policy" or peer["year"] == values["year"]):
                peers.append({"id": other.id, "values": peer,
                    "revision_hash": hashlib.sha256(other.raw_value.encode()).hexdigest()})
    # Official identities are also CAS inputs: a renamed/moved edition is stale.
    identities = {}
    for name, model, key in (("university", University, "university_id"),
                            ("competition", Competition, "competition_id"),
                            ("edition", CompetitionEdition, "edition_id")):
        target = _lookup(db, model, values[key], cache) if cache is not None else db.scalar(select(model).where(model.id == values[key]).execution_options(populate_existing=True)) if values[key] else None
        identities[name] = _record(target) if target else None
    return {"values": values, "existing_records": records, "peers": peers, "identities": identities}


def _policy_reasons(db, values, cache=None):
    p = values["prepared"]
    missing = [key for key in ("scope_type", "student_scope", "applicability_text",
        "validity_note", "recognition_evidence") if not p.get(key)]
    reasons = ["政策需明确：" + "、".join(missing)] if missing else []
    if p.get("recognition_evidence") and values["competition_id"]:
        from app.services.real_data_pilot_service import _name
        competition = _lookup(db, Competition, values["competition_id"], cache)
        names = [competition.name, competition.short_name, competition.english_name,
                 *(competition.former_names or [])] if competition else []
        names.extend(cache["aliases"][values["competition_id"]] if cache is not None else db.scalars(select(CompetitionAlias.alias).where(
            CompetitionAlias.competition_id == values["competition_id"], CompetitionAlias.is_verified.is_(True))))
        excerpt = _name(p["recognition_evidence"])
        if not any(len(_name(name)) >= 2 and _name(name) in excerpt for name in names if name):
            reasons.append("认定条款必须明确写出该赛事名称或已确认别名，通用参赛政策不是具体赛事认定")
    if values["source"]["source_type"] != "university_policy":
        reasons.append("政策必须有学校正式政策来源，不能由报名通知转换")
    if p.get("scope_type") in {"college", "major"} and p.get("college_id"):
        college = _lookup(db, College, p["college_id"], cache)
        if college is None or college.university_id != values["university_id"]:
            reasons.append("学院不属于对应学校")
    if p.get("scope_type") == "college" and not p.get("college_id"):
        reasons.append("学院范围需要明确学院")
    if p.get("scope_type") == "major" and (not p.get("major_id") or _lookup(db, Major, p["major_id"], cache) is None):
        reasons.append("专业范围需要明确专业")
    if p.get("scope_type") == "university" and (p.get("college_id") or p.get("major_id")):
        reasons.append("校级范围不能同时指定院系或专业")
    if p.get("scope_type") == "college" and p.get("major_id"):
        reasons.append("学院范围不能同时指定专业")
    start, end = _date(p.get("effective_from")), _date(p.get("effective_until"))
    if start and end and end <= start:
        reasons.append("有效期结束必须晚于开始")
    if p.get("current_validity_confirmed"):
        now = datetime.now(timezone.utc)
        if not start or start > now or end and end < now:
            reasons.append("当前有效政策必须有已开始且未过期的明确有效期")
    return reasons


def _assessment(db, snapshot, cache=None):
    v = snapshot["values"]
    reasons, flags = [], set()
    if not snapshot["identities"]["university"] or not snapshot["identities"]["competition"]:
        reasons.append("学校或赛事身份未明确"); flags.add("DUPLICATE_SUSPECTED")
    if v["notice_type"] not in NOTICE_TYPES | POLICY_TYPES:
        reasons.append("未知关系类型")
    if not v["source"]["source_url"]:
        reasons.append("缺少可追踪的原文链接")
    if v["source"]["access_status"] != "readable":
        reasons.append("原文尚未成功读取")
    if v["source"]["verification_state"] != "VERIFIED":
        reasons.append("来源尚未由管理员核验"); flags.add("UNVERIFIED")
    for label, date_value in (("校内截止", v["school_deadline"]),
            ("来源发布时间", v["source"]["published_at"]), ("资料读取时间", v["source"]["collected_at"])):
        try:
            _date(date_value)
        except (TypeError, ValueError):
            reasons.append(label + "不是明确可解析的日期，不能批准")
    if v["relation_kind"] == "notice":
        edition = snapshot["identities"]["edition"]
        if not edition or not v["year"]:
            reasons.append("普通通知必须明确届次"); flags.add("edition_uncertain")
        elif edition["competition_id"] != v["competition_id"] or edition["year"] != v["year"]:
            reasons.append("届次不属于对应赛事或年份"); flags.add("RELATION_CONFLICT")
    else:
        reasons.extend(_policy_reasons(db, v, cache))
    if v["prepared"].get("revoked"):
        flags.add("RELATION_CONFLICT")
    for record in snapshot["existing_records"]:
        if v["relation_kind"] == "notice":
            if record["notice_type"] != v["notice_type"] or len(snapshot["existing_records"]) > 1:
                flags.add("RELATION_CONFLICT")
            if record.get("verification_status") in {"revoked", "retracted", "invalid"} or not record.get("is_verified"):
                flags.add("RELATION_CONFLICT")
            if record.get("internal_registration_deadline") and v["school_deadline"] and not _same_date(
                    record["internal_registration_deadline"], v["school_deadline"]):
                flags.add("RELATION_CONFLICT")
            for deadline in (record.get("metadata_json") or {}).get("school_deadlines", []):
                if deadline.get("notice_type") == v["notice_type"] and v["school_deadline"] and not _same_date(
                        deadline.get("school_deadline"), v["school_deadline"]):
                    flags.add("RELATION_CONFLICT")
        else:
            existing_scope = (record["policy_document"].get("metadata_json") or {}).get("relation_scope")
            if existing_scope is None or (_overlaps(existing_scope, _scope(v)) and existing_scope != _scope(v)):
                flags.add("RELATION_CONFLICT")
            if record["recognition_status"] in {"explicitly_not_recognized", "revoked"}:
                flags.add("RELATION_CONFLICT")
    for peer in snapshot["peers"]:
        other = peer["values"]
        if other["prepared"].get("revoked"):
            flags.add("RELATION_CONFLICT")
        if v["relation_kind"] == "notice":
            if other["school_deadline"] and v["school_deadline"] and not _same_date(other["school_deadline"], v["school_deadline"]):
                flags.add("RELATION_CONFLICT")
        elif other["prepared"].get("scope_type") and v["prepared"].get("scope_type") and (
                _overlaps(_scope(other), _scope(v)) and _scope(other) != _scope(v)):
            flags.add("RELATION_CONFLICT")
    if "RELATION_CONFLICT" in flags:
        reasons.append("RELATION_CONFLICT：已有关系或其他材料存在撤销、范围或期限冲突，请暂缓或拒绝，不自动覆盖")
    return reasons, sorted(flags)


def _detail(db, row, doc, cache=None):
    snapshot = _snapshot(db, row, doc, cache)
    reasons, flags = _assessment(db, snapshot, cache)
    result = deepcopy(snapshot["values"])
    result.update(preview_token=_fr()._token(row, doc, snapshot), flags=flags,
        blocking_reasons=reasons, can_approve=not reasons and row.status in {"pending", "deferred"},
        existing_records=snapshot["existing_records"], history=deepcopy(doc.get("history", [])))
    return result


def _start(db, identity, payload, model, admin):
    fr = _fr()
    # FastAPI supplies a model instance. Preserve omitted patch fields when
    # revalidating, so defaults cannot masquerade as explicit identity changes.
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(exclude_unset=True)
    admin_id, data = fr._admin(db, admin), fr._input(model, payload)
    row, doc = _load(db, identity)
    if row.status not in {"pending", "deferred"}:
        fr._error("学校关系候选已完成审核", 409)
    before = _snapshot(db, row, doc)
    fr._assert_preview(row, doc, before, data.preview_token)
    fr._claim(db, row)
    # All relation writers use the same stable parent lock, including when no
    # relation exists yet. SQLite already holds its write lock after _claim.
    uid = before["values"]["university_id"]
    if uid:
        db.execute(select(University.id).where(University.id == uid).with_for_update())
    after_lock = _snapshot(db, row, doc)
    fr._assert_preview(row, doc, after_lock, data.preview_token)
    return row, doc, data, admin_id, before


def _audit(db, row, doc, admin_id, action, note, before, after, *, decision=None):
    fr = _fr()
    fr._history(db, row, doc, admin_id, action, note, before, after,
        decisions=[{"action": decision}] if decision else [], sources=[after["values"]["source"]])
    # Same entry object is held by AdminAuditLog.after.review until flush.
    if decision:
        doc["history"][-1]["action"] = decision
    fr._save(db, row, doc)


def _merge_sources(old, new):
    sources = [_public_source(source) for source in old or []]
    if not any(s["source_url"] == new["source_url"] for s in sources):
        sources.append(_public_source(new))
    return sources


def _write(db, row, values, records):
    now = datetime.now(timezone.utc)
    # Verifier identity stays in candidate history and AdminAuditLog.
    source = _public_source(values["source"])
    with reviewed_write(db):
        if values["relation_kind"] == "notice":
            if len(records) > 1:
                _fr()._error("RELATION_CONFLICT：已有重复正式通知关系", 409)
            target = db.get(Relation, records[0]["id"]) if records else None
            if target is None:
                target = Relation(university_id=values["university_id"], competition_edition_id=values["edition_id"],
                    notice_type=values["notice_type"], internal_notice_url=source["source_url"],
                    source_type=source["source_type"], source_name=source["publisher"],
                    notice_title=source["source_title"], published_at=_date(source["published_at"]),
                    observed_at=_date(source["collected_at"]) or now, is_verified=True,
                    verification_status="school_confirmed", last_verified_at=now, is_demo=False)
                db.add(target)
            meta = deepcopy(target.metadata_json or {})
            meta["review_sources"] = _merge_sources(meta.get("review_sources"), source)
            if values["school_deadline"]:
                deadline = {"school_deadline": values["school_deadline"], "notice_type": values["notice_type"],
                    "precision": _precision(values["school_deadline"]), "source_url": source["source_url"]}
                deadlines = list(meta.get("school_deadlines") or [])
                if deadline not in deadlines:
                    deadlines.append(deadline)
                meta["school_deadlines"] = deadlines
            target.metadata_json = meta
            if target.internal_registration_deadline is None:
                target.internal_registration_deadline = _registration_deadline(values)
            db.flush()
            return {"record_type": "notice", "record_id": target.id}
        scope = _scope(values)
        matching = [r for r in records if (r["policy_document"].get("metadata_json") or {}).get("relation_scope") == scope]
        if len(matching) > 1:
            _fr()._error("RELATION_CONFLICT：已有重复正式政策关系", 409)
        if matching:
            target = db.get(Recognition, matching[0]["id"])
            document = db.get(PolicyDocument, target.policy_document_id)
            meta = deepcopy(document.metadata_json or {})
            meta["review_sources"] = _merge_sources(meta.get("review_sources"), source)
            document.metadata_json = meta
        else:
            p = values["prepared"]
            identity = {k: values[k] for k in ("university_id", "competition_id", "notice_type")}
            fingerprint = hashlib.sha256(_fr()._dump({"identity": identity, "scope": scope}).encode()).hexdigest()
            document = PolicyDocument(university_id=values["university_id"], college_id=p.get("college_id"),
                major_id=p.get("major_id"), scope_type=p["scope_type"], title=source["source_title"] or "学校竞赛政策",
                policy_type=values["notice_type"], year=values["year"], publisher=source["publisher"],
                source_url=source["source_url"], document_hash="relation:" + fingerprint,
                published_at=_date(source["published_at"]), effective_from=_date(p.get("effective_from")),
                effective_until=_date(p.get("effective_until")), content_text=p["recognition_evidence"],
                is_current=p["current_validity_confirmed"], is_verified=True, verification_status="human_verified",
                source_type="university_policy", is_demo=False,
                metadata_json={"relation_scope": scope, "validity_note": p["validity_note"], "review_sources": [source]})
            db.add(document); db.flush()
            status = ("historical_recognition" if not p["current_validity_confirmed"] else
                "scoped_recognition" if p["student_scope"] not in {"undergraduate", "all"} else "recognized")
            target = Recognition(university_id=values["university_id"], competition_id=values["competition_id"],
                college_id=p.get("college_id"), major_id=p.get("major_id"), policy_document_id=document.id,
                year=values["year"], usage_type=values["notice_type"], recognition_status=status,
                evidence_text=p["recognition_evidence"], evidence_hash=fingerprint, confidence=1.0,
                needs_manual_review=False, is_demo=False)
            db.add(target)
        db.flush()
        return {"record_type": "policy", "record_id": target.id, "policy_document_id": document.id}


class SchoolRelationReviewService:
    @staticmethod
    def detail(db, identity):
        cache = _read_cache(db)
        row, doc = _load(db, identity, cache)
        return _detail(db, row, doc, cache)

    @staticmethod
    @_atomic
    def prepare(db, identity, payload, *, admin):
        row, doc, data, admin_id, before = _start(db, identity, payload, SchoolRelationPrepareIn, admin)
        v = before["values"]
        patch = data.model_dump(mode="json", exclude_unset=True)
        for key in ("preview_token", "note"):
            patch.pop(key, None)
        if v["relation_kind"] == "notice" and set(patch) & set(SCOPE_FIELDS):
            _fr()._error("普通通知不能转为政策或填写政策范围")
        for key in ("university_id", "competition_id", "year", "edition_id"):
            if key in patch and v[key] is not None and patch[key] != v[key]:
                _fr()._error("不能更换已明确的学校、赛事或届次", 409)
        for key, model in (("university_id", University), ("competition_id", Competition)):
            if key in patch:
                if not patch[key] or db.get(model, patch[key]) is None:
                    _fr()._error("补充的实体不存在")
                if not v[key] and not patch.get("identity_evidence"):
                    _fr()._error("补充身份必须记录同一实体证据")
        state = deepcopy(doc.get("relation_review") or {})
        prepared = {**v["prepared"], **patch}
        state["prepared"] = prepared
        doc["relation_review"] = state
        updated = _values(db, row, doc)
        if updated["relation_kind"] == "notice" and updated["edition_id"]:
            edition = db.get(CompetitionEdition, updated["edition_id"])
            if not edition or edition.competition_id != updated["competition_id"]:
                _fr()._error("指定届次不属于该赛事")
            if updated["year"] is None:
                prepared["year"] = edition.year
            elif edition.year != updated["year"]:
                _fr()._error("指定届次与明确年份不一致")
        if updated["relation_kind"] == "policy":
            reasons = _policy_reasons(db, updated)
            if reasons:
                _fr()._error("；".join(reasons))
        if prepared != v["prepared"]:
            state.pop("source_verification", None)
        # Explicit identity resolution updates queue filtering, never official entities.
        doc["university_id"] = updated["university_id"]
        doc["competition_id"] = updated["competition_id"]
        row.university_id = updated["university_id"]
        _audit(db, row, doc, admin_id, "school_relation_prepare", data.note, before, _snapshot(db, row, doc))
        return _detail(db, row, doc)

    @staticmethod
    @_atomic
    def verify_source(db, identity, payload, *, admin):
        row, doc, data, admin_id, before = _start(db, identity, payload, SchoolRelationSourceVerifyIn, admin)
        source = before["values"]["source"]
        if source["access_status"] != "readable" or not source["source_url"]:
            _fr()._error("需要可读取且可追踪的原始来源", 409)
        _fr()._input(FieldSourceIn, {k: source[k] for k in ("source_type", "source_url", "source_title", "publisher")})
        state = deepcopy(doc.get("relation_review") or {})
        state["source_verification"] = dict(verification_state="VERIFIED", verified_by=admin_id,
            verified_at=datetime.now(timezone.utc).isoformat(), note=data.note,
            evidence_fingerprint=_verification_fingerprint(row, doc))
        doc["relation_review"] = state
        _audit(db, row, doc, admin_id, "school_relation_verify_source", data.note, before, _snapshot(db, row, doc))
        return _detail(db, row, doc)

    @staticmethod
    @_atomic
    def review(db, identity, payload, *, admin):
        row, doc, data, admin_id, before = _start(db, identity, payload, SchoolRelationReviewIn, admin)
        written = {}
        if data.action == "approve":
            reasons, flags = _assessment(db, before)
            if reasons:
                _fr()._error("；".join(reasons), 409)
            written = _write(db, row, before["values"], before["existing_records"])
        row.status = {"approve": "approved", "reject": "rejected", "defer": "deferred"}[data.action]
        row.reviewed_at = datetime.now(timezone.utc)
        row.reviewer_notes = data.note
        state = deepcopy(doc.get("relation_review") or {})
        state["decision"] = dict(action=data.action, reviewer_id=admin_id,
            reviewed_at=row.reviewed_at.isoformat(), note=data.note, **written)
        doc["relation_review"] = state
        _audit(db, row, doc, admin_id, "school_relation_review", data.note, before,
            _snapshot(db, row, doc), decision=data.action)
        return _detail(db, row, doc)
