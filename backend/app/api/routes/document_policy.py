"""Admin-only source classification and policy automation over saved evidence."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_current_admin, get_db
from app.core.responses import success_response
from app.models import User
from app.schemas.document_policy import ClassificationCorrectionIn, DocumentPolicyActionIn, PolicyMatchConfirmationIn
from app.services.document_policy_service import DocumentPolicyService, PolicyAutomationService

router=APIRouter(prefix='/admin/document-policy',tags=['来源分类与政策名单'])

def _write(db, operation):
    try:
        result=operation();db.commit();return success_response(result)
    except Exception:
        db.rollback();raise

@router.get('')
def list_sources(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),admin:User=Depends(get_current_admin),db:Session=Depends(get_db)):
    return success_response(DocumentPolicyService.list_sources(db,limit=limit,offset=offset))

@router.post('/replay-classification')
def replay(body:DocumentPolicyActionIn,admin:User=Depends(get_current_admin),db:Session=Depends(get_db)):
    return _write(db,lambda:DocumentPolicyService.replay(db,admin=admin))

@router.get('/policies')
def policies(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),admin:User=Depends(get_current_admin),db:Session=Depends(get_db)):
    return success_response(PolicyAutomationService.list_policies(db,limit=limit,offset=offset))

@router.post('/policies/{identity}/analyze')
def analyze(identity:int,body:DocumentPolicyActionIn,admin:User=Depends(get_current_admin),db:Session=Depends(get_db)):
    return _write(db,lambda:PolicyAutomationService.analyze(db,identity,admin=admin))

@router.put('/{identity}/classification')
def correct(identity:int,body:ClassificationCorrectionIn,admin:User=Depends(get_current_admin),db:Session=Depends(get_db)):
    return _write(db,lambda:DocumentPolicyService.correct_classification(db,identity,body.document_type,body.reason,admin=admin))

@router.put('/policies/{identity}/matches')
def confirm_match(identity:int,body:PolicyMatchConfirmationIn,admin:User=Depends(get_current_admin),db:Session=Depends(get_db)):
    return _write(db,lambda:PolicyAutomationService.confirm_match(db,identity,body.raw_competition_name,body.competition_id,body.reason,admin=admin))
