# app/arxiv.py
# fetch + parse arXiv data
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime

ARXIV_API_URL = "https://export.arxiv.org/api/query"


async def fetch_arxiv_papers(
    start_date: str, end_date: str, start: int = 0, max_results: int = 100
):
    query = f"submittedDate:[{start_date} TO {end_date}]"
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(ARXIV_API_URL, params=params)
        response.raise_for_status()
        return parse_arxiv_xml(response.text)


def parse_arxiv_xml(xml_data: str):
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(xml_data)
    entries = []

    for entry in root.findall("atom:entry", ns):
        arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]
        title = entry.find("atom:title", ns).text.strip()
        # summary = entry.find("atom:summary", ns).text.strip()
        summary = "".join(entry.find("atom:summary", ns).itertext()).strip()

        import sys

        print("RAW:", entry.find("atom:summary", ns).text, file=sys.stderr)
        print("FULL:", "".join(entry.find("atom:summary", ns).itertext()).strip())

        published_raw = entry.find("atom:published", ns).text
        updated_raw = entry.find("atom:updated", ns).text
        published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        updated = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))

        authors = [
            a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)
        ]

        links = entry.findall("atom:link", ns)
        url = None
        pdf_url = None
        for link in links:
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib["href"]
            elif link.attrib.get("rel") == "alternate":
                url = link.attrib["href"]

        # Primary and all categories
        primary_category = entry.find("arxiv:primary_category", ns).attrib["term"]
        all_categories = [c.attrib["term"] for c in entry.findall("atom:category", ns)]

        entries.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "published": published,
                "updated": updated,
                "authors": authors,
                "url": url,
                "pdf_url": pdf_url,
                "primary_category": primary_category,
                "all_categories": all_categories,
            }
        )

    return entries
