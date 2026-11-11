import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.analysis import Analysis
from app.models.user import User
from app.schemas.analysis import AnalysisItemSummary, AnalysisResponse, PaginatedAnalysisHistory

router = APIRouter(prefix="/history", tags=["History"])


def _get_owned_analysis(db: Session, user: User, aid: int) -> Analysis:
    row = db.query(Analysis).filter_by(id=aid, user_id=user.id).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found or access denied.",
        )
    return row


@router.get("", response_model=PaginatedAnalysisHistory)
def list_history(
    limit: int = Query(20, ge=1, le=100, description="Number of items to retrieve"),
    cursor: int | None = Query(None, description="Cursor ID for pagination"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Paginated history list using cursor-based pagination (Item 20).
    Ordered by id descending.
    """
    query = db.query(Analysis).filter_by(user_id=user.id)
    if cursor is not None:
        query = query.filter(Analysis.id < cursor)

    # Fetch limit + 1 to check if more items exist
    rows = query.order_by(Analysis.id.desc()).limit(limit + 1).all()

    has_more = len(rows) > limit
    items_to_return = rows[:limit]
    next_cursor = items_to_return[-1].id if has_more and items_to_return else None

    summaries = [
        AnalysisItemSummary(
            id=r.id,
            job_title=r.job_title or "Untitled role",
            score=r.score,
            created_at=r.created_at.isoformat(),
        )
        for r in items_to_return
    ]

    return PaginatedAnalysisHistory(
        items=summaries,
        limit=limit,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{aid}", response_model=AnalysisResponse)
def get_history_detail(
    aid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves full analysis report by ID with ownership verification."""
    record = _get_owned_analysis(db, user, aid)
    parsed_result = json.loads(record.result_json)
    return AnalysisResponse(
        id=record.id,
        job_title=record.job_title,
        cached=False,
        created_at=record.created_at.isoformat(),
        **parsed_result,
    )


@router.delete("/{aid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_item(
    aid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes an analysis owned by the authenticated user (Item 27)."""
    record = _get_owned_analysis(db, user, aid)
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
