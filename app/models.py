# SQLModel definitions
from sqlmodel import SQLModel, Field, Relationship
from typing import List, Optional
from datetime import datetime

class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    term: str
    is_primary: bool = False
    paper_id: Optional[int] = Field(default=None, foreign_key="arxivpaper.id")

    paper: Optional["ArxivPaper"] = Relationship(back_populates="categories")


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

    categories: List[Category] = Relationship(back_populates="paper")

Category.paper = Relationship(back_populates="categories")