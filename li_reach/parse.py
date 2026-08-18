# -*- coding: utf-8 -*-
"""Best-effort parsing of the raw innerText the LinkedIn MCP returns.

`mcp-server-linkedin` intentionally returns raw page text for an LLM to read,
not clean structured records. So everything here is heuristic and defensive:
we extract what we can and always fall back to a usable job link. Keyword
filtering/ranking never depends on this parsing being perfect — it runs over
the full raw text (see models.Job.haystack).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .models import Job, Post

_WS = re.compile(r"[ \t]+")
# A "Company · Location · 2 days ago" style meta line.
_DOT = "·"


def _clean_lines(text: str) -> List[str]:
    lines = []
    for line in (text or "").splitlines():
        line = _WS.sub(" ", line).strip()
        if line:
            lines.append(line)
    return lines


def parse_job_detail(result: Dict[str, Any], job_id: str, source_query: str) -> Job:
    """Turn a `get_job_details` result into a Job with best-effort fields."""
    sections = result.get("sections") or {}
    text = "\n".join(str(v) for v in sections.values())
    lines = _clean_lines(text)

    title = _guess_title(lines)
    company, location, posted = _guess_company_location(lines)
    work_type = _guess_work_type(text)

    return Job(
        job_id=str(job_id),
        title=title,
        company=company,
        location=location,
        posted=posted,
        work_type=work_type,
        url=result.get("url"),
        source_query=source_query,
        raw=text,
        enriched=True,
    )


def _guess_title(lines: List[str]) -> Optional[str]:
    """Title is usually one of the first substantive lines without a dot-meta."""
    for line in lines[:6]:
        low = line.lower()
        if _DOT in line:
            continue
        if any(skip in low for skip in ("linkedin", "sign in", "applicants", "ago")):
            continue
        if 2 <= len(line) <= 120:
            return line
    return lines[0] if lines else None


def _guess_company_location(lines: List[str]):
    """Find a 'Company · Location · posted' meta line and split it."""
    for line in lines[:12]:
        if _DOT in line:
            parts = [p.strip() for p in line.split(_DOT) if p.strip()]
            if not parts:
                continue
            company = parts[0]
            location = parts[1] if len(parts) > 1 else None
            posted = None
            for p in parts[2:]:
                if "ago" in p.lower() or "week" in p.lower() or "day" in p.lower():
                    posted = p
                    break
            return company, location, posted
    return None, None, None


def _guess_work_type(text: str) -> Optional[str]:
    low = text.lower()
    for label in ("remote", "hybrid", "on-site", "on site"):
        if label in low:
            return "on_site" if label.startswith("on") else label
    return None


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

def parse_posts(result: Dict[str, Any], source_query: str) -> List[Post]:
    """Split a `search_posts` result into individual Post records.

    search_posts returns one big `search_results` text blob plus a
    `references` list (authors, companies, linked jobs). The blob has no
    per-post permalinks, so we segment on blank-line gaps and attach any
    reference URLs we can match by author name.
    """
    sections = result.get("sections") or {}
    blob = "\n".join(str(v) for v in sections.values())
    references = result.get("references") or []

    ref_urls = _index_reference_urls(references)

    posts: List[Post] = []
    for chunk in _segment_posts(blob):
        lines = _clean_lines(chunk)
        if not lines:
            continue
        author = lines[0] if len(lines[0]) <= 100 else None
        role = _guess_headline(lines)
        posted = _guess_posted(lines)
        url = None
        if author:
            url = ref_urls.get(author.lower())
        posts.append(
            Post(
                body=chunk.strip(),
                author=author,
                role=role,
                posted=posted,
                url=url,
                source_query=source_query,
            )
        )
    return posts


def _segment_posts(blob: str) -> List[str]:
    """Break the results blob into per-post chunks on blank-line boundaries."""
    if not blob.strip():
        return []
    chunks, current = [], []
    for line in blob.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            chunks.append("\n".join(current))
            current = []
    if current:
        chunks.append("\n".join(current))
    # Filter out obvious chrome (very short chunks with no letters).
    return [c for c in chunks if len(c.strip()) > 15]


def _guess_headline(lines: List[str]) -> Optional[str]:
    # The line after the author is typically their headline/role.
    return lines[1] if len(lines) > 1 and len(lines[1]) <= 140 else None


def _guess_posted(lines: List[str]) -> Optional[str]:
    for line in lines:
        low = line.lower()
        if "ago" in low or re.search(r"\b\d+\s*(h|d|w|mo|hour|day|week|month)\b", low):
            return line
    return None


def _index_reference_urls(references: List[Any]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for ref in references:
        if not isinstance(ref, dict):
            continue
        name = (ref.get("name") or ref.get("author") or ref.get("title") or "").strip()
        url = ref.get("url") or ref.get("permalink") or ref.get("link")
        if name and url:
            index[name.lower()] = url
    return index
