# DB connection & save logic
from sqlmodel import SQLModel, create_engine, Session
from app.models import ArxivPaper, Category
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)


def init_db():
    SQLModel.metadata.create_all(engine)


def save_papers(papers: list[dict]):
    with Session(engine) as session:
        for paper in papers:
            if session.query(ArxivPaper).filter_by(arxiv_id=paper["arxiv_id"]).first():
                continue
            new_paper = ArxivPaper(
                arxiv_id=paper["arxiv_id"],
                title=paper["title"],
                summary=paper["summary"],
                published=paper["published"],
                updated=paper["updated"],
                authors=", ".join(paper["authors"]),
                url=paper["url"],
                pdf_url=paper["pdf_url"],
            )

            # Add category entries
            categories = []
            for cat in paper["all_categories"]:
                categories.append(
                    Category(term=cat, is_primary=(cat == paper["primary_category"]))
                )
            new_paper.categories = categories

            session.add(new_paper)
        session.commit()
