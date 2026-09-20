"""Admin audit log + lightweight beta metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AdminAuditLog, BetaMetric

logger = logging.getLogger("v1.audit")


def record_admin_action(
    db: Session,
    *,
    admin_id: int | None,
    action: str,
    object_type: str,
    object_id: int | None = None,
    before: Any = None,
    after: Any = None,
) -> None:
    db.add(
        AdminAuditLog(
            admin_id=admin_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before,
            after=after,
            created_at=datetime.now(timezone.utc),
        )
    )
    logger.info(
        "admin_action admin=%s action=%s object=%s:%s",
        admin_id,
        action,
        object_type,
        object_id,
    )


def record_metric(db: Session, event: str, user_id: int | None = None) -> None:
    db.add(
        BetaMetric(
            event=event,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
    )
