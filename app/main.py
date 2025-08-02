# app/main.py

from fastapi import FastAPI
from datetime import datetime, timedelta
from app.arxiv import fetch_arxiv_papers

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "ResearchTLDR backend is alive!"}


@app.get("/arxiv/daily")
async def get_daily_arxiv():
    today = datetime.utcnow()
    yesterday = today - timedelta(days=2)

    start_date = yesterday.strftime("%Y%m%d0000")
    end_date = today.strftime("%Y%m%d2359")

    xml_data = await fetch_arxiv_papers(start_date, end_date)
    return {"raw_atom": xml_data}
