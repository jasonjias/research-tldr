# app/summarize_runner.py
from sqlmodel import Session, select
from app.db import engine
from app.models import ArxivPaper
from app.summarizer import summarize_pdf_url_to_json

async def summarize_missing_papers(limit: int = 10) -> int:
    updated = 0
    with Session(engine) as session:
        q = (
            select(ArxivPaper)
            .where((ArxivPaper.llm_summary.is_(None)) | (ArxivPaper.summary_pdf_sha256.is_(None)))
            .order_by(ArxivPaper.published.desc())
            .limit(limit)
        )
        papers = session.exec(q).all()

        for p in papers:
            if p.summary_pdf_sha256:  # already summarized this exact PDF
                continue

            try:
                meta = {
                    "title": p.title,
                    "authors": p.authors.split(",") if p.authors else [],
                    "venue": "",         # arXiv doesn’t provide; keep blank
                    "year": p.published.year if p.published else None,
                    "doi": "",           # if you store DOI, put it here
                    "arxiv_id": p.arxiv_id,
                    "url": p.url,
                    "pdf_url": p.pdf_url,
                }
                res = await summarize_pdf_url_to_json(p.pdf_url, meta)

                p.llm_summary = res.summary_text         # store JSON string
                p.summary_model = res.summary_model
                p.summary_updated_at = res.summary_updated_at
                p.summary_pdf_sha256 = res.summary_pdf_sha256

                # optional provenance if you added columns:
                if hasattr(p, "extracted_text_sha256"):
                    p.extracted_text_sha256 = res.extracted_text_sha256

                session.add(p)
                session.commit()
                updated += 1
            except Exception as e:
                print(f"[summarize_missing_papers] {p.id or p.title} failed: {e}")
                session.rollback()
    return updated
