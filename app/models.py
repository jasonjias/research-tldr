# SQLModel definitions
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class ArxivPaper(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    arxiv_id: str
    title: str
    summary: str
    published: datetime
    published_raw: Optional[str] = None
    updated: datetime
    updated_raw: Optional[str] = None
    authors: str  # comma-separated string
    url: str
    pdf_url: Optional[str]
