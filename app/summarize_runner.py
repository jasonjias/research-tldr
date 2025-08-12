# app/summarize_runner.py
# Helper routine to find unsummarized papers and attach the "summary" (word count).

from sqlmodel import Session, select
from app.db import engine
from app.models import ArxivPaper
from app.summarizer import summarize_pdf_url


async def summarize_missing_papers(limit: int = 10) -> int:
    updated = 0
    with Session(engine) as session:
        q = (
            select(ArxivPaper)
            .where(
                (ArxivPaper.llm_summary.is_(None))
                | (ArxivPaper.summary_pdf_sha256.is_(None))
            )
            .order_by(ArxivPaper.published.desc())
            .limit(limit)
        )
        papers = session.exec(q).all()

        for p in papers:
            if p.summary_pdf_sha256:
                continue  # already summarized this exact PDF
            try:
                res = await summarize_pdf_url(p.pdf_url)
                p.llm_summary = res.summary_text
                p.summary_model = res.summary_model
                p.summary_updated_at = res.summary_updated_at
                p.summary_pdf_sha256 = res.summary_pdf_sha256
                if hasattr(p, "extracted_text_sha256"):
                    p.extracted_text_sha256 = res.extracted_text_sha256
                if hasattr(p, "extraction_tool"):
                    p.extraction_tool = res.extraction_tool
                if hasattr(p, "extraction_tool_version"):
                    p.extraction_tool_version = res.extraction_tool_version
                if hasattr(p, "normalization_spec"):
                    p.normalization_spec = res.normalization_spec
                session.add(p)
                session.commit()
                updated += 1
            except Exception as e:
                print(f"[summarize_missing_papers] {p.id or p.title} failed: {e}")
                session.rollback()
    return updated
