# app/models.py
from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint
from sqlalchemy import Column
from sqlalchemy.types import JSON
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
    authors: str
    url: str
    pdf_url: Optional[str]
    categories: List[Category] = Relationship(back_populates="paper")


class UserSettings(SQLModel, table=True):
    user_sub: str = Field(primary_key=True, foreign_key="user.sub")
    # map dict -> JSON column
    prefs: dict = Field(sa_column=Column(JSON, nullable=False, server_default='{}'))
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    # Google sub is globally unique & stable
    sub: str = Field(primary_key=True)
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None


class Bookmark(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_sub: str = Field(foreign_key="user.sub")
    paper_id: int = Field(foreign_key="arxivpaper.id")
    __table_args__ = (
        UniqueConstraint("user_sub", "paper_id", name="uq_bookmark_user_paper"),
    )


class Vote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_sub: str = Field(foreign_key="user.sub")
    paper_id: int = Field(foreign_key="arxivpaper.id")
    value: int = Field(default=0)  # -1, 0, or +1
    __table_args__ = (
        UniqueConstraint("user_sub", "paper_id", name="uq_vote_user_paper"),
    )
