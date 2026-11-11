"""FastAPI router for Review APIs (Today's reviews, review submission, refresh)."""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Iterator
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.service.review_service import ReviewService
from app.repository.note_repository import NoteRepository

router = APIRouter(
    prefix="/review",
    tags=["Review API"]
)


def get_review_service() -> Iterator[ReviewService]:
    """Dependency provider for ReviewService."""
    note_repo = NoteRepository()
    try:
        yield ReviewService(note_repo=note_repo)
    finally:
        note_repo.db.close()


class ReviewSubmitRequest(BaseModel):
    section_id: int = Field(..., description="ID of the subtopic section reviewed")
    score: int = Field(..., ge=1, le=5, description="Self-assessed review score (1 to 5)")
    user_answer: Optional[str] = Field(None, description="User's answer to the review question")
    llm_feedback: Optional[str] = Field(None, description="LLM feedback or evaluation")


class ReviewSubmitResponse(BaseModel):
    status: str
    message: str


@router.get("/today", response_model=List[Dict[str, Any]])
def get_today_review(review_service: ReviewService = Depends(get_review_service)) -> List[Dict[str, Any]]:
    """
    Fetch all subtopics/sections scheduled for review today.
    """
    return review_service.get_due_reviews_for_today()


@router.post("/submit", response_model=ReviewSubmitResponse)
def submit_review(
    request: ReviewSubmitRequest,
    review_service: ReviewService = Depends(get_review_service)
) -> ReviewSubmitResponse:
    """
    Submit user's review result, log history, and advance the subtopic mastery stage.
    """
    try:
        review_service.submit_review_result(
            section_id=request.section_id,
            score=request.score,
            user_answer=request.user_answer,
            llm_feedback=request.llm_feedback
        )
        return ReviewSubmitResponse(
            status="success",
            message=f"Review result for section_id {request.section_id} recorded successfully."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/refresh", response_model=List[Dict[str, Any]])
def refresh_review(review_service: ReviewService = Depends(get_review_service)) -> List[Dict[str, Any]]:
    """
    Refresh and re-fetch today's review schedule.
    """
    return review_service.get_due_reviews_for_today()
