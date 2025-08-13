#!/usr/bin/env python3
"""
Usage:
  python test_summarizer.py path/to/paper.txt --model gpt-4o-mini --out summary.json --max-chars 6000

Env:
  OPENAI_API_KEY must be set.

Notes:
  - This script does not fetch PDFs. Feed it plain text you extracted (or a small excerpt) for quick testing.
  - Output is validated to match the expected JSON shape (lightweight checks).
"""

import os
import sys
import json
import argparse
import re
import unicodedata
from typing import List, Dict, Any
from dotenv import load_dotenv

# Requires: pip install openai>=1.40.0
try:
    from openai import OpenAI
except Exception as e:
    print("ERROR: You need 'openai>=1.40.0' installed. pip install openai>=1.40.0", file=sys.stderr)
    raise

load_dotenv()

SYSTEM_PROMPT = """You are an AI that summarizes academic papers into a JSON object. Follow this structure and rules exactly.

## OUTPUT FORMAT
{
  "tldr": "1-2 sentences, ≤60 words. Plain English.",
  "whats_new": ["• 2-4 short bullets on novelty."],
  "method": "2-4 sentences describing the approach.",
  "results": ["• 3-6 bullets, each a single key finding with numbers if available."],
  "limitations": ["• 2-4 short bullets on weaknesses or open questions."],
  "why_useful": "2-3 sentences explaining why the paper matters, possible applications, and relevance to the reader.",
  "provenance": {
    "page_citations": ["p. 3", "p. 5"],  // only if page mapping is clear
    "code_data_availability": "e.g., 'Code & data available at URL' or 'Not provided'."
  }
}

## REQUIREMENTS
1. **Grounding**: Use only information in the provided text. If a fact is missing, omit it or mark as `"unknown"`.
2. **Numbers**: Include exact metrics & units if present (e.g., "↑ 1.7 BLEU", "95% CI ±0.3").
3. **Clarity**: Short sentences. Avoid jargon when simpler terms work.
4. **Concision targets**:
   - TL;DR: 1-2 sentences, ≤60 words.
   - What's new: 2-4 bullets.
   - Method: 2-4 sentences.
   - Results: 3-6 bullets with numbers if available.
   - Limitations: 2-4 bullets.
   - Why useful: 2-3 sentences.
5. **Comparisons**: If baselines or prior work are named, mention them briefly (e.g., “outperforms X by Y% on Z”).
6. **Theoretical papers**: Emphasize problem setting, main theorems, conditions, assumptions, and implications.
7. **Reproducibility**: State if code/data is available and any notes about reproducibility.
8. **Safety/Ethics**: Only include if the paper itself discusses them.
9. **Citations**: When possible, add (page numbers) for specific claims in `provenance.page_citations`.
10. **Validity**: Output MUST be valid JSON and match the schema exactly—no extra keys.

FAIL-SAFES
- If extractable text is too sparse (<500 characters) or unreadable, return this JSON with empty fields and set:
  - summary.tldr = "Insufficient text to summarize."
  - classification.confidence = 0.0
  - reproducibility = ["Insufficient text"]
- If unsure about any field, use empty string/array rather than hallucinating.

TONE
- Neutral, precise, compact. No marketing language.

Now read the paper text chunks (in reading order) and produce the JSON."""

EXPECTED_SCHEMA = {
    "meta": {
        "title": str,
        "authors": list,
        "venue": str,
        "year": (int, type(None)),
        "doi": str,
        "arxiv_id": str,
        "url": str,
        "pdf_url": str,
    },
    "classification": {
        "paper_type": str,
        "area_tags": list,
        "novelty_level": str,
        "confidence": (int, float),
    },
    "summary": {
        "tldr": str,
        "whats_new": list,
        "method": str,
        "evidence_setup": list,
        "results": list,
        "limitations": list,
        "risks_ethics": list,
        "reproducibility": list,
        "audience_fit": list,
        "practical_takeaway": str,
    },
    "provenance": {
        "page_citations": list,
        "extracted_text_sha256": str,
        "summary_model": str,
        "summary_prompt_version": str,
    },
}

def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).replace("\u00AD", "")
    # de-hyphenate across newlines
    t = re.sub(r"-\s*\n\s*", "", t)
    # replace all newlines with single spaces
    t = re.sub(r"\s*\n\s*", " ", t)
    # collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t

def chunk_text(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+max_chars])
        i += max_chars
    return chunks

def make_user_prompt(meta: Dict[str, Any], text: str) -> str:
    return (
        "Paper metadata:\n"
        f"title: {meta.get('title', '')}\n"
        f"authors: {', '.join(meta.get('authors', []))}\n"
        f"venue: {meta.get('venue', '')}\n"
        f"year: {meta.get('year', '')}\n"
        f"doi: {meta.get('doi', '')}\n"
        f"arxiv_id: {meta.get('arxiv_id', '')}\n"
        f"url: {meta.get('url', '')}\n"
        f"pdf_url: {meta.get('pdf_url', '')}\n\n"
        "Paper text (concatenated, normalized):\n"
        f"{text}\n\n"
        "Return ONLY the JSON per the required schema."
    )

def validate_shape(obj: Dict[str, Any]) -> None:
    # Lightweight shape check
    def check_section(section_name: str, schema: Dict[str, Any]):
        if section_name not in obj:
            raise ValueError(f"Missing top-level key: {section_name}")
        section = obj[section_name]
        if not isinstance(section, dict):
            raise ValueError(f"Section '{section_name}' must be an object")
        for k, expected_type in schema.items():
            if k not in section:
                raise ValueError(f"Missing key '{k}' in section '{section_name}'")
            if expected_type == list:
                if not isinstance(section[k], list):
                    raise ValueError(f"Key '{section_name}.{k}' must be a list")
            elif expected_type == dict:
                if not isinstance(section[k], dict):
                    raise ValueError(f"Key '{section_name}.{k}' must be an object")
            else:
                if not isinstance(section[k], expected_type):
                    raise ValueError(f"Key '{section_name}.{k}' must be {expected_type}, got {type(section[k])}")
    for name, schema in EXPECTED_SCHEMA.items():
        check_section(name, schema)

def main():
    parser = argparse.ArgumentParser(description="Test ResearchTLDR summarization system prompt locally.")
    parser.add_argument("file", help="Path to a .txt file with paper text")
    parser.add_argument("--model", default=os.getenv("SUMMARY_MODEL", "gpt-4o-mini"), help="OpenAI model (default: gpt-4o-mini)")
    parser.add_argument("--max-chars", type=int, default=int(os.getenv("SUMMARY_MAX_CHARS_PER_CHUNK", "6000")), help="Max chars per chunk")
    parser.add_argument("--out", default="summary.json", help="Where to write JSON output")
    parser.add_argument("--title", default="")
    parser.add_argument("--authors", default="", help="Comma-separated authors")
    parser.add_argument("--venue", default="")
    parser.add_argument("--year", type=int, default=0)
    parser.add_argument("--doi", default="")
    parser.add_argument("--arxiv_id", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--pdf_url", default="")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: Set OPENAI_API_KEY in your environment.", file=sys.stderr)
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        raw = f.read()

    text = normalize_text(raw)
    chunks = chunk_text(text, args.max_chars)

    meta = {
        "title": args.title,
        "authors": [a.strip() for a in args.authors.split(",") if a.strip()] if args.authors else [],
        "venue": args.venue,
        "year": args.year if args.year else None,
        "doi": args.doi,
        "arxiv_id": args.arxiv_id,
        "url": args.url,
        "pdf_url": args.pdf_url,
    }

    # Combine chunks into one message for now (you can do multi-turn later if needed)
    content = make_user_prompt(meta, "\n\n".join(chunks))

    client = OpenAI(api_key=api_key)

    print(f"> Calling model={args.model} on {args.file} (chars={len(text)}, chunks={len(chunks)})...")
    resp = client.responses.create(
        model=args.model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.2,
    )

    output_text = resp.output_text.strip()
    # Ensure it's pure JSON (some models add leading/trailing junk)
    try:
        first_brace = output_text.find("{")
        last_brace = output_text.rfind("}")
        json_text = output_text[first_brace:last_brace+1]
        data = json.loads(json_text)
    except Exception as e:
        print("Raw model output (truncated to 1k chars):")
        print(output_text[:1000])
        raise RuntimeError(f"Failed to parse model JSON: {e}")

    # Validate the shape
    try:
        validate_shape(data)
        ok = True
    except Exception as e:
        ok = False
        print(f"WARNING: JSON shape validation failed: {e}", file=sys.stderr)

    # Attach minimal provenance if missing
    data.setdefault("provenance", {})
    data["provenance"].setdefault("summary_model", args.model)
    data["provenance"].setdefault("summary_prompt_version", "v1")

    # Write output
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {args.out} | valid_shape={ok}")
    # Pretty-print TL;DR for convenience
    try:
        print("\nTL;DR:", data["summary"]["tldr"])
    except Exception:
        pass

if __name__ == "__main__":
    main()
