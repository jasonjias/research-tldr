# app/summarizer.py
# Word-count "summarizer" for development & wiring.
# Keeps all provenance fields (PDF hash, text hash, extraction tool/version).

import io
import hashlib
import httpx
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from pydantic import BaseModel
from pypdf import PdfReader

MAX_CHARS_PER_CHUNK = 6000  # unused here, but kept for compatibility

EXTRACTION_TOOL = "pypdf"
try:
    EXTRACTION_TOOL_VERSION = PdfReader.__version__
except Exception:
    EXTRACTION_TOOL_VERSION = "unknown"

ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _normalize_pdf_url(url: str) -> str:
    # Force HTTPS for arXiv (avoids 301 and some CDN quirks)
    try:
        p = urlparse(url)
        if p.netloc in ARXIV_HOSTS and p.scheme != "https":
            p = p._replace(scheme="https")
            return urlunparse(p)
    except Exception:
        pass
    return url


async def _download_pdf(pdf_url: str) -> bytes:
    url = _normalize_pdf_url(pdf_url)
    # httpx defaults to NOT following redirects; set follow_redirects=True.
    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": "ResearchTLDR/1.0 (+https://researchtldr.com)"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        # Some servers return HTML on error pages; quick sanity check.
        ctype = r.headers.get("content-type", "")
        if "application/pdf" not in ctype and not url.endswith(".pdf"):
            # arXiv serves PDFs without .pdf; allow if header says pdf, else raise.
            if "application/pdf" not in ctype:
                raise RuntimeError(f"Expected PDF, got Content-Type={ctype} for {url}")
        return r.content


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages).replace("\r", "")


def _count_words(text: str) -> int:
    # Simple, deterministic word counter
    # Splits on whitespace and filters out empties
    if not text:
        return 0
    return sum(1 for tok in text.split() if tok.strip())


class SummarizationResult(BaseModel):
    summary_text: str
    summary_model: str
    summary_updated_at: datetime
    summary_pdf_sha256: str
    extracted_text_sha256: Optional[str] = None
    extraction_tool: Optional[str] = None
    extraction_tool_version: Optional[str] = None
    normalization_spec: Optional[Dict[str, Any]] = None
    extracted_text_url: Optional[str] = None  # if you upload the text elsewhere


async def summarize_pdf_url(pdf_url: str) -> SummarizationResult:
    # 1) Download and fingerprint the raw PDF
    pdf_bytes = await _download_pdf(pdf_url)
    pdf_hash = _sha256_bytes(pdf_bytes)

    # 2) Extract text (simple deterministic pass) + fingerprint
    extracted_text = _extract_text_from_pdf(pdf_bytes)
    text_hash = _sha256_text(extracted_text) if extracted_text else None

    # 3) "Summarize" by reporting the word count
    wc = _count_words(extracted_text)
    summary_text = f"Word count: {wc}"

    return SummarizationResult(
        summary_text=summary_text,
        summary_model="wordcount-v1",
        summary_updated_at=datetime.utcnow(),
        summary_pdf_sha256=pdf_hash,
        extracted_text_sha256=text_hash,
        extraction_tool=EXTRACTION_TOOL,
        extraction_tool_version=EXTRACTION_TOOL_VERSION,
        normalization_spec={
            "unicode": "as-is",
            "unwrap_hyphenation": False,
            "collapse_whitespace": False,
        },
    )
