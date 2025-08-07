# app/main.py
# FastAPI routes

from fastapi import FastAPI, Request
from datetime import datetime, timedelta
from sqlmodel import Session, select
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.arxiv import fetch_arxiv_papers
from app.db import init_db, save_papers, engine
from app.models import ArxivPaper

app = FastAPI()
templates = Jinja2Templates(directory="templates")
init_db()


@app.get("/arxiv/daily")
async def get_daily_arxiv():
    today = datetime.utcnow()
    yesterday = today - timedelta(days=3)
    start = yesterday.strftime("%Y%m%d0000")
    end = today.strftime("%Y%m%d2359")

    parsed = await fetch_arxiv_papers(start, end)
    save_papers(parsed)
    return {"stored": len(parsed)}


@app.get("/arxiv/show")
def show_papers():
    with Session(engine) as session:
        stmt = select(ArxivPaper).order_by(ArxivPaper.published.desc()).limit(10)
        papers = session.exec(stmt).all()
        return papers


@app.get("/", response_class=HTMLResponse)
def html_view(request: Request):
    with Session(engine) as session:
        stmt = select(ArxivPaper).order_by(ArxivPaper.published.desc()).limit(50)
        papers = session.exec(stmt).all()
        return templates.TemplateResponse("papers.html", {"request": request, "papers": papers})
