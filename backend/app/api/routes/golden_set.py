"""Human annotation endpoints, separate from all fact/relation approval paths."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_admin
from app.core.responses import success_response
from app.models import User
from app.schemas.golden_set import AnnotationIn, AuditIn, ExposureIn
from app.services.golden_set_service import GoldenSetService, get_golden_set_service

router = APIRouter(prefix="/admin/golden-set", tags=["Golden Set 人工标注"])


def _actor(admin):
    return f"{admin.id}:{admin.username}"


@router.get("")
def dataset(admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.dataset())


@router.put("/annotations/{source_id}")
def save_annotation(source_id: str, body: AnnotationIn, admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.save_annotation(source_id, body, _actor(admin)))


@router.post("/exposure/{source_id}")
def expose(source_id: str, body: ExposureIn, admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.expose(source_id, _actor(admin)))


@router.get("/metrics")
def metrics(admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.metrics())


@router.get("/export")
def export(admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.export())


@router.get("/audits/{kind}")
def audits(kind: str, admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.audits(kind))


@router.put("/audits/{kind}/{audit_id}")
def save_audit(kind: str, audit_id: str, body: AuditIn, admin: User = Depends(get_current_admin), service: GoldenSetService = Depends(get_golden_set_service)):
    return success_response(service.save_audit(kind, audit_id, body, _actor(admin)))
