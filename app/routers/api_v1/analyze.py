import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import get_current_user
from app.models.analysis import Analysis
from app.models.user import User
from app.schemas.analysis import AnalysisResponse
from app.services.nlp_service import analyze, compute_content_hash
from app.services.pdf_service import extract_pdf_text

router = APIRouter(tags=["Analysis"])


@router.post("/analyze", response_model=AnalysisResponse)
@limiter.limit(settings.RATE_LIMIT_ANALYZE)
async def analyze_resume(
    request: Request,
    job_description: str = Form(...),
    job_title: str = Form(""),
    resume_text: str = Form(""),
    resume_file: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyzes resume against a job description.
    - Runs CPU-heavy PDF parsing and embedding scoring inside a threadpool (Item 12)
    - Enforces hard character and file size bounds (Item 18)
    - Checks content-hash cache to avoid duplicate inference costs (Item 19)
    """
    clean_jd = job_description.strip()
    if len(clean_jd) < settings.MIN_JOB_DESC_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Job description too short. Please provide at least {settings.MIN_JOB_DESC_CHARS} characters.",
        )
    if len(clean_jd) > settings.MAX_JOB_DESC_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Job description exceeds maximum limit of {settings.MAX_JOB_DESC_CHARS} characters.",
        )

    # Handle file upload or pasted text
    if resume_file and resume_file.filename:
        # Read file with size limit check
        file_bytes = await resume_file.read(settings.MAX_PDF_BYTES + 1)
        if len(file_bytes) > settings.MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"PDF file exceeds {settings.MAX_PDF_BYTES // (1024 * 1024)} MB limit.",
            )
        try:
            # Offload CPU-bound PDF extraction to worker thread
            clean_resume = await run_in_threadpool(extract_pdf_text, file_bytes)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract text from this PDF. Please verify it is not corrupted or scanned.",
            )
    else:
        clean_resume = resume_text.strip()
        if len(clean_resume) < settings.MIN_RESUME_CHARS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Resume text too short. Upload a PDF or paste at least {settings.MIN_RESUME_CHARS} characters.",
            )
        if len(clean_resume) > settings.MAX_RESUME_CHARS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Resume text exceeds maximum limit of {settings.MAX_RESUME_CHARS} characters.",
            )

    # Compute deterministic content hash for caching (Item 19)
    content_hash = compute_content_hash(clean_resume, clean_jd)

    # Check if identical analysis already exists for this user
    cached_record = (
        db.query(Analysis)
        .filter_by(user_id=user.id, content_hash=content_hash)
        .order_by(Analysis.created_at.desc())
        .first()
    )

    if cached_record:
        parsed_result = json.loads(cached_record.result_json)
        return AnalysisResponse(
            id=cached_record.id,
            job_title=cached_record.job_title,
            cached=True,
            created_at=cached_record.created_at.isoformat(),
            **parsed_result,
        )

    # Execute CPU-intensive NLP analysis in worker threadpool (Item 12)
    result = await run_in_threadpool(
        analyze,
        clean_resume[: settings.MAX_RESUME_CHARS],
        clean_jd[: settings.MAX_JOB_DESC_CHARS],
    )

    clean_title = (job_title or "").strip()[:200]
    row = Analysis(
        user_id=user.id,
        job_title=clean_title,
        score=result["score"],
        content_hash=content_hash,
        result_json=json.dumps(result),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return AnalysisResponse(
        id=row.id,
        job_title=row.job_title,
        cached=False,
        created_at=row.created_at.isoformat(),
        **result,
    )
