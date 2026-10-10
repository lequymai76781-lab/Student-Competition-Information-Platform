from datetime import datetime, timezone

from sqlalchemy import DateTime, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Legacy naive values mean UTC; never infer the server's local timezone."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Preserve DateTime DDL; SQLite stores naive UTC and Python reads aware UTC."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        value = as_utc(value)
        return value.replace(tzinfo=None) if value is not None and dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        return as_utc(value)


def _utc_assignment(target, value, oldvalue, initiator):
    return as_utc(value)


class Base(DeclarativeBase):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Install once when each model is declared, before engines or statements
        # exist. This changes bind/result handling, not tables or stored records.
        if "__table__" in cls.__dict__:
            for column in cls.__table__.columns:
                if isinstance(column.type, DateTime):
                    column.type = UTCDateTime(timezone=column.type.timezone)
                    event.listen(getattr(cls, column.key), "set", _utc_assignment, retval=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
