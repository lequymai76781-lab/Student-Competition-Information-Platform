"""Official fact writes require the field-review service's approval scope.

The guard covers competition facts and reviewed school relations/policies. Plain Session is intentionally
available for isolated fixture setup; runtime uses ReviewGuardedSession.
"""
from contextlib import contextmanager
import re
from weakref import WeakKeyDictionary, ref

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause


PROTECTED_TABLES = frozenset({"competitions", "competition_editions", "university_competition_edition_relations",
    "policy_documents", "competition_policy_recognitions"})
BOOKKEEPING_FIELDS = frozenset({"freshness_status", "next_check_at", "last_seen_at", "updated_at"})
PROTECTED_RELATIONSHIPS = {
    "competitions": frozenset({"editions", "parent", "children"}),
    "competition_editions": frozenset({"competition"}),
}
_review_depth = WeakKeyDictionary()
_guarded_connections = WeakKeyDictionary()


class UnreviewedFactWrite(RuntimeError):
    """An importer attempted to bypass human field review."""


def _deny(table: str, operation: str) -> None:
    raise UnreviewedFactWrite(
        f"Blocked {operation} on {table}: submit a field review candidate and "
        "verify its source before an administrator approves official facts. "
        "Legacy importers must use CompetitionFieldIngestionService."
    )


def is_review_guarded(db: Session) -> bool:
    return isinstance(db, ReviewGuardedSession)


def _table_name(obj) -> str | None:
    inspected = inspect(obj, raiseerr=False)
    mapper = getattr(inspected, "mapper", inspected)
    table = getattr(mapper, "local_table", None)
    return getattr(table, "name", None)


def _check_pending(db: Session) -> None:
    for obj in db.new:
        if (table := _table_name(obj)) in PROTECTED_TABLES:
            _deny(table, "insert")
    for obj in db.deleted:
        if (table := _table_name(obj)) in PROTECTED_TABLES:
            _deny(table, "delete")
    for obj in db.dirty:
        if (table := _table_name(obj)) not in PROTECTED_TABLES:
            continue
        state = inspect(obj)
        changed = {attr.key for attr in state.mapper.column_attrs if state.attrs[attr.key].history.has_changes()}
        changed.update(key for key in PROTECTED_RELATIONSHIPS.get(table, ()) if state.attrs[key].history.has_changes())
        if protected := changed - BOOKKEEPING_FIELDS:
            _deny(table, "update " + ", ".join(sorted(protected)))


@contextmanager
def reviewed_write(db: Session):
    """Only the validated field-review service may use this; never commits.

Reject preexisting dirty facts so approval cannot launder a prior import write.
Flush inside the scope so its permission cannot leak into a later transaction.
"""
    depth = _review_depth.get(db, 0)
    if depth == 0:
        _check_pending(db)
    _review_depth[db] = depth + 1
    try:
        yield
        db.flush()
    finally:
        if depth:
            _review_depth[db] = depth
        else:
            _review_depth.pop(db, None)


class ReviewGuardedSession(Session):
    """Also protect legacy bulk APIs, which skip normal ORM events."""

    def bulk_save_objects(self, objects, *args, **kwargs):
        objects = list(objects)
        if not _review_depth.get(self):
            for obj in objects:
                if (table := _table_name(obj)) in PROTECTED_TABLES:
                    _deny(table, "bulk save")
        return super().bulk_save_objects(objects, *args, **kwargs)

    def bulk_insert_mappings(self, mapper, mappings, *args, **kwargs):
        if not _review_depth.get(self) and (table := _table_name(mapper)) in PROTECTED_TABLES:
            _deny(table, "bulk insert")
        return super().bulk_insert_mappings(mapper, mappings, *args, **kwargs)

    def bulk_update_mappings(self, mapper, mappings):
        mappings = list(mappings)
        if not _review_depth.get(self) and (table := _table_name(mapper)) in PROTECTED_TABLES:
            for values in mappings:
                if set(values) - BOOKKEEPING_FIELDS - {"id"}:
                    _deny(table, "bulk update")
        return super().bulk_update_mappings(mapper, mappings)


@event.listens_for(ReviewGuardedSession, "before_flush")
def _before_flush(db, flush_context, instances):
    if not _review_depth.get(db):
        _check_pending(db)


@event.listens_for(ReviewGuardedSession, "do_orm_execute")
def _before_execute(state):
    if _review_depth.get(state.session):
        return
    _check_statement(state.statement, state.parameters,
                     primary_key_selector=state.is_orm_statement and state.is_executemany)


def _check_statement(statement, parameters=None, *, primary_key_selector=False):
    if isinstance(statement, TextClause):
        # Raw SQL cannot prove a bookkeeping-only change. Refuse writes involving
        # either protected table, including comments, CTEs and quoted names.
        sql = re.sub(r"/\*.*?\*/|--[^\n]*", " ", statement.text, flags=re.S)
        if re.search(r"\b(insert|update|delete|replace|merge|drop|alter|truncate)\b", sql, re.I):
            for table in PROTECTED_TABLES:
                if re.search(r"\b" + table + r"\b", sql, re.I):
                    _deny(table, "raw SQL write")
        return
    target = getattr(statement, "table", None)
    while getattr(target, "original", None) is not None:
        target = target.original
    table = getattr(target, "name", None)
    if table not in PROTECTED_TABLES:
        return
    if getattr(statement, "is_insert", False) or getattr(statement, "is_delete", False):
        _deny(table, "bulk insert/delete")
    if getattr(statement, "is_update", False):
        keys = {getattr(key, "key", key) for key in (getattr(statement, "_values", None) or {})}
        keys.update(getattr(key, "key", key) for key, _ in (getattr(statement, "_ordered_values", None) or ()))
        params = parameters
        if params:
            columns = set(target.columns.keys())
            for values in params if isinstance(params, (list, tuple)) else [params]:
                # Execute-time column parameters can extend SET without being
                # present in statement._values. Compiler-generated WHERE binds
                # (id_1, target_id) and custom value binds are not target columns.
                supplied_columns = set(values) & columns
                if primary_key_selector:
                    supplied_columns.discard("id")
                keys.update(supplied_columns)
        if not keys or keys - BOOKKEEPING_FIELDS:
            _deny(table, "bulk update")


@event.listens_for(ReviewGuardedSession, "after_begin")
def _guard_transaction_connection(db, transaction, connection):
    """Also cover db.connection().execute()/exec_driver_sql().

This listener belongs to the Connection borrowed by this guarded session,
not the Engine; unrelated fixture/administrative connections are unaffected.
"""
    if connection in _guarded_connections:
        return
    db_ref = ref(db)
    _guarded_connections[connection] = db_ref

    def check(connection, cursor, sql, parameters, context, executemany):
        owner = db_ref()
        if owner is None or _review_depth.get(owner):
            return
        # before_flush has already checked each changed mapped field. Driver
        # INSERT/UPDATE generated by that flush is therefore safe here.
        if owner._flushing:
            return
        compiled = getattr(context, "compiled", None)
        statement = getattr(compiled, "statement", None)
        if statement is not None and (getattr(statement, "is_update", False)
                or getattr(statement, "is_insert", False) or getattr(statement, "is_delete", False)):
            _check_statement(statement, getattr(context, "compiled_parameters", None))
        else:
            _check_statement(TextClause(sql))

    event.listen(connection, "before_cursor_execute", check)
