"""Append-only audit telemetry. Caller owns commit/rollback; no candidate writes.

Mode is an explicit operator declaration, not proof that a person read a source.
A sample is a completely decided candidate, or one batch wall-clock interval.
Thirty minutes without a recorded activity excludes an unfinished interval.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
from statistics import mean, median
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import inspect, select, update
from app.models import AdminAuditLog, ReviewQueue, User
from app.schemas.review_telemetry import ReviewTelemetryEventIn, ReviewTelemetryStartIn

OBJECT_TYPE = "review_telemetry"
IDLE_SECONDS = 1800
FINAL = {"approved", "rejected"}
REVIEW_ACTIONS = {"field_review", "field_reject_unstructured", "school_relation_review"}

def _now():
    return datetime.now(timezone.utc)

def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _error(message, status=422):
    raise HTTPException(status_code=status, detail=message)

def _input(model, payload):
    try:
        return model.model_validate(payload.model_dump() if hasattr(payload, "model_dump") else payload)
    except ValidationError as exc:
        _error(str(exc))

def _admin_id(db, actor, *, internal=False):
    if internal:
        if isinstance(actor, bool) or not isinstance(actor, int):
            _error("A persisted administrator is required", 403)
        identity = actor
    else:
        if not isinstance(actor, User) or inspect(actor).identity is None:
            _error("A persisted administrator is required", 403)
        identity = actor.id
    # no_autoflush prevents an unflushed caller mutation granting itself a role.
    with db.no_autoflush:
        actual = db.execute(select(User.id, User.is_admin, User.is_active).where(User.id == identity)).first()
    if not actual or not actual.is_admin or not actual.is_active:
        _error("A persisted administrator is required", 403)
    return actual.id

def _lock(db, admin_id):
    """Serialize per-admin sessions without updating candidate preview data."""
    connection = db.connection()
    if connection.dialect.name == "sqlite":
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            # SQLite write reservation, with no rows changed or identity touched.
            db.execute(update(AdminAuditLog).where(AdminAuditLog.id < 0).values(id=AdminAuditLog.id))
    else:
        db.execute(select(User.id).where(User.id == admin_id).with_for_update())

def _candidate(db, identity):
    row = db.scalar(select(ReviewQueue).where(ReviewQueue.id == identity).execution_options(populate_existing=True))
    if row is None or row.item_type != "field_candidate":
        _error("Review candidate not found", 404)
    try:
        doc = json.loads(row.raw_value or "")
        if not isinstance(doc, dict) or doc.get("schema_version") != 1 or not isinstance(doc.get("proposals"), list):
            raise ValueError()
    except (TypeError, ValueError):
        _error("Candidate document is invalid", 409)
    return row, doc

def _terminal(row, doc):
    if row.status in FINAL:
        return True
    names = {p.get("field_name") for p in doc["proposals"]}
    return bool(names) and all(doc.get("decisions", {}).get(n, {}).get("action") in FINAL for n in names)

def _pending(row, doc):
    return row.status in {"pending", "partially_approved", "deferred"} and not _terminal(row, doc)

def _all_logs(db, admin_id=None):
    query = select(AdminAuditLog).where(AdminAuditLog.object_type == OBJECT_TYPE).order_by(AdminAuditLog.id)
    if admin_id is not None:
        query = query.where(AdminAuditLog.admin_id == admin_id)
    return list(db.scalars(query))

def _sessions(logs):
    sessions = {}
    for row in logs:
        data = row.after or {}
        identity = data.get("session_id")
        if not identity:
            continue
        if row.action == "review_telemetry_start":
            sessions[identity] = {**data, "events": [], "start_log_id": row.id, "admin_id": row.admin_id}
        elif identity in sessions:
            sessions[identity]["events"].append((row.action.removeprefix("review_telemetry_"), _utc(row.created_at), data))
    return list(sessions.values())

def _state(session, now):
    started = _utc(session["started_at"])
    last = started
    phases = {"source_open": None, "decision": None, "submit": None}
    status, completed, reason, ended = "active", None, None, None
    for event, at, data in session["events"]:
        last = at
        if event in phases and phases[event] is None:
            phases[event] = max(0.0, (at - started).total_seconds())
        if event == "complete":
            status, completed, ended = "completed", at, at
        elif event == "interrupt":
            status, reason, ended = "interrupted", data.get("reason"), at
    if status == "active" and (now - last).total_seconds() > IDLE_SECONDS:
        status, reason, ended = "interrupted", "idle_timeout", last
    return {
        "session_id": session["session_id"], "candidate_id": session["candidate_id"],
        "candidate_ids": session["candidate_ids"], "reviewer_id": session["admin_id"],
        "mode": session["mode"], "sample_type": session["sample_type"], "status": status,
        "started_at": started.isoformat(), "last_event_at": last.isoformat(),
        "completed_at": completed.isoformat() if completed else None,
        "elapsed_seconds": max(0.0, ((ended or now) - started).total_seconds()),
        "phase_seconds": phases, "interruption_reason": reason, "candidate_snapshots": session["candidate_snapshots"],
    }

def _record(db, admin_id, candidate_id, event, data, now):
    row = AdminAuditLog(admin_id=admin_id, action="review_telemetry_" + event,
        object_type=OBJECT_TYPE, object_id=candidate_id, before=None, after=data, created_at=now)
    db.add(row)
    db.flush()
    return row

def _reviews(db, admin_id=None, after_id=0, candidate_ids=None):
    query = select(AdminAuditLog).where(AdminAuditLog.object_type == "field_candidate",
        AdminAuditLog.action.in_(REVIEW_ACTIONS), AdminAuditLog.id > after_id).order_by(AdminAuditLog.id)
    if admin_id is not None:
        query = query.where(AdminAuditLog.admin_id == admin_id)
    if candidate_ids is not None:
        query = query.where(AdminAuditLog.object_id.in_(candidate_ids))
    return list(db.scalars(query))

def _is_decision(audit):
    if audit.action == "field_reject_unstructured":
        return True
    review = (audit.after or {}).get("review", {})
    if audit.action == "school_relation_review":
        return review.get("action") in {"approve", "reject"}
    return any(d.get("action") in {"approve", "reject"} for d in review.get("decisions", []))

def _snapshot(db, row, doc):
    # Local import avoids coupling the core review service's module imports.
    from app.services.field_review_service import FieldReviewService
    detail = FieldReviewService.detail(db, row.id)
    context = doc.get("collection_context") or {}
    candidates = [p.get("source") or {} for p in doc["proposals"]]
    if context.get("source_url") or context.get("source_title"):
        candidates.append(context)
    elif row.source_url:
        candidates.append({"source_url": row.source_url})
    sources = {("url", source["source_url"]) if source.get("source_url") else
        ("offline", source.get("source_title"), source.get("publisher"))
        for source in candidates if source.get("source_url") or source.get("source_title")}
    return {"candidate_id": row.id, "kind": context.get("kind") or doc.get("entity_type"),
        "source_count": len(sources), "risk": detail.get("risk_level") or detail.get("risk") or "unknown"}

def _summary(states):
    done = [s for s in states if s["status"] == "completed"]
    durations = sorted(s["elapsed_seconds"] for s in done)
    count = sum(len(s["candidate_ids"]) for s in done)
    total = sum(durations)
    return {"completed_samples": len(done), "completed_candidates": count,
        "active_sessions": sum(s["status"] == "active" for s in states),
        "interrupted_sessions": sum(s["status"] == "interrupted" for s in states),
        "mean_seconds": mean(durations) if durations else None,
        "median_seconds": median(durations) if durations else None,
        "p90_seconds": durations[math.ceil(len(durations) * 0.9) - 1] if durations else None,
        "elapsed_total_seconds": total,
        "theoretical_per_hour": 3600 * count / total if total > 0 else None}

class ReviewTelemetryService:
    @staticmethod
    def start(db, id, payload, *, admin):
        data = _input(ReviewTelemetryStartIn, payload)
        admin_id = _admin_id(db, admin)
        members = data.candidate_ids or [id]
        if members[0] != id:
            _error("The route candidate must be the first batch member")
        _lock(db, admin_id)
        candidates = [_candidate(db, item) for item in members]
        now = _now()
        sessions = _sessions(_all_logs(db, admin_id))
        active = [s for s in sessions if _state(s, now)["status"] == "active"]
        if any(s["mode"] != data.mode for s in active):
            _error("An active timing session cannot change mode", 409)
        for session in active:
            if session["candidate_ids"] == members:
                if all(_terminal(row, doc) for row, doc in candidates):
                    _error("Review candidates are already completed", 409)
                if any(not _pending(row, doc) and not _terminal(row, doc) for row, doc in candidates):
                    _error("A batch candidate is no longer reviewable", 409)
                reviewers = {r.object_id: r.admin_id for r in _reviews(db,
                    after_id=session["review_audit_watermark"], candidate_ids=members) if _is_decision(r)}
                if any(_terminal(row, doc) and reviewers.get(row.id) != admin_id for row, doc in candidates):
                    _error("A batch member was completed by another reviewer", 409)
                _record(db, admin_id, id, "resume", {"session_id": session["session_id"]}, now)
                session["events"].append(("resume", now, {}))
                return {**_state(session, now), "resumed": True}
        if any(not _pending(row, doc) for row, doc in candidates):
            _error("Only unfinished review candidates can start timing", 409)
        # Validate expensive snapshots before persisting any interruption.
        snapshots = [_snapshot(db, row, doc) for row, doc in candidates]
        review_ids = [r.id for r in _reviews(db, admin_id)]
        for session in active:
            _record(db, admin_id, session["candidate_id"], "interrupt",
                {"session_id": session["session_id"], "reason": "switched_candidate"}, now)
        session = {"session_id": uuid4().hex, "candidate_id": id, "candidate_ids": members,
            "mode": data.mode, "sample_type": "batch" if len(members) > 1 else "single",
            "started_at": now.isoformat(), "review_audit_watermark": max(review_ids, default=0),
            "candidate_snapshots": snapshots}
        log = _record(db, admin_id, id, "start", session, now)
        return {**_state({**session, "admin_id": admin_id, "events": [], "start_log_id": log.id}, now), "resumed": False}

    @staticmethod
    def event(db, id, payload, *, admin):
        data = _input(ReviewTelemetryEventIn, payload)
        admin_id = _admin_id(db, admin)
        _lock(db, admin_id)
        sessions = _sessions(_all_logs(db))
        session = next((s for s in sessions if s["session_id"] == data.session_id), None)
        if session is None:
            _error("Timing session not found", 404)
        if session["admin_id"] != admin_id:
            _error("Timing session belongs to another administrator", 403)
        if session["candidate_id"] != id:
            _error("Timing session belongs to another candidate", 409)
        now = _now()
        if _state(session, now)["status"] != "active":
            _error("Timing session is no longer active", 409)
        candidates = [_candidate(db, item) for item in session["candidate_ids"]]
        if any(row.status not in {"pending", "partially_approved", "deferred", "approved", "rejected"} for row, doc in candidates):
            _error("A batch candidate is no longer reviewable", 409)
        if all(_terminal(row, doc) for row, doc in candidates):
            _error("Review candidate is already completed", 409)
        proposals = [p for row, doc in candidates for p in doc["proposals"]]
        if data.proposal_id and not any(p.get("id") == data.proposal_id for p in proposals):
            _error("Unknown candidate proposal")
        if data.field_name and not any(p.get("field_name") == data.field_name for p in proposals):
            _error("Unknown candidate field")
        if data.proposal_id and data.field_name and not any(
                p.get("id") == data.proposal_id and p.get("field_name") == data.field_name for p in proposals):
            _error("The proposal does not belong to that field")
        event_data = data.model_dump(exclude={"event"}, exclude_none=True)
        _record(db, admin_id, id, data.event, event_data, now)
        session["events"].append((data.event, now, event_data))
        return _state(session, now)

    @staticmethod
    def complete(db, id, admin_id, action):
        admin_id = _admin_id(db, admin_id, internal=True)
        if action not in {"approve", "reject"}:
            return {"recorded": False, "reason": "not_a_final_decision", "session": None}
        _lock(db, admin_id)
        now = _now()
        matches = [s for s in _sessions(_all_logs(db, admin_id)) if id in s["candidate_ids"]]
        active = [s for s in matches if _state(s, now)["status"] == "active"]
        if not active:
            prior = next((s for s in reversed(matches) if _state(s, now)["status"] == "completed"), None)
            return {"recorded": False, "reason": "already_completed" if prior else "no_active_session",
                "session": _state(prior, now) if prior else None}
        session = active[-1]
        candidates = [_candidate(db, item) for item in session["candidate_ids"]]
        if not all(_terminal(row, doc) for row, doc in candidates):
            return {"recorded": False, "reason": "candidate_unfinished", "session": _state(session, now)}
        reviews = _reviews(db, after_id=session["review_audit_watermark"], candidate_ids=session["candidate_ids"])
        latest = {r.object_id: r for r in reviews if _is_decision(r)}
        decided = {identity for identity, audit in latest.items() if audit.admin_id == admin_id}
        if not set(session["candidate_ids"]).issubset(decided):
            return {"recorded": False, "reason": "missing_successful_review_audit", "session": _state(session, now)}
        _record(db, admin_id, session["candidate_id"], "complete",
            {"session_id": session["session_id"], "action": action,
             "review_audit_ids": [r.id for r in reviews if _is_decision(r) and r.object_id in session["candidate_ids"]]}, now)
        session["events"].append(("complete", now, {}))
        return {"recorded": True, "reason": None, "session": _state(session, now)}

    @staticmethod
    def statistics(db, admin, mode=None):
        admin_id = _admin_id(db, admin)
        if mode not in {None, "human", "automation"}:
            _error("Unknown timing mode")
        now = _now()
        sessions = _sessions(_all_logs(db, admin_id))
        states = [_state(s, now) for s in sessions]
        active_ids = {cid for state in states if state["status"] == "active" for cid in state["candidate_ids"]}
        if active_ids:
            rows = {r.id: r for r in db.scalars(select(ReviewQueue).where(ReviewQueue.id.in_(active_ids)))}
            last_reviewers = {r.object_id: r.admin_id for r in _reviews(db, candidate_ids=active_ids) if _is_decision(r)}
            for state in states:
                if state["status"] != "active":
                    continue
                closed = []
                for cid in state["candidate_ids"]:
                    row = rows.get(cid)
                    try:
                        doc = json.loads(row.raw_value or "") if row else None
                        valid = row is not None and row.item_type == "field_candidate" and isinstance(doc, dict) and isinstance(doc.get("proposals"), list)
                        if not valid or row.status not in {"pending", "partially_approved", "deferred", "approved", "rejected"}:
                            raise ValueError()
                        terminal = _terminal(row, doc)
                    except (ValueError, TypeError):
                        state.update(status="interrupted", interruption_reason="candidate_unavailable")
                        break
                    closed.append(terminal)
                    if terminal and last_reviewers.get(cid) != admin_id:
                        state.update(status="interrupted", interruption_reason="completed_by_other_reviewer")
                        break
                else:
                    if all(closed):
                        state.update(status="interrupted", interruption_reason="candidate_completed_without_timing")
        modes = [mode] if mode else ["human", "automation"]
        groups = {}
        for group_mode in modes:
            subset = [s for s in states if s["mode"] == group_mode]
            groups[group_mode] = {**_summary(subset), "by_sample_type": {
                kind: _summary([s for s in subset if s["sample_type"] == kind]) for kind in ["single", "batch"]}}
        processed = {r.object_id for r in _reviews(db, admin_id) if _is_decision(r)}
        timed = {cid for s in states if s["status"] == "completed" for cid in s["candidate_ids"]}
        return {"reviewer_id": admin_id, "generated_at": now.isoformat(), "mode": mode,
            "processed_candidates": len(processed), "unknown_duration_candidates": len(processed - timed),
            "groups": groups, "sessions": [s for s in states if mode is None or s["mode"] == mode],
            "measurement_notes": "Server wall-clock; mode is declared, source opening is not proof of reading. "
                "P90 uses nearest rank. Capacity assumes the measured workload and no non-review overhead."}
