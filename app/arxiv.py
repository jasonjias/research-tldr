# app/arxiv.py

import httpx

ARXIV_API_URL = "https://export.arxiv.org/api/query"


async def fetch_arxiv_papers(start_date: str, end_date: str, start: int = 0):
    query = f"submittedDate:[{start_date} TO {end_date}]"
    params = {
        "search_query": query,
        "start": start,
        "max_results": 10,  # or more depending on your use
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(ARXIV_API_URL, params=params)
        response.raise_for_status()
        return response.text  # or `response.content` if you want bytes
