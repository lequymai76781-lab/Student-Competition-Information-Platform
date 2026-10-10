"""Administrator-only blind review observation and offline learning datasets."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_current_admin, get_db
from app.core.responses import success_response
from app.services import review_learning_service as learning

router = APIRouter(prefix='/admin/review-learning', tags=['人机共审学习'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class StartIn(Strict):
    candidate_id: int = Field(gt=0)


class EventIn(Strict):
    event: Literal['source_open', 'decision', 'submit']
    details: dict | None = None


class CompleteIn(Strict):
    human_primary_type: Literal['participation','result','information','policy','update','repost','other']
    human_secondary_type: str | None = Field(default=None, max_length=100)
    human_risk_level: Literal['LOW_RISK','NORMAL','HIGH_RISK'] | None = None


class CorrectIn(Strict):
    human_ground_truth: CompleteIn
    reason: str = Field(min_length=1, max_length=3000)


class BatchIn(Strict):
    min_samples: Literal[100,300,500] = 100


def _call(operation):
    try:
        return success_response(operation())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, '学习记录不存在') from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/config')
def config(admin=Depends(get_current_admin), db=Depends(get_db)):
    learning.require_admin(db, admin)
    return _call(lambda: learning.learning_config(db))


@router.post('/sessions')
def start(payload: StartIn, admin=Depends(get_current_admin), db=Depends(get_db)):
    return _call(lambda: learning.start_learning(db, admin, payload.candidate_id))


@router.post('/sessions/{session_id}/events')
def event(session_id: str, payload: EventIn, admin=Depends(get_current_admin), db=Depends(get_db)):
    return _call(lambda: learning.learning_event(db, admin, session_id, payload.event, payload.details))


@router.post('/sessions/{session_id}/complete')
def complete(session_id: str, payload: CompleteIn, admin=Depends(get_current_admin), db=Depends(get_db)):
    return _call(lambda: learning.complete_learning(db, admin, session_id, payload.model_dump()))


@router.get('/performance')
def performance(admin=Depends(get_current_admin), db=Depends(get_db)):
    from app.services.review_learning_metrics import performance as summarize
    def operation():
        learning.require_admin(db, admin)
        store, _ = learning.learning_store(db)
        report = summarize(store.examples())
        return {**report, **learning.learning_config(db),
            'status': 'ready_for_evaluation' if report['sample_count'] >= 100 else 'observing'}
    return _call(operation)


@router.get('/examples')
def examples(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
             admin=Depends(get_current_admin), db=Depends(get_db)):
    def operation():
        learning.require_admin(db, admin)
        store, _ = learning.learning_store(db)
        rows = list(reversed(store.examples(active_only=False)))
        return {'items': rows[offset:offset+limit], 'total': len(rows)}
    return _call(operation)


@router.post('/examples/{example_id}/correct')
def correct(example_id: str, payload: CorrectIn, admin=Depends(get_current_admin), db=Depends(get_db)):
    return _call(lambda: learning.correct_learning(db, admin, example_id,
        payload.human_ground_truth.model_dump(exclude_unset=True), payload.reason))


@router.get('/batches')
def batches(admin=Depends(get_current_admin), db=Depends(get_db)):
    def operation():
        learning.require_admin(db, admin)
        store, _ = learning.learning_store(db)
        return {'items': [{**batch, 'status': 'ready_for_evaluation'} for batch in store.batches()]}
    return _call(operation)


@router.post('/batches')
def create_batch(payload: BatchIn, admin=Depends(get_current_admin), db=Depends(get_db)):
    def operation():
        learning.require_admin(db, admin)
        store, runtime = learning.learning_store(db)
        if runtime['mode'] != 'human':
            raise HTTPException(403, '自动化操作不能封存真实训练批次')
        return {**store.create_batch(min_samples=payload.min_samples), 'status': 'ready_for_evaluation'}
    return _call(operation)


@router.post('/replay')
def replay(admin=Depends(get_current_admin), db=Depends(get_db)):
    from app.services.review_learning_metrics import replay_examples
    def operation():
        learning.require_admin(db, admin)
        store, _ = learning.learning_store(db)
        return replay_examples(store.examples())
    return _call(operation)
