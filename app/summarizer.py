# app/summarizer.py
import io, hashlib, os, re, unicodedata
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
from pydantic import BaseModel
from pypdf import PdfReader
from openai import OpenAI

SUMMARY_MODEL = "gpt-4o-mini"
PROMPT_PATH = os.getenv("SUMMARY_PROMPT_PATH", "app/prompts/summarize_v1.txt")
MAX_CHARS_PER_CHUNK = int(os.getenv("SUMMARY_MAX_CHARS_PER_CHUNK", "6000"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}

def _normalize_pdf_url(url: str) -> str:
    from urllib.parse import urlparse, urlunparse
    p = urlparse(url)
    if p.netloc in ARXIV_HOSTS and p.scheme != "https":
        p = p._replace(scheme="https")
        return urlunparse(p)
    return url

async def _download_pdf(pdf_url: str) -> bytes:
    url = _normalize_pdf_url(pdf_url)
    async with httpx.AsyncClient(
        timeout=60, follow_redirects=True,
        headers={"User-Agent":"ResearchTLDR/1.0 (+https://researchtldr.com)"}
    ) as http:
        r = await http.get(url)
        r.raise_for_status()
        return r.content

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages).replace("\r","")

def _normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).replace("\u00AD","")  # drop soft hyphens
    t = re.sub(r"-\s*\n\s*", "", t)    # de-hyphenate across newlines
    t = re.sub(r"\s*\n\s*", " ", t)    # join lines
    t = re.sub(r"\s+", " ", t).strip() # collapse spaces
    return t

def _chunk_text(s: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    if len(s) <= max_chars:
        return [s]
    return [s[i:i+max_chars] for i in range(0, len(s), max_chars)]

def _load_system_prompt() -> str:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()

def _make_user_prompt(meta: Dict[str, Any], text: str) -> str:
    return (
        "Paper metadata:\n"
        f"title: {meta.get('title','')}\n"
        f"authors: {', '.join(meta.get('authors',[]))}\n"
        f"venue: {meta.get('venue','')}\n"
        f"year: {meta.get('year','')}\n"
        f"doi: {meta.get('doi','')}\n"
        f"arxiv_id: {meta.get('arxiv_id','')}\n"
        f"url: {meta.get('url','')}\n"
        f"pdf_url: {meta.get('pdf_url','')}\n\n"
        "Paper text (concatenated, normalized):\n"
        f"{text}\n\n"
        "Return ONLY the JSON per the required schema."
    )

class SummarizationResult(BaseModel):
    summary_text: str           # JSON string (as returned by model)
    summary_model: str
    summary_updated_at: datetime
    summary_pdf_sha256: str
    extracted_text_sha256: Optional[str] = None

async def summarize_pdf_url_to_json(pdf_url: str, meta: Dict[str, Any]) -> SummarizationResult:
    # 1) Download + hash
    pdf_bytes = await _download_pdf(pdf_url)
    pdf_hash = _sha256_bytes(pdf_bytes)

    # 2) Extract + normalize
    raw_text = _extract_text_from_pdf(pdf_bytes)
    norm_text = _normalize_text(raw_text)
    text_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest() if norm_text else None

    # 3) Chunk (single-request merge for now)
    chunks = _chunk_text(norm_text)
    combined_text = "\n\n".join(chunks)

    # 4) LLM call
    system_prompt = _load_system_prompt()
    user_prompt = _make_user_prompt(meta, combined_text)

    resp = client.responses.create(
        model=SUMMARY_MODEL,
        input=[
            {"role":"system","content":system_prompt},
            {"role":"user","content":user_prompt},
        ],
        temperature=0.2,
    )
    output_text = resp.output_text.strip()

    # 5) Be tolerant if model returns extra text around JSON
    first = output_text.find("{")
    last = output_text.rfind("}")
    json_text = output_text[first:last+1] if first != -1 and last != -1 else "{}"

    return SummarizationResult(
        summary_text=json_text,
        summary_model=SUMMARY_MODEL,
        summary_updated_at=datetime.utcnow(),
        summary_pdf_sha256=pdf_hash,
        extracted_text_sha256=text_hash,
    )
