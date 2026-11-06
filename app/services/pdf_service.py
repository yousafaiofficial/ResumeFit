import io
import re
from pypdf import PdfReader
from app.core.config import settings


def extract_pdf_text(data: bytes) -> str:
    """
    Extracts text from PDF bytes with defensive security checks:
    - Magic bytes validation
    - Password encryption detection
    - Hard page count limit (item 18)
    - Minimum readable characters check (detects scanned documents)
    """
    if not data.startswith(b"%PDF"):
        raise ValueError("Uploaded file is not a valid PDF document.")

    if len(data) > settings.MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds the maximum size limit of {settings.MAX_PDF_BYTES // (1024 * 1024)} MB.")

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        raise ValueError(f"Unable to parse PDF structure: {e}")

    if reader.is_encrypted:
        raise ValueError("This PDF is password-protected. Please remove the password and re-upload.")

    total_pages = len(reader.pages)
    if total_pages > settings.MAX_PDF_PAGES:
        raise ValueError(
            f"PDF has {total_pages} pages, exceeding the maximum allowed limit of {settings.MAX_PDF_PAGES} pages."
        )

    extracted_pages = []
    for page_num, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
            extracted_pages.append(page_text)
        except Exception:
            extracted_pages.append("")

    full_text = "\n".join(extracted_pages)
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()

    if len(full_text) < settings.MIN_RESUME_CHARS:
        raise ValueError(
            "No readable text found in PDF. Scanned images require OCR; please upload a text-based PDF or paste your resume text."
        )

    return full_text
