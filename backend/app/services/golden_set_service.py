"""Isolated, revisioned human labels over immutable historical snapshots.

This module does not use the application's write session, classifier, matcher,
or review approval services. Its only writable file is annotations.sqlite.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from fastapi import HTTPException

from app.schemas.golden_set import AnnotationIn, AuditIn
from app.services.source_document_classifier import DOCUMENT_TYPES, DOCUMENT_TYPE_LABELS

POLICY_CHECKS = {
    "is_policy": "确实是政策文件",
    "extraction_correct": "赛事名称提取正确",
    "recognition_type_correct": "认可类型正确",
    "match_correct": "赛事匹配正确",
    "no_track_ambiguity": "不存在子赛道歧义",
    "validity_clear": "政策有效期清晰且有效",
}
RELATION_CHECKS = {
    "school_correct": "学校正确",
    "competition_correct": "赛事正确",
    "source_valid": "政策来源有效",
    "recognition_type_correct": "认可类型正确",
    "match_correct": "赛事名称匹配正确",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class GoldenSetService:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        path = self.directory / "manifest.json"
        if not path.is_file():
            raise HTTPException(503, "Golden Set 样本尚未准备好")
        raw = path.read_bytes()
        self.digest = sha256(raw).hexdigest()
        self.manifest = json.loads(raw)
        self.items = self._index(self.manifest.get("items", []), "source_id")
        self.audit_sets = {
            kind: self._index(self.manifest.get("audit_sets", {}).get(kind, []), "audit_id")
            for kind in ("policies", "relations")
        }
        self.provenance = "test_fixture" if self.manifest.get("fixture_only") else "human"

    @staticmethod
    def _index(items, key):
        indexed = {str(item[key]): item for item in items}
        if len(indexed) != len(items) or any(not identity for identity in indexed):
            raise HTTPException(409, "样本 ID 重复或无效")
        return indexed

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.directory / "annotations.sqlite", timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS annotations (source_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS audits (kind TEXT NOT NULL, audit_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,audit_id))")
            db.execute("CREATE TABLE IF NOT EXISTS exposures (source_id TEXT PRIMARY KEY, actor TEXT NOT NULL, at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, entity_kind TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, data TEXT NOT NULL)")
            saved = db.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()
            if saved and saved[0] != self.digest:
                raise HTTPException(409, "样本快照已变更，拒绝混用已有人工标注")
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('manifest_sha256', ?)", (self.digest,))
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('dataset_id', ?)", (self.manifest["dataset_id"],))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _progress(items, annotations):
        counts = Counter(a["status"] for identity, a in annotations.items() if identity in items)
        return {"total": len(items), "annotated": counts["annotated"], "draft": counts["draft"],
                "skipped": counts["skipped"], "untouched": len(items) - sum(counts.values())}

    @staticmethod
    def _annotations(db):
        return {row["source_id"]: json.loads(row["data"]) for row in db.execute("SELECT * FROM annotations")}

    @staticmethod
    def _audits(db, kind):
        return {row["audit_id"]: json.loads(row["data"]) for row in db.execute("SELECT * FROM audits WHERE kind=?", (kind,))}

    def dataset(self):
        with self._db() as db:
            annotations = self._annotations(db)
            exposed = {row[0] for row in db.execute("SELECT source_id FROM exposures")}
            return {"dataset_id": self.manifest["dataset_id"], "total": len(self.items),
                    "items": [{**deepcopy(item), "prediction_exposed": identity in exposed,
                               "annotation": annotations.get(identity)} for identity, item in self.items.items()],
                    "progress": self._progress(self.items, annotations),
                    "document_types": [{"value": value, "label": DOCUMENT_TYPE_LABELS[value]} for value in DOCUMENT_TYPES],
                    "audit_sets": {kind: {"total": len(items)} for kind, items in self.audit_sets.items()},
                    "provenance": self.manifest.get("provenance", {}),
                    "fixture_only": bool(self.manifest.get("fixture_only"))}

    @staticmethod
    def _event(db, kind, identity, action, actor, at, data):
        db.execute("INSERT INTO events(entity_kind,entity_id,action,actor,at,data) VALUES (?,?,?,?,?,?)",
                   (kind, identity, action, actor, at, _json(data)))

    @staticmethod
    def _revision(row, expected):
        current = row["revision"] if row else 0
        if current != expected:
            raise HTTPException(409, "该条已在其他窗口更新，请对比最新结果后再保存")
        return current + 1

    def _item(self, identity):
        item = self.items.get(str(identity))
        if item is None:
            raise HTTPException(404, "样本不存在")
        return item

    def expose(self, source_id, actor):
        self._item(source_id)
        source_id = str(source_id)
        with self._db() as db:
            at = _now()
            inserted = db.execute("INSERT OR IGNORE INTO exposures VALUES (?,?,?)", (source_id, actor, at)).rowcount
            if inserted:
                self._event(db, "classification", source_id, "prediction_exposed", actor, at, {})
        return {"prediction_exposed": True}

    def save_annotation(self, source_id, body: AnnotationIn, actor):
        item = self._item(source_id)
        source_id = str(source_id)
        with self._db() as db:
            row = db.execute("SELECT * FROM annotations WHERE source_id=?", (source_id,)).fetchone()
            revision = self._revision(row, body.expected_revision)
            at = _now()
            if body.prediction_exposed:
                db.execute("INSERT OR IGNORE INTO exposures VALUES (?,?,?)", (source_id, actor, at))
            exposed = db.execute("SELECT 1 FROM exposures WHERE source_id=?", (source_id,)).fetchone() is not None
            annotation = {**body.model_dump(exclude={"expected_revision"}), "source_id": item["source_id"],
                          "title": item["title"], "revision": revision, "saved_at": at,
                          "annotated_by": actor, "annotated_at": at if body.status == "annotated" else None,
                          "skipped": body.status == "skipped", "prediction_exposed": exposed,
                          "predicted_type": item.get("predicted_type"), "predicted_confidence": item.get("predicted_confidence"),
                          "label_provenance": self.provenance}
            db.execute("INSERT INTO annotations VALUES (?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET revision=excluded.revision,status=excluded.status,data=excluded.data",
                       (source_id, revision, body.status, _json(annotation)))
            self._event(db, "classification", source_id, body.status, actor, at,
                        {"before": json.loads(row["data"]) if row else None, "after": annotation})
            return {"annotation": annotation, "progress": self._progress(self.items, self._annotations(db))}

    def _audit_kind(self, kind):
        if kind not in self.audit_sets:
            raise HTTPException(404, "抽验类型不存在")
        return self.audit_sets[kind], POLICY_CHECKS if kind == "policies" else RELATION_CHECKS

    def audits(self, kind):
        items, checks = self._audit_kind(kind)
        with self._db() as db:
            annotations = self._audits(db, kind)
            return {"items": [{**deepcopy(item), "annotation": annotations.get(identity)} for identity, item in items.items()],
                    "progress": self._progress(items, annotations),
                    "checks": [{"key": key, "label": label} for key, label in checks.items()]}

    def save_audit(self, kind, audit_id, body: AuditIn, actor):
        items, checks = self._audit_kind(kind)
        audit_id = str(audit_id)
        if audit_id not in items:
            raise HTTPException(404, "抽验样本不存在")
        if set(body.answers) - set(checks) or (body.status == "annotated" and set(body.answers) != set(checks)):
            raise HTTPException(422, "请逐项回答所有抽验问题（可选择无法确定）")
        with self._db() as db:
            row = db.execute("SELECT * FROM audits WHERE kind=? AND audit_id=?", (kind, audit_id)).fetchone()
            revision = self._revision(row, body.expected_revision)
            at = _now()
            annotation = {**body.model_dump(exclude={"expected_revision"}), "audit_id": audit_id,
                          "title": items[audit_id]["title"], "kind": kind, "revision": revision,
                          "annotated_by": actor, "annotated_at": at if body.status == "annotated" else None,
                          "saved_at": at, "skipped": body.status == "skipped", "label_provenance": self.provenance}
            db.execute("INSERT INTO audits VALUES (?,?,?,?,?) ON CONFLICT(kind,audit_id) DO UPDATE SET revision=excluded.revision,status=excluded.status,data=excluded.data",
                       (kind, audit_id, revision, body.status, _json(annotation)))
            self._event(db, kind, audit_id, body.status, actor, at,
                        {"before": json.loads(row["data"]) if row else None, "after": annotation})
            return {"annotation": annotation, "progress": self._progress(items, self._audits(db, kind))}

    def export(self):
        from app.services.golden_set_metrics import evaluate_golden_set
        with self._db() as db:
            annotations = list(self._annotations(db).values())
            policy = list(self._audits(db, "policies").values())
            relation = list(self._audits(db, "relations").values())
        return {"dataset_id": self.manifest["dataset_id"], "manifest_sha256": self.digest,
                "annotations": annotations, "policy_audits": policy, "relation_audits": relation,
                "metrics": evaluate_golden_set(list(self.items.values()), annotations, policy, relation)}

    def metrics(self):
        return self.export()["metrics"]


def get_golden_set_service():
    configured = os.environ.get("GOLDEN_SET_DIR")
    if not configured:
        raise HTTPException(404, "本服务未启用独立 Golden Set 实验")
    allowed = Path(__file__).resolve().parents[3] / ".codex-qa" / "golden-set-20261001"
    directory = Path(configured).resolve()
    if not directory.is_relative_to(allowed.resolve()) or directory == allowed.resolve():
        raise HTTPException(503, "Golden Set 必须使用指定实验目录下的独立存储")
    return GoldenSetService(directory)
