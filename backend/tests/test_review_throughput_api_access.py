"""Actual HTTP auth boundaries for the review throughput endpoints."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_db
from app.api.routes.field_reviews import router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.security import create_token
from app.models import AdminAuditLog, ReviewQueue, User

CASES = [
    ("GET", "/statistics", None),
    ("GET", "?risk=HIGH_RISK&relation_type=registration_notice&sort=priority", None),
    ("GET", "/999999", None),
    ("GET", "/999999/sources", None),
    ("GET", "/999999/audit", None),
    ("POST", "/bulk-preview", {"items":[{"id":999999,"preview_token":"not-a-token","field_names":["frequency"]}],"note":"auth test"}),
    ("POST", "/bulk-review", {"items":[{"id":999999,"preview_token":"not-a-token","field_names":["frequency"]}],"note":"auth test"}),
    ("POST", "/999999/timing/start", {"mode":"automation"}),
    ("POST", "/999999/timing/event", {"session_id":"not-a-session","event":"source_open"}),
    ("PUT", "/999999/relation/prepare", {"preview_token":"not-a-token","note":"auth test","year":2025}),
    ("POST", "/999999/relation/verify-source", {"preview_token":"not-a-token","note":"auth test"}),
    ("POST", "/999999/relation/review", {"preview_token":"not-a-token","note":"auth test","action":"approve"}),
]

@pytest.mark.parametrize("method,path,body",CASES)
@pytest.mark.parametrize("actor",["anonymous","ordinary","inactive_admin"])
def test_throughput_routes_reject_unprivileged_http_clients(db_session,method,path,body,actor):
    app=FastAPI()
    app.include_router(router,prefix="/api")
    register_exception_handlers(app)
    app.dependency_overrides[get_db]=lambda:db_session
    headers={}
    if actor!="anonymous":
        user=User(username="accesscheck",email="accesscheck@example.test",hashed_password="fixture",
            is_admin=actor=="inactive_admin",is_active=actor!="inactive_admin")
        db_session.add(user);db_session.commit()
        headers={"Authorization":"Bearer "+create_token(user.id,get_settings().app_secret)}
    before=(db_session.scalar(select(func.count()).select_from(ReviewQueue)),
            db_session.scalar(select(func.count()).select_from(AdminAuditLog)))
    with TestClient(app) as client:
        response=client.request(method,"/api/admin/field-reviews"+path,headers=headers,
            **({"json":body} if body is not None else {}))
    assert response.status_code==403,response.text
    assert "999999" not in response.text
    assert before==(db_session.scalar(select(func.count()).select_from(ReviewQueue)),
                    db_session.scalar(select(func.count()).select_from(AdminAuditLog)))

